from __future__ import annotations

import sqlite3
from pathlib import Path

from app.pet.state import PetStateStore


def test_corrupt_database_is_quarantined_and_recreated(tmp_path: Path) -> None:
    db_path = tmp_path / "pet.db"
    db_path.write_bytes(b"not a sqlite database")
    (tmp_path / "pet.db-wal").write_bytes(b"wal bytes")
    (tmp_path / "pet.db-shm").write_bytes(b"shm bytes")

    store = PetStateStore(db_path)

    assert store.get_state()["name"] == "豆豆"
    assert sqlite3.connect(db_path).execute("PRAGMA quick_check").fetchone()[0] == "ok"

    backup_roots = list((tmp_path / "db-backups").glob("corrupt-*"))
    assert len(backup_roots) == 1
    backup_root = backup_roots[0]
    assert (backup_root / "pet.db").read_bytes() == b"not a sqlite database"
    assert (backup_root / "pet.db-wal").read_bytes() == b"wal bytes"
    assert (backup_root / "pet.db-shm").read_bytes() == b"shm bytes"


def test_valid_database_is_not_quarantined(tmp_path: Path) -> None:
    db_path = tmp_path / "pet.db"
    first_store = PetStateStore(db_path)
    state = first_store.get_state()
    state["intimacy"] = 77
    first_store.save_state(state)

    second_store = PetStateStore(db_path)

    assert second_store.get_state()["intimacy"] == 77
    assert not (tmp_path / "db-backups").exists()
