# Task Packet

## Packet Header
- `task_id`: `{{ task_id }}`
- `run_id`: `{{ run_id }}`
- `phase_id`: `{{ phase_id }}`
- `module_id`: `{{ module_id }}`
- `agent`: `{{ agent }}`

## Source Of Truth References
{% for ref in sor_refs %}
- `{{ ref }}`
{% endfor %}

## Inputs
{% for artifact_id in input_artifact_ids %}
- `{{ artifact_id }}`
{% endfor %}

## Writable Scope
{% for path in writable_paths %}
- `{{ path }}`
{% endfor %}

## Expected Output Contract
- `contract`: `{{ expected_output_contract }}`

## Gate Expectations
{% for gate in gate_expectations %}
- `{{ gate }}`
{% endfor %}

## Execution Rules
- Only modify files inside the writable scope.
- Treat Source-of-Truth references as authoritative.
- Write structured result output that can be validated against the result packet schema.
- Record blockers with explicit artifact or gate references.
