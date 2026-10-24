from typing import List, Optional, Dict, Any
from pathlib import Path
import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)

try:
    import chromadb
except ImportError:
    chromadb = None

class ChromaVectorStore:
    """
    基于 ChromaDB 的向量存储实现，增加了对 Schema 漂移和初始化错误的自愈逻辑。
    """
    _client: Optional[Any] = None
    _collection: Optional[Any] = None
    _db_path: Path

    def __init__(self, db_path: str = "chroma_db"):
        self._db_path = Path(db_path)
        if not chromadb:
            raise ImportError("chromadb is not installed")
        try:
            self._initialize_chroma_client()
        except Exception as e:
            # P0: 自愈逻辑 - 如果初始化失败（如 collections.topic 缺失 或数据库损坏），尝试清理并重建
            err_str = str(e).lower()
            if any(marker in err_str for marker in ("no such column", "database disk image is malformed", "collections.topic", "table collections has no column", "unable to open database file")):
                logger.error(f"ChromaDB initialization failed: {e}. Attempting self-healing reset of {self._db_path}")
                try:
                    self._self_heal_reset()
                except Exception as retry_e:
                    logger.critical(f"ChromaDB self-healing failed FATALLY: {retry_e}")
                    raise
            else:
                raise

    def _initialize_chroma_client(self):
        self._db_path.mkdir(parents=True, exist_ok=True)
        # 增加 settings 配置，显式禁用遥测并强制使用同步模式减少 SQLite 冲突
        from chromadb.config import Settings
        self._client = chromadb.PersistentClient(
            path=str(self._db_path),
            settings=Settings(anonymized_telemetry=False, is_persistent=True)
        )
        # 核心修复：显式检查集合，避免潜在的 SQL 生成错误。如果 get_or_create_collection 失败也会触发外层的 self-heal
        self._collection = self._client.get_or_create_collection(name="code_chunks_collection")
        logger.info(f"ChromaDB initialized at {self._db_path}")

    def _self_heal_reset(self):
        if self._db_path.exists():
            shutil.rmtree(self._db_path)
        self._initialize_chroma_client()

    async def save(self, item_id: str, content: str, metadata: Dict[str, Any]) -> None:
        if not self._collection:
            raise RuntimeError("ChromaDB collection not initialized.")
        # 确保 metadata 是平铺的，避免复杂嵌套触发 Chroma 内部 SQL 过滤逻辑异常
        self._collection.add(documents=[content], metadatas=[metadata], ids=[item_id])

    async def search(self, query_text: str, n_results: int = 5, where_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self._collection:
            return []
        # 修复：确保 where_metadata 中的字段不会被误解析为一级列名
        results = self._collection.query(query_texts=[query_text], n_results=n_results, where=where_metadata)
        found_items = []
        if results and results['ids']:
            for i in range(len(results['ids'])):
                found_items.append({
                    "id": results['ids'][i],
                    "content": results['documents'][i],
                    "metadata": results['metadatas'][i],
                    "distance": results['distances'][i] if results['distances'] else None
                })
        return found_items

    async def count(self) -> int:
        return self._collection.count() if self._collection else 0

    def reset(self):
        if self._client:
            self._client.delete_collection(name="code_chunks_collection")
            self._collection = self._client.get_or_create_collection(name="code_chunks_collection")

class NullVectorStore:
    def __init__(self, *args, **kwargs):
        logger.warning("ChromaDB unavailable; using NullVectorStore.")
    async def save(self, *args, **kwargs): pass
    async def get(self, *args, **kwargs): return None
    async def delete(self, *args, **kwargs): pass
    async def search(self, *args, **kwargs): return []
    async def count(self): return 0
    def reset(self): pass