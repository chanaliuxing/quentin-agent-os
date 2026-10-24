from meta_agent.self_programming.mcp_integration.schema_utils import synthesize_examples_from_schema


def test_synthesize_examples_from_schema_basic():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "flag": {"type": "boolean"},
            "choice": {"enum": ["a", "b"]},
        },
    }
    examples = synthesize_examples_from_schema(schema)
    assert examples
    ex = examples[0]["input"]
    assert ex["name"].startswith("example_")
    assert isinstance(ex["count"], int)
    assert ex["flag"] is True
    assert ex["choice"] == "a"
