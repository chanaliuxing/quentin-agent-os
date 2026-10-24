# P6 Compatibility Policy

## Versioning
Quentin uses Semantic Versioning (SemVer) for its Platform API.

## Version Routing
The `VersionRouter` allows the system to support multiple API versions simultaneously.
- `v1`: Original stable API.
- `v2`: Enhanced concurrent API (example).

## Config Migration
When updating Quentin, use the `ConfigMigrator` to upgrade your `config/*.yaml` files to the latest schema without losing data.
- **Dry-run**: Always test migrations with `dry_run=True` first.
- **Rollback**: Keep backups of configuration files before running migrations.
