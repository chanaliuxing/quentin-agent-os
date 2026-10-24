# Champion Memory Stack (B + C + D)

目标：解决 1M 级别的在线检索结构性瓶颈，并让“大脑更聪明”而不是追求跑分满分。

## 架构

- B (Dual-Engine)
  - Dense: Qdrant (HNSW) 做向量检索
  - Sparse/Metadata: Postgres 做 FTS + 过滤 + 持久化
- C (Tiering)
  - online 默认走热/工作集检索（依赖 query.since、tier、importance 过滤）
  - cold fallback 可后续做异步补全（当前先保留接口与策略位点）
- D (Sparse + Rerank)
  - FTS 使用 GIN(content_tsv)（code domain 使用 `simple` config 避免英文词干）
  - 终局排序：继续使用 `quentin/memory/fabric.py` 的 RRF + alignment rerank

## 可打勾 TODO（落地顺序）

- [x] 新增 Qdrant REST client：`quentin/memory/champion/qdrant_rest.py`
- [x] 新增 Champion store：`quentin/memory/store_champion.py`
- [x] Container 支持 `QUENTIN_MEMORY_STORE=champion`
- [x] Postgres store schema 与 sqlite 对齐（domain/topic/update_policy 等）
- [x] Postgres FTS：generated `content_tsv` + GIN index；code domain 用 `simple`
- [x] 修复 Fabric 在 Postgres 下的 `decayed=0` 兼容问题（COUNT/graph-hop）
- [x] Docker compose：`docker/memory-champion/docker-compose.yml`
- [x] smoke：`scripts/run_memory_champion_smoke.py`

## 运行方式（本地）

1. 启动服务
   - `docker compose -f docker/memory-champion/docker-compose.yml up -d`
2. 跑 smoke
   - `source venv/bin/activate`
   - `export QUENTIN_MEMORY_STORE=champion`
   - `python scripts/run_memory_champion_smoke.py`

说明：compose 默认把 Postgres 映射到宿主机 `55432`（避免占用你本机已存在的 5432）。

## Benchmark

`scripts/bench_memory_intelligence.py` 已支持 `--backend champion`，并且会自动用 `QUENTIN_MEMORY_NAMESPACE` 隔离每次 run，避免重复执行把同一 collection/namespace 越跑越大导致假性超慢。

可选自动清理（防止 benchmark 遗留数据累积）：

- 清理 namespace（PG）：`--champion-cleanup`
- 同时删除对应 Qdrant collection：`--champion-cleanup --champion-drop-collection`

## 下一步（还没做，但冠军版必须做）

- [x] benchmark 支持 `backend=champion` 并隔离 bench 数据（独立 DB/collection 或自动清理）
- [x] C: 热/冷分层的明确策略（默认热=全部；可切换热=最近N天/STS+MTS）
- [x] D: 可选 reranker 插件（需要额外依赖，如 transformers；在网络受限环境下要有离线安装路径）

## C: 热/冷策略配置

通过 `QUENTIN_CHAMPION_HOT_POLICY` 控制在线热集：

- `all`：不过滤（默认）
- `recent_days`：仅最近 N 天（`QUENTIN_CHAMPION_HOT_RECENT_DAYS`，默认 90）
- `sts_mts`：仅 STS+MTS
- `sts_only`：仅 STS

冷回退：

- `QUENTIN_CHAMPION_COLD_FALLBACK_ENABLE=1`（默认）时，热查询不足 `top_k` 会自动从 PG 冷层补齐。

## D: Reranker 配置

- 关闭：`QUENTIN_CHAMPION_RERANKER=off`（默认）
- 轻量无依赖：`QUENTIN_CHAMPION_RERANKER=lexical`
- 可选 cross-encoder：`QUENTIN_CHAMPION_RERANKER=cross_encoder`

cross-encoder 依赖（可离线）：

1. 在线安装：
   - `pip install sentence-transformers torch`
2. 离线安装（wheel）：
   - `pip install /path/to/torch.whl /path/to/sentence_transformers.whl`

若 cross-encoder 依赖不可用，系统会自动回退到 lexical reranker，不会中断检索链路。
