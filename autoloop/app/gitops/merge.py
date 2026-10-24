from pathlib import Path


def resolve_conflict_markers(content: str, strategy: str = "ours") -> str:
    if strategy not in {"ours", "theirs"}:
        raise ValueError("strategy must be ours or theirs")

    output: list[str] = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("<<<<<<< "):
            output.append(line)
            index += 1
            continue

        index += 1
        ours: list[str] = []
        theirs: list[str] = []
        while index < len(lines) and not lines[index].startswith("======="):
            ours.append(lines[index])
            index += 1
        index += 1
        while index < len(lines) and not lines[index].startswith(">>>>>>> "):
            theirs.append(lines[index])
            index += 1
        index += 1
        output.extend(ours if strategy == "ours" else theirs)

    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(output) + trailing_newline


def auto_resolve_conflicts_in_repo(repo_path: Path, strategy: str = "ours") -> list[str]:
    resolved_files: list[str] = []
    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "<<<<<<< " not in content or "=======" not in content or ">>>>>>> " not in content:
            continue
        file_path.write_text(resolve_conflict_markers(content, strategy=strategy), encoding="utf-8")
        resolved_files.append(str(file_path))
    return resolved_files
