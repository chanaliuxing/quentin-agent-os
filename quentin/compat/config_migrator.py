from __future__ import annotations
from typing import Dict, Any, List, Callable

class ConfigMigrator:
    """
    P6-D: Config Migrator
    Manages schema migrations for configuration files.
    """
    def __init__(self) -> None:
        self.migrations: Dict[str, List[Callable]] = {} # config_type -> list of migration fns

    def register_migration(self, config_type: str, migration_fn: Callable) -> None:
        if config_type not in self.migrations:
            self.migrations[config_type] = []
        self.migrations[config_type].append(migration_fn)

    def migrate(self, config_type: str, data: Dict[str, Any], target_version: int) -> Dict[str, Any]:
        """
        Run migrations up to the target version.
        """
        current_data = data.copy()
        current_version = data.get("version", 0)
        
        relevant_migrations = self.migrations.get(config_type, [])
        for i in range(current_version, target_version):
            if i < len(relevant_migrations):
                current_data = relevant_migrations[i](current_data)
                current_data["version"] = i + 1
        
        return current_data
