
import json
from pathlib import Path
from quentin.cognitive.loop_context_helpers import generate_sensing_report

class MockTask:
    def __init__(self, text):
        self.input_text = text

repo_root = Path(".").resolve()
task = MockTask("TASK: 实现一个新 的工具插件，名称为 'WebSearchTool'，用于网页搜索。 STEPS: 1. 创建目录 'extensions/tools/web_search/'。 2. 创建 'extensions/tools/web_search/manifest.yaml'。")
focus_paths = ["extensions/tools/web_search", "extensions/tools/web_search/manifest.yaml"]

report = generate_sensing_report(repo_root=repo_root, task=task, focus_paths=focus_paths)
print(json.dumps(report, indent=2))
