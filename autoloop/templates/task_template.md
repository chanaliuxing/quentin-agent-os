# {agent} Task - Phase {phase_id}

## Context
{context_description}

## Module
{module_name}

## Your Tasks
1. {task_1}
2. {task_2}
3. {task_3}

## Constraints
- Work only in your assigned worktree directory
- Do not modify files outside your scope
- Follow the commit message format: agent:{agent} phase:{phase_id} module:{module_name} summary:<changes>
- Use async/await for I/O operations
- Follow Black code formatting (line length 100)
- Do not add comments unless explicitly requested

## Reference Files
- PRD: {prd_path}
- Previous results: {previous_results_path}

## Deliverables
Write your results to: `{result_file_path}`

Include:
- Task summary
- Actions taken
- Files modified
- Status (SUCCESS/FAILED/BLOCKED)
- Any issues or blockers
- Next steps or recommendations

After completing:
1. Write detailed result.md
2. Commit all changes with proper message format
3. Create completion hook: `hooks/{phase_id}_{agent}_done.json`
