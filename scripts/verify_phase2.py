import asyncio
import logging
import sys
import os

# 确保能导入 quentin
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.sleep.loop import SleepLoop, SleepLoopConfig

# 配置日志
logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 开始 Phase 2 验证: 智能睡眠循环")
    
    # 1. 初始化 Fabric (自动连接 DB 和 Embedding)
    # 确保你已经跑过 Phase 1，且环境变量 MEM_EMBED_PROVIDER=ollama 已设置
    # 使用 Postgres 以通过 Phase 4 验证
    fabric = MemoryFabric(use_postgres=True)
    
    # 2. 制造一些“嘈杂”的 STS 数据 (模拟 Log 碎片)
    print("\n📝 写入测试数据 (3条相似, 1条不同)...")
    base_content = "Postgres connection failed due to timeout in port 5432."
    
    # 写入 3 条相似的
    fabric.remember_atomic(f"{base_content} Retry 1.", source="test", tier=MemoryTier.STS)
    fabric.remember_atomic(f"{base_content} Retry 2.", source="test", tier=MemoryTier.STS)
    fabric.remember_atomic(f"DB Error: timeout on 5432.", source="test", tier=MemoryTier.STS)
    
    # 写入 1 条完全不同的
    fabric.remember_atomic("User requested to summarize the weather.", source="test", tier=MemoryTier.STS)
    
    print("✅ 写入完成。等待数据落盘...")
    await asyncio.sleep(1)
    
    # 3. 运行 SleepLoop
    print("\n💤 启动 SleepLoop (Intelligent Mode)...")
    config = SleepLoopConfig(
        sts_min_age_hours=0,        # 立即处理，不等待
        cluster_sim_threshold=0.8,  # 宽松一点以便聚类
        enable_llm_consolidation=True
    )
    loop = SleepLoop(memory_fabric=fabric, config=config)
    
    report = await loop.run_once()
    
    print("\n📊 运行报告:")
    print(f"  - 处理 STS 记录数: {report.processed_sts}")
    print(f"  - 生成聚类数: {report.generated_clusters}")
    print(f"  - 新增 MTS 洞察: {report.mts_created}")
    print(f"  - 归档 STS 数量: {report.sts_archived}")
    
    if report.mts_created > 0:
        print("\n✨ 验证通过! 系统成功将碎片提炼为了洞察。")
    else:
        print("\n⚠️ 验证警告: 没有生成 MTS，请检查 Embedding 服务或 LLM 连接。")

if __name__ == "__main__":
    asyncio.run(main())
