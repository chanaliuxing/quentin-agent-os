# Phase Report: {phase_id}

## Project Information
- **Project ID**: {project_id}
- **Phase**: {phase_number}
- **Started**: {start_timestamp}
- **Completed**: {completion_timestamp}
- **Duration**: {duration_seconds}s

## Tasks Assigned
| Agent | Module | Priority | Status |
|-------|--------|----------|--------|
| {agent_1} | {module_1} | {priority_1} | {status_1} |
| {agent_2} | {module_2} | {priority_2} | {status_2} |

## Agent Results Summary

### Lead
{lead_summary}

### Planner
{planner_summary}

### Reviewer
{reviewer_summary}

### Dev
{dev_summary}

### QA
{qa_summary}

## Git Overlap Analysis

### Files with Multiple Agent Modifications
| File Path | Agents | Risk Level |
|-----------|--------|------------|
| {file_1} | {agents_1} | {risk_1} |
| {file_2} | {agents_2} | {risk_2} |

**Total Overlaps**: {overlap_count}

### Overlap Details
{detailed_overlap_analysis}

### Recommended Actions
{overlap_resolution_recommendations}

## Test Results

### Unit Tests
- Total: {unit_total}
- Passed: {unit_passed}
- Failed: {unit_failed}
- Skipped: {unit_skipped}

### Integration Tests
- Total: {integration_total}
- Passed: {integration_passed}
- Failed: {integration_failed}
- Skipped: {integration_skipped}

### Failed Tests
{list_of_failed_tests}

## Code Quality Metrics
- Lines of code changed: {loc_changed}
- Files modified: {files_modified}
- Commits: {commit_count}

## Issues & Blockers
{list_of_issues_and_blockers}

## Review Loop Summary
- Planner ↔ Reviewer loops: {planner_reviewer_loops}
- Dev ↔ QA loops: {dev_qa_loops}

## Phase Status
**{COMPLETED | FAILED | BLOCKED}**

### Success Criteria
- [ ] All tasks completed
- [ ] All tests passing
- [ ] No high-risk git overlaps
- [ ] Code review approved
- [ ] Integration tests passed

## Next Phase Planning
{recommendations_for_next_phase}

## Artifacts
- Task files: `phases/{phase_id}/tasks/`
- Result files: `phases/{phase_id}/results/`
- Logs: `runtime/logs/`
- Hooks: `runtime/hooks/`

---
Generated: {generation_timestamp}
