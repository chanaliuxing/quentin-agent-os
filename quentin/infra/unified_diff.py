from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional, Sequence, Tuple


class PatchApplyError(RuntimeError):
    pass


_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_len>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_len>\d+))? @@"
)


def _normalize_path(p: str) -> Optional[str]:
    p = (p or "").strip()
    if not p:
        return None
    # The first token is the path; ignore timestamps.
    p = p.split("\t", 1)[0].split(" ", 1)[0]
    if p == "/dev/null":
        return None
    if p.startswith("a/") or p.startswith("b/"):
        p = p[2:]
    return p


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: Tuple[str, ...]


@dataclass(frozen=True)
class FilePatch:
    old_path: Optional[str]
    new_path: Optional[str]
    hunks: Tuple[Hunk, ...]


def parse_unified_diff(diff_text: str) -> List[FilePatch]:
    lines = diff_text.splitlines(keepends=True)
    patches: List[FilePatch] = []

    i = 0
    current_old: Optional[str] = None
    current_new: Optional[str] = None
    hunks: List[Hunk] = []

    def flush() -> None:
        nonlocal current_old, current_new, hunks
        if hunks:
            patches.append(FilePatch(old_path=current_old, new_path=current_new, hunks=tuple(hunks)))
        current_old = None
        current_new = None
        hunks = []

    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            flush()
            current_old = _normalize_path(line[4:])
            i += 1
            if i < len(lines) and lines[i].startswith("+++ "):
                current_new = _normalize_path(lines[i][4:])
                i += 1
            continue

        if line.startswith("@@ "):
            m = _HUNK_RE.match(line.rstrip("\n"))
            if not m:
                raise PatchApplyError(f"Invalid hunk header: {line!r}")
            old_start = int(m.group("old_start"))
            old_len = int(m.group("old_len") or "1")
            new_start = int(m.group("new_start"))
            new_len = int(m.group("new_len") or "1")
            i += 1
            hunk_lines: List[str] = []
            while i < len(lines):
                l2 = lines[i]
                if l2.startswith("@@ ") or l2.startswith("--- "):
                    break
                if l2.startswith(("\\",)):
                    # "\ No newline at end of file" – ignore marker.
                    i += 1
                    continue
                if not l2 or l2[0] not in (" ", "+", "-"):
                    break
                hunk_lines.append(l2)
                i += 1
            hunks.append(
                Hunk(
                    old_start=old_start,
                    old_len=old_len,
                    new_start=new_start,
                    new_len=new_len,
                    lines=tuple(hunk_lines),
                )
            )
            continue

        i += 1

    flush()
    if not patches:
        # Diff without headers; still allow hunks-only diffs.
        # This parser only captures hunks after encountering "@@" lines. If none exist, return [].
        return []
    return patches


def _line_text(patch_line: str) -> str:
    return patch_line[1:]


def _lines_equal(patch_line: str, original_line: str) -> bool:
    a = _line_text(patch_line)
    b = original_line
    if a.endswith("\n") != b.endswith("\n"):
        return a.rstrip("\n") == b.rstrip("\n")
    return a == b


def apply_file_patch(original_text: str, file_patch: FilePatch) -> str:
    if not file_patch.hunks:
        return original_text
    original_lines = original_text.splitlines(keepends=True)
    out: List[str] = []
    pos = 0

    for hunk in file_patch.hunks:
        # Unified diff is 1-based. Some tools emit 0 for empty files; treat it as 1.
        start_old = max(1, int(hunk.old_start))
        target_pos = start_old - 1
        if target_pos < pos:
            raise PatchApplyError("Overlapping hunks are not supported in v1 applier.")

        out.extend(original_lines[pos:target_pos])
        pos = target_pos

        for pl in hunk.lines:
            if not pl:
                continue
            marker = pl[0]
            if marker == " ":
                if pos >= len(original_lines) or not _lines_equal(pl, original_lines[pos]):
                    got = original_lines[pos] if pos < len(original_lines) else "<EOF>"
                    raise PatchApplyError(f"Context mismatch at line {pos + 1}: expected={_line_text(pl)!r} got={got!r}")
                out.append(original_lines[pos])
                pos += 1
            elif marker == "-":
                if pos >= len(original_lines) or not _lines_equal(pl, original_lines[pos]):
                    got = original_lines[pos] if pos < len(original_lines) else "<EOF>"
                    raise PatchApplyError(f"Removal mismatch at line {pos + 1}: expected={_line_text(pl)!r} got={got!r}")
                pos += 1
            elif marker == "+":
                out.append(_line_text(pl))
            else:
                raise PatchApplyError(f"Invalid patch line marker: {marker!r}")

    out.extend(original_lines[pos:])
    return "".join(out)


def apply_unified_diff_to_text(original_text: str, diff_text: str) -> str:
    patches = parse_unified_diff(diff_text)
    if not patches:
        raise PatchApplyError("No file patches found in unified diff.")
    if len(patches) != 1:
        raise PatchApplyError(f"Expected single-file unified diff, got {len(patches)} file patches.")
    return apply_file_patch(original_text, patches[0])


def select_file_patches_for_targets(
    diff_text: str, targets: Sequence[str]
) -> List[Tuple[str, FilePatch]]:
    """
    Returns a list of (target_path, file_patch) pairs to apply.

    Safety note: this only returns patches that match a provided target path, unless the diff
    is header-less (old_path/new_path are None) and there is exactly one target.
    """
    patches = parse_unified_diff(diff_text)
    if not patches:
        raise PatchApplyError("No file patches found in unified diff.")

    target_set = set(str(t) for t in (targets or []))
    if not target_set:
        # Apply whatever is in the diff.
        out: List[Tuple[str, FilePatch]] = []
        for fp in patches:
            path = fp.new_path or fp.old_path
            if not path:
                raise PatchApplyError("Diff contains header-less patch but no explicit targets were provided.")
            out.append((path, fp))
        return out

    out = []
    for fp in patches:
        p = fp.new_path or fp.old_path
        if p and p in target_set:
            out.append((p, fp))

    if out:
        return out

    # Header-less diff: apply to the only target.
    if len(patches) == 1 and (patches[0].old_path is None and patches[0].new_path is None) and len(target_set) == 1:
        only = next(iter(target_set))
        return [(only, patches[0])]

    raise PatchApplyError("No diff file patch matches provided targets.")

