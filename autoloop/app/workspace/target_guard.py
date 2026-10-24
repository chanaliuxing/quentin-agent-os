from __future__ import annotations

import fnmatch
from pathlib import Path
from pydantic import BaseModel, Field


class PathGuardResult(BaseModel):
    ok: bool
    invalid_paths: list[str] = Field(default_factory=list)
    ignored_paths: list[str] = Field(default_factory=list)


NON_SOURCE_ARTIFACT_PATTERNS = (
    "phases/**/results/**",
    "phases/**/tasks/**",
    "phases/**/reports/**",
    "phases/**/phase_report.md",
    "runtime/**",
)


def _normalize_for_match(path_value: str, repo_root: Path) -> str:
    candidate = Path(path_value)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(repo_root.resolve())
        except Exception:
            candidate = Path(path_value)
    return candidate.as_posix().lstrip("./")


def is_non_source_artifact_path(path_value: str, repo_root: Path) -> bool:
    normalized = _normalize_for_match(path_value, repo_root)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in NON_SOURCE_ARTIFACT_PATTERNS)


def split_claimed_paths(
    *,
    claimed_paths: list[str],
    repo_root: Path,
) -> tuple[list[str], list[str]]:
    filtered: list[str] = []
    ignored: list[str] = []
    for item in claimed_paths:
        if is_non_source_artifact_path(item, repo_root):
            ignored.append(item)
        else:
            filtered.append(item)
    return filtered, ignored


def validate_claimed_paths(
    *,
    claimed_paths: list[str],
    allowed_patterns: list[str],
    repo_root: Path,
) -> PathGuardResult:
    if not claimed_paths or not allowed_patterns:
        return PathGuardResult(ok=True, invalid_paths=[], ignored_paths=[])

    filtered_paths, ignored_paths = split_claimed_paths(
        claimed_paths=claimed_paths,
        repo_root=repo_root,
    )
    if not filtered_paths:
        return PathGuardResult(ok=True, invalid_paths=[], ignored_paths=ignored_paths)

    invalid: list[str] = []
    for item in filtered_paths:
        normalized = _normalize_for_match(item, repo_root)
        if not any(fnmatch.fnmatch(normalized, pattern) for pattern in allowed_patterns):
            invalid.append(item)

    return PathGuardResult(ok=not invalid, invalid_paths=invalid, ignored_paths=ignored_paths)
