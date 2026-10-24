import pytest
from pathlib import Path

from meta_agent.self_programming.schema import FileModification
from meta_agent.self_programming.infra.file_patcher import FilePatcher, MatchKind, normalize_whitespace

# Define a temporary directory for test files
@pytest.fixture
def tmp_path_for_tests(tmp_path):
    return tmp_path

@pytest.fixture
def file_patcher():
    return FilePatcher(similarity_threshold=0.9)

# Helper function to create a test file
def create_test_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def read_test_file(path: Path):
    return path.read_text(encoding="utf-8")

# Test 1: Exact matching and successful replacement
def test_exact_match_and_replace(file_patcher, tmp_path_for_tests):
    file_content = "def foo():\n    return 1\n"
    new_content = "def bar():\n    return 2\n"
    file_path = tmp_path_for_tests / "test_file.py"
    create_test_file(file_path, file_content)

    mod = FileModification(
        file_path="test_file.py",
        action="modify",
        original_snippet="def foo():\n    return 1\n",
        new_content=new_content,
    )

    reports = file_patcher.apply_modifications([mod], repo_root=str(tmp_path_for_tests))
    assert len(reports) == 1
    assert reports[0].match_kind == "exact"
    assert read_test_file(file_path) == new_content

# Test 2: Fuzzy matching ignoring whitespace
def test_fuzzy_match_and_replace(file_patcher, tmp_path_for_tests):
    file_content = "def foo():\n    return 1\n"
    original_snippet_fuzzy = "def foo():\n  return 1\n" # different indentation
    new_content = "def bar():\n    return 2\n"
    file_path = tmp_path_for_tests / "test_file_fuzzy.py"
    create_test_file(file_path, file_content)

    mod = FileModification(
        file_path="test_file_fuzzy.py",
        action="modify",
        original_snippet=original_snippet_fuzzy,
        new_content=new_content,
    )

    reports = file_patcher.apply_modifications([mod], repo_root=str(tmp_path_for_tests))
    assert len(reports) == 1
    assert reports[0].match_kind in ("fuzzy", "normalized")
    assert read_test_file(file_path) == new_content

# Test 3: Idempotency (already applied)
def test_idempotency(file_patcher, tmp_path_for_tests):
    file_content_for_idempotency = "def my_func():\n    print('hello')\n"
    mod_orig_snippet = "def my_func():\n    print('hello')\n"
    mod_new_content = "def my_func():\n    print('hello world')\n" # Different from current
    file_path = tmp_path_for_tests / "test_file_idempotent.py"

    # Case 1: The content to search for is already the new_content, expect 'already_applied'
    create_test_file(file_path, mod_new_content) # File already has the new_content
    mod_idempotent_test = FileModification(
        file_path="test_file_idempotent.py",
        action="modify",
        original_snippet=mod_new_content, # The content to search for is already the new_content
        new_content=mod_new_content,
    )
    reports_idempotent = file_patcher.apply_modifications([mod_idempotent_test], repo_root=str(tmp_path_for_tests))
    assert len(reports_idempotent) == 1
    assert reports_idempotent[0].match_kind == "already_applied"
    assert read_test_file(file_path) == mod_new_content # File content remains unchanged

    # Case 2: The original_snippet matches exactly, but the file content is different from new_content
    create_test_file(file_path, file_content_for_idempotency) # File has original content
    mod_apply_change = FileModification(
        file_path="test_file_idempotent.py",
        action="modify",
        original_snippet=mod_orig_snippet,
        new_content=mod_new_content,
    )
    reports_apply_change = file_patcher.apply_modifications([mod_apply_change], repo_root=str(tmp_path_for_tests))
    assert len(reports_apply_change) == 1
    assert reports_apply_change[0].match_kind == "exact"
    assert read_test_file(file_path) == mod_new_content # File content should be updated

# Test 4: Not finding the snippet
def test_not_found(file_patcher, tmp_path_for_tests):
    file_content = "def func_a():\n    pass\n"
    file_path = tmp_path_for_tests / "test_file_not_found.py"
    create_test_file(file_path, file_content)

    mod = FileModification(
        file_path="test_file_not_found.py",
        action="modify",
        original_snippet="def non_existent_func():\n    pass\n",
        new_content="def new_func():\n    pass\n",
    )

    reports = file_patcher.apply_modifications([mod], repo_root=str(tmp_path_for_tests))
    assert len(reports) == 1
    assert reports[0].match_kind == "not_found"
    assert read_test_file(file_path) == file_content # File should remain unchanged

# Test for ambiguous exact matches
def test_ambiguous_exact_match(file_patcher, tmp_path_for_tests):
    file_content = "Line 1: common string\nLine 2: common string\nLine 3: unique\nLine 4: common string\n"
    file_path = tmp_path_for_tests / "test_file_ambiguous.txt"
    create_test_file(file_path, file_content)

    ambiguous_snippet = "common string" # This string appears multiple times
    new_content = "replaced string"

    mod = FileModification(
        file_path="test_file_ambiguous.txt",
        action="modify",
        original_snippet=ambiguous_snippet,
        new_content=new_content,
    )

    # With a similarity threshold, a short, repeated string might lead to ambiguous results
    reports = file_patcher.apply_modifications([mod], repo_root=str(tmp_path_for_tests))
    assert len(reports) == 1
    assert reports[0].match_kind == "ambiguous"
    assert "ambiguous exact matches" in reports[0].message
    assert read_test_file(file_path) == file_content # File should remain unchanged

# Test for 'create' action for a new file
def test_create_new_file(file_patcher, tmp_path_for_tests):
    file_path = tmp_path_for_tests / "new_file.txt"
    new_content = "This is a brand new file."

    mod = FileModification(
        file_path="new_file.txt",
        action="create",
        original_snippet=None, # Indicates a new file creation
        new_content=new_content,
    )

    reports = file_patcher.apply_modifications([mod], repo_root=str(tmp_path_for_tests))
    assert len(reports) == 1
    assert reports[0].match_kind == "exact"
    assert file_path.exists()
    assert read_test_file(file_path) == new_content

# Test for 'create' action with original_snippet (should behave like modify if file exists)
def test_create_action_on_existing_file(file_patcher, tmp_path_for_tests):
    file_content = "Existing content."
    file_path = tmp_path_for_tests / "existing_file.txt"
    create_test_file(file_path, file_content)

    new_content = "Modified content."
    mod = FileModification(
        file_path="existing_file.txt",
        action="create", # Action is create, but file exists and original_snippet is provided
        original_snippet=file_content,
        new_content=new_content,
    )

    reports = file_patcher.apply_modifications([mod], repo_root=str(tmp_path_for_tests))
    assert len(reports) == 1
    assert reports[0].match_kind == "exact"
    assert read_test_file(file_path) == new_content

# Test for normalize_whitespace helper
def test_normalize_whitespace():
    assert normalize_whitespace("  hello   world  ") == "hello world"
    assert normalize_whitespace("hello\n  world") == "hello\nworld"
    assert normalize_whitespace("  line1\n\t  line2 \nline3  ") == "line1\nline2\nline3"
    assert normalize_whitespace("") == ""
    assert normalize_whitespace("  \t \n\n ") == ""