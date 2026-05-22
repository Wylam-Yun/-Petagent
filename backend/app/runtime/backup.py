"""SQLite database backup manager (CC-9, STAB-023)."""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.pet.state import LockedSQLiteConnection

logger = logging.getLogger(__name__)


class DatabaseBackupManager:
    """Manages rolling SQLite backups.

    - Routine backups: once per day, keep 7 most recent
    - Pre-migration backups: before schema version changes, keep 3 most recent
    Uses sqlite3.Connection.backup() for online safe backup.
    """

    def __init__(
        self,
        connection: "LockedSQLiteConnection",
        backup_dir: Path,
        max_routine: int = 7,
        max_pre_migration: int = 3,
    ) -> None:
        self.connection = connection
        self.backup_dir = backup_dir
        self.max_routine = max_routine
        self.max_pre_migration = max_pre_migration
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_routine_backup(self) -> Optional[Path]:
        """Create a routine daily backup. Returns path or None on failure."""
        return self._create_backup("pet", "routine")

    def create_pre_migration_backup(self, version: str) -> Optional[Path]:
        """Create a pre-migration backup. Returns path or None on failure."""
        return self._create_backup("pre-migration-v%s" % version, "pre_migration")

    def _create_backup(self, prefix: str, category: str) -> Optional[Path]:
        """Create a backup using sqlite3.Connection.backup()."""
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = "%s-%s.db" % (prefix, stamp)
        path = self.backup_dir / filename

        try:
            with self.connection.locked():
                raw = getattr(self.connection, "_connection", self.connection)
                dest = sqlite3.connect(str(path))
                try:
                    raw.backup(dest)
                finally:
                    dest.close()
            logger.info("Created %s backup: %s", category, path.name)
        except Exception:
            logger.warning("Failed to create %s backup", category, exc_info=True)
            path.unlink(missing_ok=True)
            return None

        # Prune old backups of same category
        self._prune(category)
        return path

    def _prune(self, category: str) -> None:
        """Prune old backups keeping max_routine or max_pre_migration."""
        max_keep = self.max_routine if category == "routine" else self.max_pre_migration
        prefix = "pet-" if category == "routine" else "pre-migration-"

        try:
            backups = sorted(
                [f for f in self.backup_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".db"],
                key=lambda f: f.name,
                reverse=True,
            )
            for old in backups[max_keep:]:
                old.unlink(missing_ok=True)
                logger.debug("Pruned old backup: %s", old.name)
        except Exception:
            logger.warning("Backup pruning failed", exc_info=True)

    def last_backup_time(self) -> Optional[str]:
        """Return the timestamp of the most recent routine backup, or None."""
        try:
            backups = sorted(
                [f for f in self.backup_dir.iterdir() if f.name.startswith("pet-") and f.suffix == ".db"],
                key=lambda f: f.name,
                reverse=True,
            )
            if backups:
                return backups[0].stem.replace("pet-", "")
        except Exception:
            pass
        return None
