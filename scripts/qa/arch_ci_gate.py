from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import yaml


DEFAULT_SCAN_ROOTS = ("quentin", "meta_agent", "scripts")
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "venv",
    "data",
    "logs",
    "runs",
    "generated",
    "chroma_db_code_chunks",
    "tmp_playwright_profile",
    "my_profile_temp",
    "temp_test_repo",
    "temp_test_repo.local_backup",
}


@dataclass(frozen=True)
class ImportViolationKey:
    module: str
    name: str
    file: str


@dataclass
class Violation:
    rule_id: str
    file: str
    lineno: int
    message: str
    module: str = ""
    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "lineno": int(self.lineno),
            "message": self.message,
            "module": self.module,
            "name": self.name,
        }


@dataclass
class GateReport:
    ok: bool
    status: str
    violations: List[Violation]
    allowed: List[Violation]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "status": str(self.status),
            "violations": [v.to_dict() for v in self.violations],
            "allowed": [v.to_dict() for v in self.allowed],
            "meta": dict(self.meta),
        }


def _iter_python_files(repo_root: Path, scan_roots: Iterable[str]) -> List[Path]:
    out: List[Path] = []
    for root in scan_roots:
        base = (repo_root / root).resolve()
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            parts = set(path.parts)
            if parts & EXCLUDED_DIR_NAMES:
                continue
            out.append(path)
    return sorted(set(out))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _relpath_posix(path: Path, repo_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except Exception:
        rel = path
    return rel.as_posix()


def _load_allowlist(path: Path) -> Set[ImportViolationKey]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return set()
    items = data.get("allowed_imports", [])
    allowed: Set[ImportViolationKey] = set()
    if not isinstance(items, list):
        return set()
    for item in items:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module") or "").strip()
        name = str(item.get("name") or "").strip()
        file = str(item.get("file") or "").strip()
        if module and name and file:
            allowed.add(ImportViolationKey(module=module, name=name, file=file))
    return allowed


def _extract_silent_token(repo_root: Path) -> str:
    path = repo_root / "quentin" / "runtime" / "silent_protocol.py"
    if not path.exists():
        return ""
    tree = ast.parse(_read_text(path), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "SILENT_REPLY_TOKEN":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    return ""


def _check_silent_token_consistency(*, repo_root: Path, files: List[Path]) -> Tuple[List[Violation], Dict[str, Any]]:
    violations: List[Violation] = []
    canonical_path = (repo_root / "quentin" / "runtime" / "silent_protocol.py").resolve()
    canonical_rel = _relpath_posix(canonical_path, repo_root)
    canonical_token = _extract_silent_token(repo_root)

    token_defs: List[Tuple[str, str]] = []
    for path in files:
        text = _read_text(path)
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "SILENT_REPLY_TOKEN":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        token_defs.append((_relpath_posix(path, repo_root), node.value.value))
                    else:
                        token_defs.append((_relpath_posix(path, repo_root), "<non_literal>"))

    for rel, val in token_defs:
        if rel != canonical_rel:
            violations.append(
                Violation(
                    rule_id="silent_token.single_source",
                    file=rel,
                    lineno=1,
                    message="SILENT_REPLY_TOKEN must be defined only in quentin/runtime/silent_protocol.py",
                    module="",
                    name="SILENT_REPLY_TOKEN",
                )
            )
        elif canonical_token and val != canonical_token:
            violations.append(
                Violation(
                    rule_id="silent_token.value_mismatch",
                    file=rel,
                    lineno=1,
                    message="SILENT_REPLY_TOKEN value mismatch inside canonical file",
                    module="",
                    name=val,
                )
            )

    if not canonical_token:
        violations.append(
            Violation(
                rule_id="silent_token.missing",
                file=canonical_rel,
                lineno=1,
                message="Missing SILENT_REPLY_TOKEN in canonical silent_protocol.py",
                module="",
                name="",
            )
        )

    foundation_path = repo_root / "config" / "prompts" / "foundation.yaml"
    if foundation_path.exists() and canonical_token:
        foundation_text = _read_text(foundation_path)
        if canonical_token not in foundation_text:
            violations.append(
                Violation(
                    rule_id="silent_token.foundation_missing",
                    file=_relpath_posix(foundation_path, repo_root),
                    lineno=1,
                    message="foundation.yaml must mention the canonical silent token",
                    module="",
                    name=canonical_token,
                )
            )
        # Best-effort parse to ensure YAML is valid (prevents silent drift).
        try:
            yaml.safe_load(foundation_text)
        except Exception as e:
            violations.append(
                Violation(
                    rule_id="silent_token.foundation_invalid_yaml",
                    file=_relpath_posix(foundation_path, repo_root),
                    lineno=1,
                    message=f"foundation.yaml invalid YAML: {e!r}",
                    module="",
                    name="",
                )
            )

    meta = {
        "canonical_silent_token": canonical_token,
        "silent_token_definitions": [{"file": f, "value": v} for f, v in token_defs],
    }
    return violations, meta


def run_gate(
    *,
    repo_root: Path,
    allowlist_path: Path,
    scan_roots: Iterable[str] = DEFAULT_SCAN_ROOTS,
) -> GateReport:
    repo_root = repo_root.resolve()
    files = _iter_python_files(repo_root, scan_roots)
    allowed_imports = _load_allowlist(allowlist_path)

    violations: List[Violation] = []
    allowed: List[Violation] = []

    # ---- Rule: canonical loop import path (no direct loop_impl imports in non-test code) ----
    loop_reexport_rel = "quentin/cognitive/loop.py"

    # ---- Rule: deprecated MetaAgentRuntime imports (allowlisted baseline only) ----
    runtime_loop_facade_rel = "quentin/runtime/system.py"
    for path in files:
        rel = _relpath_posix(path, repo_root)
        text = _read_text(path)
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            violations.append(
                Violation(
                    rule_id="python.syntax_error",
                    file=rel,
                    lineno=int(getattr(e, "lineno", 1) or 1),
                    message=f"SyntaxError: {e.msg}",
                )
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = str(node.module or "")
                for alias in node.names:
                    name = str(alias.name or "")
                    # Canonical entry uniqueness: forbid direct imports from loop_impl outside re-export shim.
                    if mod == "quentin.cognitive.loop_impl" and rel != loop_reexport_rel:
                        violations.append(
                            Violation(
                                rule_id="entry.canonical_import",
                                file=rel,
                                lineno=int(getattr(node, "lineno", 1) or 1),
                                message="Import CognitiveLoop symbols via 'quentin.cognitive.loop' (re-export), not 'loop_impl'.",
                                module=mod,
                                name=name,
                            )
                        )

                    if mod == "quentin.runtime.system" and name == "MetaAgentRuntime":
                        v = Violation(
                            rule_id="imports.deprecated_runtime_entry",
                            file=rel,
                            lineno=int(getattr(node, "lineno", 1) or 1),
                            message="MetaAgentRuntime is a legacy runtime entry; prefer Container() + quentin.cognitive.loop.",
                            module=mod,
                            name=name,
                        )
                        key = ImportViolationKey(module=mod, name=name, file=rel)
                        if key in allowed_imports:
                            allowed.append(v)
                        else:
                            violations.append(v)

                    # Runtime loop facade should not leak as a public entrypoint.
                    if mod == "quentin.runtime.cognitive_loop" and rel != runtime_loop_facade_rel:
                        violations.append(
                            Violation(
                                rule_id="entry.runtime_facade_import",
                                file=rel,
                                lineno=int(getattr(node, "lineno", 1) or 1),
                                message="Import cognitive loop via 'quentin.cognitive.loop' (or Container.cognitive_loop); do not import runtime facade directly.",
                                module=mod,
                                name=name,
                            )
                        )

    # ---- Silent token consistency (single source + foundation parity) ----
    silent_violations, silent_meta = _check_silent_token_consistency(repo_root=repo_root, files=files)
    violations.extend(silent_violations)

    meta: Dict[str, Any] = {
        "repo_root": repo_root.as_posix(),
        "scan_roots": list(scan_roots),
        "scanned_files": len(files),
        "allowlist_path": _relpath_posix(allowlist_path, repo_root),
        "allowed_import_violations": len(allowed),
        "silent": silent_meta,
    }

    ok = len(violations) == 0
    status = "ok" if ok else "violations"
    return GateReport(ok=ok, status=status, violations=violations, allowed=allowed, meta=meta)


def main() -> int:
    p = argparse.ArgumentParser(description="Architecture CI gate: prevent main-loop fragmentation regressions.")
    p.add_argument("--repo-root", default=".", help="Repository root")
    p.add_argument("--allowlist", default="config/arch_ci_gate_allowlist.json", help="Allowlisted legacy imports JSON")
    p.add_argument("--report", default="", help="Optional path to write a JSON report")
    args = p.parse_args()

    repo_root = Path(args.repo_root)
    allowlist = (repo_root / args.allowlist).resolve() if not Path(args.allowlist).is_absolute() else Path(args.allowlist)
    report = run_gate(repo_root=repo_root, allowlist_path=allowlist)

    if args.report:
        report_path = (repo_root / args.report).resolve() if not Path(args.report).is_absolute() else Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report.to_dict(), ensure_ascii=False))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
