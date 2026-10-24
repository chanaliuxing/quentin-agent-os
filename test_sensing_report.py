
import os
from pathlib import Path
from quentin.cognitive.loop_context_helpers import generate_sensing_report

class MockTask:
    def __init__(self, text):
        self.input_text = text

repo_root = Path(".").resolve()
task = MockTask("Implement WebSearchTool in extensions/tools/web_search/")
focus_paths = [
    "extensions/tools/web_search/",
    "extensions/tools/web_search/manifest.yaml",
    "extensions/tools/web_search/logic.py"
]

report = generate_sensing_report(repo_root=repo_root, task=task, focus_paths=focus_paths)
import json
print(json.dumps(report, indent=2))
