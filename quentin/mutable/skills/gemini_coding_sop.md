# SOP: Coding with Gemini CLI

## Context
Use this skill when you encounter complex programming tasks, bug fixes, or architecture design. The Gemini CLI is optimized for high-quality code generation and project-aware patches.

## Triggers
- "fix bug", "implement feature", "refactor code", "add tests", "coding task"

## Steps
1. **Gather Context**: Use `ls` or `find` to identify relevant files.
2. **Prepare Instructions**: Formulate a clear objective. Mention specific technologies or patterns to use.
3. **Invoke Tool**: Call `gemini.code` or `coder.generate` with the `backend='gemini_cli'`.
4. **Context Files**: ALWAYS provide the full paths of files that need to be read or modified in the `context_files` argument.
5. **Prompt Engineering for Gemini**:
   - Be specific: "Implement a rate limiter in quentin/infra/llm/client.py using a sliding window algorithm."
   - Ask for tests: "Include a unit test using pytest."
   - Enforce style: "Follow PEP8 and use type hints."
6. **Review & Apply**: The tool returns the code. Review it before writing to disk using `fs.write_file`.
7. **Verify**: Always run `pytest` or similar verification after applying the code.

## Example
```json
{
  "name": "gemini.code",
  "args": {
    "prompt": "Fix the recursion depth error in quentin/planning/hierarchical_planner.py. Add a max_depth check.",
    "context_files": ["quentin/planning/hierarchical_planner.py"]
  }
}
```
