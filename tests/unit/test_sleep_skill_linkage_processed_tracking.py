from pathlib import Path

from quentin.evolution.sleep_skill_linkage import MTSSummary, SleepSkillLinkage


def test_only_unprocessed_filters_processed_summaries(tmp_path: Path) -> None:
    linkage = SleepSkillLinkage(repo_root=tmp_path)

    s1 = MTSSummary(summary_id="s1", summary_text="one", source_trace_ids=["t1"], domain="general")
    s2 = MTSSummary(summary_id="s2", summary_text="two", source_trace_ids=["t2"], domain="general")

    linkage.emit_mts_summary(s1)
    linkage.emit_mts_summary(s2)

    # Mark s1 as processed via the public consumption logger.
    linkage.log_skill_mining_consumption(summary_id="s1", skills_generated=1, notes="unit")

    unprocessed = linkage.fetch_summaries_for_skill_mining(only_unprocessed=True)
    ids = [s.summary_id for s in unprocessed]
    assert "s1" not in ids
    assert "s2" in ids

