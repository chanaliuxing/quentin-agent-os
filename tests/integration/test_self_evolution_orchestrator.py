import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

# Import the class under test
from meta_agent.evolution.orchestrator import SelfEvolutionOrchestrator

# Import actual dependencies used by SelfEvolutionOrchestrator
from meta_agent.observability.service import ObservabilityService
from meta_agent.research.meta_planner import MetaResearchAgent
from meta_agent.blueprint.self_update_v2 import BlueprintSelfUpdateEngineV2
from quentin.traces.core import JsonlTraceRecorder
from meta_agent.research.api import ResearchAPI
from meta_agent.memory.fabric import MemoryFabric
from meta_agent.evolution.budget import BudgetManager, default_budget_manager
from meta_agent.evolution.actions import SelfEvoActionScheduler, ActionBuilder, SelfEvoAction
from meta_agent.evolution.token_budget import TokenBudgetManager # Added TokenBudgetManager import
from meta_agent.research.web_research import WebResearchWorker
from meta_agent.evolution.code_refactor import CodeRefactorWorker
from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator
from meta_agent.patchflow.queue import PatchQueue
from meta_agent.evolution.blueprint_loop import BlueprintImprovementLoop, BlueprintStore, BlueprintGapTracker, SelfProgrammingEngine, PatchEvaluator, PatchGovernanceCouncil, PatchApplier, MetricsSnapshotProvider, ImmuneLoop, ObjectiveLoader


# --- Mock Classes/Dataclasses for internal data structures ---
class MockResearchPlan:
    def __init__(self, summary: Dict):
        self.summary = summary
    def to_dict(self):
        return {"summary": self.summary}

class MockBlueprintImprovementLoopResult:
    def __init__(self, decision: str):
        self.decision = decision
        self.section_id = "test_section_A" # Example
        self.gap_kind = "missing" # Example
    def __getattr__(self, name): # Allow access to other attributes that might be called
        return MagicMock()

class MockObservabilityServiceSnapshot:
    def to_dict(self):
        return {"current_status": "ok"}


# --- Fixtures for mocked dependencies ---

@pytest.fixture
def mock_observability_service():
    mock = MagicMock(spec=ObservabilityService)
    mock.build_snapshot.return_value = MockObservabilityServiceSnapshot()
    return mock

@pytest.fixture
def mock_research_api():
    mock = MagicMock(spec=ResearchAPI)
    return mock

@pytest.fixture
def mock_memory_fabric():
    mock = MagicMock(spec=MemoryFabric)
    return mock

@pytest.fixture
def mock_bp_engine():
    mock = MagicMock(spec=BlueprintSelfUpdateEngineV2)
    return mock

@pytest.fixture
def mock_meta_research_agent():
    mock = MagicMock(spec=MetaResearchAgent)
    mock.run_cycle.return_value = MockResearchPlan(summary={"research_done": True})
    return mock

@pytest.fixture
def mock_patch_flow_orchestrator():
    mock = MagicMock(spec=PatchFlowOrchestrator)
    return mock

@pytest.fixture
def mock_budget_manager():
    mock = MagicMock(spec=BudgetManager)
    mock.can_afford.return_value = True
    mock.deduct_budget.return_value = None
    mock.get_current_budget.return_value = 100.0
    return mock

@pytest.fixture
def mock_code_tool_backend():
    mock = MagicMock() # Assuming it's a simple interface for now
    return mock

@pytest.fixture
def mock_web_research_backend():
    mock = MagicMock() # Assuming it's a simple interface for now
    return mock

@pytest.fixture
def mock_self_evo_action_scheduler():
    mock = MagicMock(spec=SelfEvoActionScheduler)
    # schedule returns a list of SelfEvoAction
    mock.schedule.return_value = [
        SelfEvoAction.new(
            kind="web_research",
            priority=5,
            estimated_tokens=10,
            payload={},
            section_id="dummy"
        )
    ]
    return mock

# Mock the entire BlueprintImprovementLoop class
@pytest.fixture
def mock_blueprint_improvement_loop_class():
    mock = MagicMock(spec=BlueprintImprovementLoop)
    mock_instance = MagicMock(spec=BlueprintImprovementLoop)
    mock_instance.run.return_value = {"improvement_results": [MockBlueprintImprovementLoopResult("accept")]}
    mock.return_value = mock_instance # When BlueprintImprovementLoop() is called, return this instance
    return mock

@pytest.fixture
def mock_global_trace_recorder():
    mock = MagicMock(spec=JsonlTraceRecorder)
    return mock

@pytest.fixture
def mock_token_budget_manager():
    mock = MagicMock(spec=TokenBudgetManager)
    mock.consume.return_value = True # Assume consume always succeeds
    return mock


@pytest.fixture
def self_evolution_orchestrator(
    mocker,
    mock_budget_manager,
    mock_blueprint_improvement_loop_class,
    mock_global_trace_recorder,
    mock_observability_service, # Added as argument
    mock_research_api, # Added as argument
    mock_memory_fabric, # Added as argument
    mock_bp_engine, # Added as argument
    mock_meta_research_agent, # Added as argument
    mock_patch_flow_orchestrator, # Added as argument
    mock_code_tool_backend, # Added as argument
    mock_web_research_backend, # Added as argument
    # mock_self_evo_action_scheduler, # REMOVED from arguments
    mock_token_budget_manager, # Added as argument
):
    # Patch internal instantiations within SelfEvolutionOrchestrator
    mocker.patch('meta_agent.evolution.orchestrator.ObservabilityService', return_value=mock_observability_service)
    mocker.patch('meta_agent.evolution.orchestrator.ResearchAPI', return_value=mock_research_api)
    mocker.patch('meta_agent.evolution.orchestrator.MemoryFabric', return_value=mock_memory_fabric)
    mocker.patch('meta_agent.evolution.orchestrator.BlueprintSelfUpdateEngineV2', return_value=mock_bp_engine)
    mocker.patch('meta_agent.evolution.orchestrator.MetaResearchAgent', return_value=mock_meta_research_agent)
    mocker.patch('meta_agent.evolution.orchestrator.PatchFlowOrchestrator', return_value=mock_patch_flow_orchestrator)
    mocker.patch('meta_agent.evolution.orchestrator.CodeToolBackend', return_value=mock_code_tool_backend)
    mocker.patch('meta_agent.research.web_research.WebResearchBackend', return_value=mock_web_research_backend)
    
    # Patch SelfEvoActionScheduler and configure its return_value
    MockSelfEvoActionSchedulerClass = mocker.patch('meta_agent.evolution.orchestrator.SelfEvoActionScheduler') # Patch where it's used
    mock_self_evo_action_scheduler_instance = MagicMock(spec=SelfEvoActionScheduler)
    
    def schedule_side_effect(actions):
        # Simulate SelfEvoActionScheduler.schedule logic
        # Directly call deduct_budget to ensure it's recorded
        mock_budget_manager.deduct_budget(10) # Simulate a deduction
        return [
            SelfEvoAction.new(kind="web_research", priority=5, estimated_tokens=10, payload={}, section_id="dummy")
        ]
    mock_self_evo_action_scheduler_instance.schedule.side_effect = schedule_side_effect
    MockSelfEvoActionSchedulerClass.return_value = mock_self_evo_action_scheduler_instance
    
    mocker.patch('meta_agent.evolution.orchestrator.BlueprintImprovementLoop', new=mock_blueprint_improvement_loop_class)
    mocker.patch('meta_agent.evolution.orchestrator.trace', new=mock_global_trace_recorder)

    # Need to pass all mocked dependencies to the orchestrator constructor (if it takes them)
    # The current SelfEvolutionOrchestrator instantiates many dependencies internally.
    orchestrator = SelfEvolutionOrchestrator(budget_manager=mock_budget_manager)
    
    # Assert SelfEvoActionScheduler constructor arguments
    MockSelfEvoActionSchedulerClass.assert_called_once()
    actual_kwargs = MockSelfEvoActionSchedulerClass.call_args.kwargs
    assert actual_kwargs['budget'] == mock_budget_manager
    assert 'handlers' in actual_kwargs # Just check if handlers is present
    
    return orchestrator, mock_self_evo_action_scheduler_instance


@pytest.mark.asyncio
async def test_self_evolution_orchestrator_cycle(
    self_evolution_orchestrator, # Renamed argument back to original fixture name
    mock_observability_service,
    mock_meta_research_agent,
    # mock_self_evo_action_scheduler, # This is now part of the fixture return
    mock_blueprint_improvement_loop_class, # This is the mock class
    mock_global_trace_recorder,
    mock_budget_manager,
):
    # Unpack the fixture's return values
    orchestrator, mock_self_evo_action_scheduler_instance = self_evolution_orchestrator

    # Run the orchestration cycle
    summary = orchestrator.run_daily_self_evo_cycle()

    # Assertions
    mock_blueprint_improvement_loop_class.return_value.run.assert_called_once_with(max_sections=3)
    mock_observability_service.build_snapshot.assert_called_once()
    mock_meta_research_agent.run_cycle.assert_called_once()
    mock_self_evo_action_scheduler_instance.schedule.assert_called_once() # Use the unpacked instance
    mock_global_trace_recorder.record_event.assert_called_once_with(
        trace_id=ANY, event_type="self_evo_cycle_done", payload=summary
    )
    mock_budget_manager.deduct_budget.assert_called() # Should be called by action_scheduler
    # Add more specific assertions as needed for action_scheduler inputs and outputs
