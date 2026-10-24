import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from quentin.memory.models import MemoryRecord, MemoryTier
from quentin.memory.processors.cluster import cluster_records
from quentin.memory.processors.summarizer import Insight
from quentin.memory.sleep_loop import SleepLoop, SleepLoopConfig

# ---- 1. 测试聚类算法 (Clustering) ----
def test_cluster_logic():
    # 构造 3 个记录：A 和 B 很像，C 完全不同
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.99, 0.01, 0.0] # 与 A 相似度极高
    vec_c = [0.0, 1.0, 0.0]   # 与 A 正交
    
    recs = [
        MemoryRecord.new(MemoryTier.STS, "A", "test", vector=vec_a),
        MemoryRecord.new(MemoryTier.STS, "B", "test", vector=vec_b),
        MemoryRecord.new(MemoryTier.STS, "C", "test", vector=vec_c),
    ]
    
    # 阈值 0.9
    clusters = cluster_records(recs, similarity_threshold=0.9)
    
    assert len(clusters) == 2
    # A 和 B 应该在一个簇
    assert len(clusters[0].records) == 2 
    # C 单独一个簇
    assert len(clusters[1].records) == 1

# ---- 2. 测试 SleepLoop 主流程 (Mock LLM) ----
@pytest.mark.asyncio
async def test_sleep_loop_flow():
    # Mock 依赖
    mock_fabric = MagicMock()
    mock_fabric.get_sts_for_consolidation.return_value = [
        MemoryRecord.new(MemoryTier.STS, "Log 1", "test", vector=[1,0,0]),
        MemoryRecord.new(MemoryTier.STS, "Log 2", "test", vector=[0.99,0.01,0])
    ]
    
    # Mock Summarizer
    with patch("quentin.memory.sleep_loop.Summarizer") as MockSummarizer:
        instance = MockSummarizer.return_value
        instance.distill = AsyncMock(return_value=Insight(
            title="Summary", content="Distilled content", tags=[], relations={}
        ))
        # 假设没有重复，不需要 merge
        
        # Mock Deduplicator (返回 None 表示没找到重复)
        with patch("quentin.memory.sleep_loop.Deduplicator") as MockDedup:
            dedup_instance = MockDedup.return_value
            dedup_instance.find_duplicate.return_value = None
            
            # 运行 Loop
            loop = SleepLoop(memory_fabric=mock_fabric, config=SleepLoopConfig(sts_min_age_hours=0))
            
            # 手动注入 mock embedding client 以防报错
            loop.fabric.embedding_client = MagicMock()
            loop.fabric.embedding_client.embed_text.return_value = [0.5, 0.5, 0.0]

            report = await loop.run_once()
            
            # 断言
            assert report.processed_sts == 2
            assert report.generated_clusters == 1 # 两个相似记录聚为 1 类
            assert report.mts_created == 1        # 创建了 1 条 MTS
            
            # 验证 fabric 是否被调用写入 MTS
            mock_fabric.remember_atomic.assert_called_once()
            args, kwargs = mock_fabric.remember_atomic.call_args
            assert kwargs['content'] == "Distilled content" # 内容是提炼后的