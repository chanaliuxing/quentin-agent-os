from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, List, Tuple
from pathlib import Path
import re
from difflib import SequenceMatcher

from meta_agent.self_programming.schema import FileModification


MatchKind = Literal["exact", "normalized", "fuzzy",
                    "already_applied", "ambiguous", "not_found"]


@dataclass
class MatchResult:
    kind: MatchKind
    start_idx: Optional[int] = None
    end_idx: Optional[int] = None
    similarity: Optional[float] = None
    candidates: Optional[List[Tuple[int, int, float]]] = None  # (start, end, sim)


@dataclass
class BlockApplyReport:
    file_path: str
    match_kind: MatchKind
    similarity: Optional[float]
    message: str


def normalize_whitespace(s: str) -> str:
    """
    用于宽松匹配：忽略缩进差异、多空格差异。
    """
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in s.split("\n")]
    lines = [re.sub(r"\s+", " ", line) for line in lines if line.strip()] # Added condition to filter empty lines
    return "\n".join(lines)


def _split_lines_with_offsets(text: str):
    """
    返回 (line_text, start_idx, end_idx) 列表，
    便于从行号映射回字符区间。
    """
    lines = []
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        lines.append((line, start, end))
        start = end
    return lines


class FilePatcher:
    """
    负责把 FileModification 应用到实际文件。
    支持：
    - 精确字符串匹配
    - 忽略空白的模糊匹配（相似度阈值）
    - 幂等检查（避免重复 patch）
    """

    def __init__(self, similarity_threshold: float = 0.95):
        self.similarity_threshold = similarity_threshold

    # ==== 对外接口 ====

    def apply_modifications(
        self,
        mods: List[FileModification],
        repo_root: str = ".",
    ) -> List[BlockApplyReport]:
        """
        批量应用修改，返回每个修改的报告。
        """
        print(f"[{self.__class__.__name__}] Applying {len(mods)} modifications.")
        reports: List[BlockApplyReport] = []

        # 按 file_path 分组，可以避免重复读写
        mods_by_file: dict[str, List[FileModification]] = {}
        for m in mods:
            mods_by_file.setdefault(m.file_path, []).append(m)

        root = Path(repo_root)

        for rel_path, file_mods in mods_by_file.items():
            print(f"[{self.__class__.__name__}] Processing file: {rel_path}")
            path = (root / rel_path).resolve()
            if not path.exists() and any(m.action == "modify" for m in file_mods):
                # 修改一个不存在的文件：明确拒绝，避免无意创建。
                raise FileNotFoundError(f"Cannot modify missing file: {rel_path}")
            elif path.exists():
                text = path.read_text(encoding="utf-8")
            else:
                text = ""

            new_text, file_reports = self._apply_to_text(text, file_mods, rel_path)
            # 只要有成功改动就写回文件
            if new_text != text:
                print(f"[{self.__class__.__name__}] Writing changes to {rel_path}")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_text, encoding="utf-8")
            else:
                print(f"[{self.__class__.__name__}] No changes to write for {rel_path}")

            reports.extend(file_reports)

        return reports

    # ==== 内部实现 ====

    def _apply_to_text(
        self,
        original_text: str,
        mods: List[FileModification],
        file_path: str,
    ) -> tuple[str, List[BlockApplyReport]]:
        print(f"[{self.__class__.__name__}] Applying {len(mods)} mods to text for {file_path}")
        text = original_text
        reports: List[BlockApplyReport] = []

        for mod in mods:
            if mod.action == "delete":
                # 简化：整个文件删除交给上层处理，这里不实现局部删除
                # 你可以后续扩展为：如果 original_snippet 存在，就替换成 ""
                reports.append(
                    BlockApplyReport(
                        file_path=file_path,
                        match_kind="not_found",
                        similarity=None,
                        message="delete not implemented at FilePatcher level",
                    )
                )
                continue

            if mod.action == "create" and (not mod.original_snippet):
                # 直接全量写内容（针对新文件）
                text = mod.new_content
                reports.append(
                    BlockApplyReport(
                        file_path=file_path,
                        match_kind="exact",
                        similarity=None,
                        message="created new file content",
                    )
                )
                continue

            # modify 或 create + original_snippet != None，走匹配逻辑
            text, report = self._apply_single_block(text, mod, file_path)
            reports.append(report)

        return text, reports

    def _apply_single_block(
        self,
        text: str,
        mod: FileModification,
        file_path: str,
    ) -> tuple[str, BlockApplyReport]:
        print(f"[{self.__class__.__name__}] Applying single block for {file_path}")
        orig = mod.original_snippet or ""

        if not orig:
            # 没有 original_snippet，直接当追加/覆盖处理
            new_text = text + ("\n" if not text.endswith("\n") else "") + mod.new_content
            print(f"[FilePatcher] Applied block to {file_path}, match_kind: exact (appended)")
            return new_text, BlockApplyReport(
                file_path=file_path,
                match_kind="exact",
                similarity=None,
                message="no original_snippet given, appended new_content",
            )

        # 1) exact match occurrences
        print(f"[{self.__class__.__name__}] Attempting exact match...")
        exact_matches = [(m.start(), m.end()) for m in re.finditer(re.escape(orig), text)]

        if len(exact_matches) > 1:
            print(f"[{self.__class__.__name__}] Multiple exact matches found (n={len(exact_matches)}), skipping to avoid ambiguity.")
            return text, BlockApplyReport(
                file_path=file_path,
                match_kind="ambiguous",
                similarity=1.0,
                message=f"ambiguous exact matches (n={len(exact_matches)}), no change applied",
            )
        elif len(exact_matches) == 1:
            idx, end = exact_matches[0]
            print(f"[{self.__class__.__name__}] Exact match found at index {idx}")
            if self._already_applied(text, idx, end, mod.new_content):
                print(f"[{self.__class__.__name__}] Applied block to {file_path}, match_kind: already_applied (exact)")
                return text, BlockApplyReport(
                    file_path=file_path,
                    match_kind="already_applied",
                    similarity=1.0,
                    message="block already applied (exact slot)",
                )
            new_text = text[:idx] + mod.new_content + text[end:]
            print(f"[FilePatcher] Applied block to {file_path}, match_kind: exact")
            return new_text, BlockApplyReport(
                file_path=file_path,
                match_kind="exact",
                similarity=1.0,
                message="applied with exact match",
            )
        # If no exact match, proceed to fuzzy match


        # 2/3) normalized + fuzzy match
        print(f"[{self.__class__.__name__}] Exact match failed, trying fuzzy match...")
        match_res = self._fuzzy_match(text, orig)
        print(f"[{self.__class__.__name__}] Fuzzy match result: {match_res.kind}")


        if match_res.kind in ("fuzzy", "normalized"):
            assert match_res.start_idx is not None and match_res.end_idx is not None
            idx, end = match_res.start_idx, match_res.end_idx
            if self._already_applied(text, idx, end, mod.new_content):
                print(f"[{self.__class__.__name__}] Applied block to {file_path}, match_kind: already_applied (fuzzy)")
                return text, BlockApplyReport(
                    file_path=file_path,
                    match_kind="already_applied",
                    similarity=match_res.similarity,
                    message=f"block already applied (fuzzy slot, sim={match_res.similarity:.3f})",
                )
            new_text = text[:idx] + mod.new_content + text[end:]
            print(f"[FilePatcher] Applied block to {file_path}, match_kind: {match_res.kind}")
            return new_text, BlockApplyReport(
                file_path=file_path,
                match_kind=match_res.kind,
                similarity=match_res.similarity,
                message=f"applied with {match_res.kind} match, sim={match_res.similarity:.3f}",
            )

        if match_res.kind == "ambiguous":
            print(f"[{self.__class__.__name__}] Applied block to {file_path}, match_kind: ambiguous")
            return text, BlockApplyReport(
                file_path=file_path,
                match_kind="ambiguous",
                similarity=match_res.similarity,
                message=f"ambiguous fuzzy matches (n={len(match_res.candidates or [])}), no change applied",
            )

        # Last resort: check for idempotency if no match was found.
        # This handles re-running a patch where the 'original_snippet' is already gone.
        if normalize_whitespace(text).find(normalize_whitespace(mod.new_content)) != -1:
            print(f"[{self.__class__.__name__}] Applied block to {file_path}, match_kind: already_applied (heuristic)")
            return text, BlockApplyReport(
                file_path=file_path,
                match_kind="already_applied",
                similarity=1.0,
                message="block skipped, new_content seems to be already present in the file",
            )

        print(f"[{self.__class__.__name__}] Applied block to {file_path}, match_kind: not_found")
        return text, BlockApplyReport(
            file_path=file_path,
            match_kind="not_found",
            similarity=None,
            message="no suitable match found, block skipped",
        )

    def _fuzzy_match(self, text: str, original_snippet: str) -> MatchResult:
        """
        忽略空白的行级滑动窗口 + 相似度匹配。
        """
        orig_norm = normalize_whitespace(original_snippet)
        orig_lines = original_snippet.splitlines()
        n = max(1, len(orig_lines))

        lines_with_offsets = _split_lines_with_offsets(text)
        total_lines = len(lines_with_offsets)

        candidates: List[Tuple[int, int, float]] = []
        best_sim = 0.0

        for i in range(0, max(1, total_lines - n + 1)):
            window_lines = lines_with_offsets[i : i + n]
            window_text = "".join(l[0] for l in window_lines)
            window_norm = normalize_whitespace(window_text)
            sim = SequenceMatcher(None, orig_norm, window_norm).ratio()
            if sim >= self.similarity_threshold:
                start_idx = window_lines[0][1]
                end_idx = window_lines[-1][2]
                candidates.append((start_idx, end_idx, sim))
                if sim > best_sim:
                    best_sim = sim

        if not candidates:
            return MatchResult(kind="not_found")

        if len(candidates) == 1:
            s, e, sim = candidates[0]
            return MatchResult(
                kind="fuzzy", start_idx=s, end_idx=e, similarity=sim
            )

        # 多个候选：暂时标 ambiguous，由上层决定要不要自动选最高
        candidates.sort(key=lambda x: x[2], reverse=True)
        s, e, sim = candidates[0]
        return MatchResult(
            kind="ambiguous",
            start_idx=s,
            end_idx=e,
            similarity=sim,
            candidates=candidates,
        )

    def _already_applied(self, text: str, start: int, end: int, new_content: str) -> bool:
        """
        判断指定区间的内容是否已经非常接近 new_content（避免重复 patch）。
        """
        current_segment = text[start:end]
        if current_segment == new_content:
            return True
        old_norm = normalize_whitespace(current_segment)
        new_norm = normalize_whitespace(new_content)
        sim = SequenceMatcher(None, old_norm, new_norm).ratio()
        return sim > 0.99
