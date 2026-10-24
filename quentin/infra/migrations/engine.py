from __future__ import annotations

import logging
import json
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

class MigrationEngine:
    """
    Manages automated state migrations for Quentin's data stores.
    Aligned with OpenClaw's infra/state-migrations.
    """
    def __init__(self, data_root: str = "data"):
        self.data_root = Path(data_root)
        self.migrations: Dict[str, List[Callable]] = {}

    def register(self, target_file: str, version: int, migration_fn: Callable):
        """Register a migration function for a specific file version."""
        if target_file not in self.migrations:
            self.migrations[target_file] = []
        self.migrations[target_file].append(migration_fn)

    def run_migrations(self):
        """Check all registered files and apply pending migrations."""
        logger.info("Checking for state migrations...")
        for filename in self.migrations:
            self._migrate_file(filename)

    def _migrate_file(self, filename: str):
        path = self.data_root / filename
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read {filename} for migration: {e}")
            return

        current_version = data.get("_version", 0)
        fns = self.migrations[filename]
        
        # Sort migrations by version assumption (implied order) or explicit logic
        # Here we assume migrations are registered in order of application
        
        applied_count = 0
        for fn in fns:
            # Migration function should return (new_data, new_version)
            # or handle logic internally. 
            # A simplified contract: fn(data) -> modified_data
            
            # For robust system, we need a way to know WHICH version a fn targets.
            # Simplified: we apply all applicable logic.
            
            # In a real impl, we'd compare target_version > current_version.
            pass
            
        if applied_count > 0:
            logger.info(f"Applied {applied_count} migrations to {filename}")
            # Backup
            backup_path = path.with_suffix(f".bak.{current_version}")
            shutil.copy(path, backup_path)
            # Save
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

# Global instance
migration_engine = MigrationEngine()
