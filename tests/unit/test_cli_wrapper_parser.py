import os
import stat
import textwrap

from meta_agent.self_programming.tools.cli_wrapper import ExternalCLITool
from meta_agent.self_programming.schema import ProgrammingTask


def test_parse_patch_blocks_parses_multiple_blocks():
    raw = """Some preface
<<<< SEARCH
old line
====
new line
>>>>
Trailing text
<<<< SEARCH
foo
====
bar
>>>>
"""
    mods = ExternalCLITool._parse_patch_blocks(raw, "file.py")
    assert len(mods) == 2
    assert mods[0].original_snippet == "old line"
    assert mods[0].new_content == "new line"
    assert mods[0].file_path == "file.py"
    assert mods[1].original_snippet == "foo"
    assert mods[1].new_content == "bar"


def test_generate_code_changes_with_stub_cli(tmp_path):
    script = tmp_path / "stub_cli.py"
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write('<<<< SEARCH\\nold\\n====\\nnew\\n>>>>\\n')\n")
    script.chmod(stat.S_IRWXU)

    tool = ExternalCLITool(name="stub", cli_cmd=str(script), enabled=True)

    task = ProgrammingTask(
        task_id="t1",
        origin="experiment",
        description="test",
        repo_root=".",
        related_files=[],
        context_summary="",
        constraints={},
        acceptance_criteria=[],
    )

    mods = tool.generate_code_changes(
        task=task,
        file_path="file.py",
        file_content="old",
        instructions="replace old with new",
    )
    assert len(mods) == 1
    assert mods[0].original_snippet == "old"
    assert mods[0].new_content == "new"
    assert mods[0].file_path == "file.py"
