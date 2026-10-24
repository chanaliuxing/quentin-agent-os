"""
可被自编程引擎修改的通用技能。
- 这里可以写一些 prompt 优化器、日志分析等。
- 将来 PatchCandidate 就会针对这里生成 diff。
"""

def simple_summarizer(params: dict) -> str:
    text = params.get("text", "")
    return text[:200]
