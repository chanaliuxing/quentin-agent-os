from pathlib import Path
from collections import defaultdict
from git import Repo
from app.models import GitOverlap, AgentRole
from app.config import settings
from app.observability.metrics import MetricsCollector


def detect_git_overlaps(
    repo_path: Path, phase_id: str, agent_commits: dict[AgentRole, list[str]]
) -> list[GitOverlap]:
    try:
        repo = Repo(repo_path)
    except Exception:
        return []
    file_modifications: dict[str, dict[AgentRole, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for agent, commit_shas in agent_commits.items():
        for sha in commit_shas:
            try:
                commit = repo.commit(sha)
                for item in commit.stats.files.keys():
                    file_modifications[item][agent].append(sha)
            except Exception:
                continue

    overlaps = []
    for file_path, agents_dict in file_modifications.items():
        if len(agents_dict) >= settings.git_overlap_threshold:
            agents = list(agents_dict.keys())
            all_commits = []
            for commits in agents_dict.values():
                all_commits.extend(commits)

            risk_level = "high" if len(agents_dict) >= 3 else "medium"

            overlap = GitOverlap(
                file_path=file_path,
                agents=agents,
                commits=all_commits,
                risk_level=risk_level,
            )
            overlaps.append(overlap)

            MetricsCollector.increment_conflicts(phase_id, risk_level, count=1)

    return overlaps
