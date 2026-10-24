import pytest
from quentin.compat.config_migrator import ConfigMigrator

def test_config_migration_sequence():
    migrator = ConfigMigrator()
    
    # Register migrations
    def m1(data):
        data["new_field"] = "added"
        return data
        
    def m2(data):
        data["v2_field"] = data.pop("old_field")
        return data
        
    migrator.register_migration("auth", m1)
    migrator.register_migration("auth", m2)
    
    # Run migration from v0 to v2
    original = {"version": 0, "old_field": "secret"}
    migrated = migrator.migrate("auth", original, target_version=2)
    
    assert migrated["version"] == 2
    assert migrated["new_field"] == "added"
    assert migrated["v2_field"] == "secret"
    assert "old_field" not in migrated
