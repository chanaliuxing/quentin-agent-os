"""
Make `tests` a regular Python package.

Without this file, Python treats `tests` as a namespace package and may merge it
with unrelated `tests` directories on `sys.path`, which can lead to surprising
imports and environment-specific failures.
"""

