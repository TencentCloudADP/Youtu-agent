from os import environ
from unittest.mock import AsyncMock

environ.setdefault("UTU_LLM_TYPE", "openai")
environ.setdefault("UTU_LLM_MODEL", "test-model")

from utu.agents.orchestrator.chain import ChainPlanner
from utu.agents.orchestrator.common import Plan, Recorder, Task


class FakeRouterResult:
    def __init__(self, final_output: str, history: list, event: object):
        self.final_output = final_output
        self._history = history
        self._event = event

    async def stream_events(self):
        yield self._event

    def to_input_list(self) -> list:
        return self._history


class FakeRouter:
    def __init__(self, result: FakeRouterResult):
        self.result = result
        self.inputs = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    def run_streamed(self, input):
        self.inputs.append(input)
        return self.result


def make_planner(router: FakeRouter, create_plan: AsyncMock) -> ChainPlanner:
    planner = ChainPlanner.__new__(ChainPlanner)
    planner.router = router
    planner.create_plan = create_plan
    return planner


async def test_handle_input_records_direct_router_answer_without_creating_plan(monkeypatch):
    router_event = object()
    response_history = [{"role": "assistant", "content": "Direct answer"}]
    result = FakeRouterResult("Direct answer", response_history, router_event)
    router = FakeRouter(result)
    create_plan = AsyncMock()
    planner = make_planner(router, create_plan)
    recorder = Recorder(input="What is the answer?", history_messages=[{"role": "user", "content": "Earlier question"}])
    monkeypatch.setattr(
        "utu.agents.orchestrator.chain.AgentsUtils.get_trajectory_from_agent_result",
        lambda agent_result, agent_name: {"agent": agent_name, "output": agent_result.final_output},
    )

    plan = await planner.handle_input(recorder)

    assert plan is None
    assert recorder.final_output == "Direct answer"
    assert router.inputs == [
        [
            {"role": "user", "content": "Earlier question"},
            {"role": "user", "content": "What is the answer?"},
        ]
    ]
    assert recorder.history_messages == response_history
    assert recorder.trajectories == [{"agent": "router", "output": "Direct answer"}]
    assert recorder._event_queue.get_nowait() is router_event
    create_plan.assert_not_awaited()


async def test_handle_input_creates_plan_when_router_requests_planning(monkeypatch):
    router_event = object()
    response_history = [{"role": "assistant", "content": "I will plan first <plan>"}]
    result = FakeRouterResult("I will plan first <plan>", response_history, router_event)
    router = FakeRouter(result)
    expected_plan = Plan(input="Complete this task", tasks=[Task(agent_name="worker", task="Do work")])
    create_plan = AsyncMock(return_value=expected_plan)
    planner = make_planner(router, create_plan)
    recorder = Recorder(input="Complete this task")
    monkeypatch.setattr(
        "utu.agents.orchestrator.chain.AgentsUtils.get_trajectory_from_agent_result",
        lambda agent_result, agent_name: {"agent": agent_name, "output": agent_result.final_output},
    )

    plan = await planner.handle_input(recorder)

    assert plan is expected_plan
    assert recorder.final_output is None
    assert recorder.history_messages == response_history
    assert recorder.trajectories == [{"agent": "router", "output": "I will plan first <plan>"}]
    assert recorder._event_queue.get_nowait() is router_event
    create_plan.assert_awaited_once_with(recorder)
