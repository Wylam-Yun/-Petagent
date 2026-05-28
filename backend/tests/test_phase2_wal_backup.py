"""Tests for STAB-022/023: WAL checkpoint and DB backup."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.pet.state import LockedSQLiteConnection
from app.runtime.backup import DatabaseBackupManager
from app.runtime.maintenance import MaintenanceService


def _make_connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return LockedSQLiteConnection(conn)


# --- Backup tests ---


def test_create_routine_backup(tmp_path):
    conn = _make_connection()
    conn.execute("CREATE TABLE test (id INTEGER)")
    conn.execute("INSERT INTO test VALUES (1)")
    conn.commit()

    mgr = DatabaseBackupManager(conn, backup_dir=tmp_path)
    path = mgr.create_routine_backup()

    assert path is not None
    assert path.exists()
    assert path.name.startswith("pet-")
    assert path.suffix == ".db"

    # Verify backup contains data
    bconn = sqlite3.connect(str(path))
    row = bconn.execute("SELECT * FROM test").fetchone()
    assert row[0] == 1
    bconn.close()


def test_create_pre_migration_backup(tmp_path):
    conn = _make_connection()
    mgr = DatabaseBackupManager(conn, backup_dir=tmp_path)

    path = mgr.create_pre_migration_backup("42")
    assert path is not None
    assert "pre-migration-v42" in path.name


def test_prune_old_routine_backups(tmp_path):
    conn = _make_connection()
    mgr = DatabaseBackupManager(conn, backup_dir=tmp_path, max_routine=3)

    # Create 5 backups
    for i in range(5):
        stamp = "2026010%d-000000" % (i + 1)
        (tmp_path / ("pet-%s.db" % stamp)).touch()

    # Trigger prune by creating a new backup
    mgr.create_routine_backup()

    # Should have at most 3 routine backups + the one just created = max 3
    routine = [f for f in tmp_path.iterdir() if f.name.startswith("pet-") and f.suffix == ".db"]
    assert len(routine) <= 3


def test_last_backup_time(tmp_path):
    conn = _make_connection()
    mgr = DatabaseBackupManager(conn, backup_dir=tmp_path)

    assert mgr.last_backup_time() is None

    (tmp_path / "pet-20260522-120000.db").touch()
    assert mgr.last_backup_time() == "20260522-120000"


# --- Maintenance WAL checkpoint tests ---


def test_wal_checkpoint_runs():
    conn = _make_connection()
    svc = MaintenanceService.__new__(MaintenanceService)
    svc.connection = conn
    svc.wal_checkpoint_interval_seconds = 1800
    svc._write_count = 0
    svc._last_wal_checkpoint_at = None
    svc._wal_checkpoint_retry_after = None

    # First call should run (no previous checkpoint)
    assert svc.wal_checkpoint_if_due() is True
    assert svc._last_wal_checkpoint_at is not None
    assert svc._wal_checkpoint_retry_after is None
    assert svc._write_count == 0


def test_wal_checkpoint_skips_when_not_due():
    conn = _make_connection()
    svc = MaintenanceService.__new__(MaintenanceService)
    svc.connection = conn
    svc.wal_checkpoint_interval_seconds = 1800
    svc._write_count = 0
    svc._last_wal_checkpoint_at = datetime.utcnow()
    svc._wal_checkpoint_retry_after = None

    # Just ran — should skip
    assert svc.wal_checkpoint_if_due() is False


def test_wal_checkpoint_runs_on_write_count():
    conn = _make_connection()
    svc = MaintenanceService.__new__(MaintenanceService)
    svc.connection = conn
    svc.wal_checkpoint_interval_seconds = 1800
    svc._write_count = 100
    svc._last_wal_checkpoint_at = datetime.utcnow()
    svc._wal_checkpoint_retry_after = None

    # 100 writes threshold met
    assert svc.wal_checkpoint_if_due() is True
    assert svc._write_count == 0


def test_wal_checkpoint_backs_off_after_lock_error():
    class FailingConnection:
        calls = 0

        def locked(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, _sql):
            self.calls += 1
            raise sqlite3.OperationalError("database table is locked")

    conn = FailingConnection()
    svc = MaintenanceService.__new__(MaintenanceService)
    svc.connection = conn
    svc.wal_checkpoint_interval_seconds = 1800
    svc._write_count = 100
    svc._last_wal_checkpoint_at = datetime.utcnow() - timedelta(hours=1)
    svc._wal_checkpoint_retry_after = None

    assert svc.wal_checkpoint_if_due() is False
    assert conn.calls == 1
    assert svc._wal_checkpoint_retry_after is not None

    assert svc.wal_checkpoint_if_due() is False
    assert conn.calls == 1


def test_daily_backup_if_due(tmp_path):
    conn = _make_connection()
    mgr = DatabaseBackupManager(conn, backup_dir=tmp_path)

    svc = MaintenanceService.__new__(MaintenanceService)
    svc.backup_manager = mgr
    svc._last_backup_date = None

    assert svc.daily_backup_if_due() is True
    assert svc._last_backup_date == datetime.utcnow().strftime("%Y-%m-%d")


def test_daily_backup_skips_already_done(tmp_path):
    conn = _make_connection()
    mgr = DatabaseBackupManager(conn, backup_dir=tmp_path)

    svc = MaintenanceService.__new__(MaintenanceService)
    svc.backup_manager = mgr
    svc._last_backup_date = datetime.utcnow().strftime("%Y-%m-%d")

    assert svc.daily_backup_if_due() is False
