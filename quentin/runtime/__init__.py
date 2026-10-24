"""
Runtime package.

Avoid importing heavy runtime wiring at import-time to prevent circular imports
(`traces` -> `runtime.session_write_lock` -> `runtime.__init__` -> `runtime.system` -> `traces`).
"""
__all__: list[str] = []
