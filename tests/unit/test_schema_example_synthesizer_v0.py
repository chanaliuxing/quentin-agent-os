from __future__ import annotations

from quentin.tools.learning.schema_examples import synthesize_examples_from_schema


def test_synthesize_examples_from_object_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "count": {"type": "integer"},
            "flag": {"type": "boolean"},
        },
        "required": ["owner", "repo"],
    }
    examples = synthesize_examples_from_schema(input_schema=schema, tool_name="x", signature="x(owner,repo)", max_examples=2)
    assert examples
    ex = examples[0]
    assert isinstance(ex.get("input"), dict)
    assert "owner" in ex["input"]
    assert "repo" in ex["input"]

