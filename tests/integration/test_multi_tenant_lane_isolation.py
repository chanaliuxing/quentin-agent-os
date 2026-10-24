import pytest
import asyncio
from quentin.infra.concurrency.lane_orchestrator import LaneOrchestrator

@pytest.mark.asyncio
async def test_lane_policy_quota():
    orchestrator = LaneOrchestrator()
    tenant_id = "test_tenant"
    
    # Set a low quota
    orchestrator.policy.update_quota(tenant_id, max_concurrency=1)
    
    async def slow_task():
        await asyncio.sleep(0.1)
        return "done"

    # First task should acquire slot
    task1 = asyncio.create_task(orchestrator.run_in_lane("session1", slow_task, tenant_id=tenant_id))
    
    # Wait a bit to ensure task1 has acquired the slot
    await asyncio.sleep(0.01)
    
    # Second task should fail due to quota
    with pytest.raises(RuntimeError, match="quota exceeded"):
        await orchestrator.run_in_lane("session2", slow_task, tenant_id=tenant_id)
        
    await task1

@pytest.mark.asyncio
async def test_global_circuit_breaker():
    orchestrator = LaneOrchestrator()
    orchestrator.policy.global_circuit_breaker_threshold = 1
    
    async def slow_task():
        await asyncio.sleep(0.1)
        return "done"

    # First task should pass
    task1 = asyncio.create_task(orchestrator.run_in_lane("s1", slow_task, tenant_id="t1"))
    await asyncio.sleep(0.01)
    
    # Second task (different tenant) should fail due to global circuit breaker
    with pytest.raises(RuntimeError, match="quota exceeded"):
        await orchestrator.run_in_lane("s2", slow_task, tenant_id="t2")
        
    await task1
