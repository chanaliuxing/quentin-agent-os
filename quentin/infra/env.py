from pathlib import Path

def get_project_root() -> Path:
    """
    返回整个 Project Quentin 仓库的根目录。
    默认以当前文件往上两级为 project root：
    quentin/infra/env.py → quentin/ → repo root
    """
    return Path(__file__).resolve().parents[2]
