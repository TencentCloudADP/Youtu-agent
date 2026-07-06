import os

os.environ.setdefault("UTU_LLM_TYPE", "openai")
os.environ.setdefault("UTU_LLM_MODEL", "gpt-4o-mini")

import pytest

from utu.agents.common import TaskRecorder
from utu.agents.orchestrator.chain import ChainPlanner
from utu.agents.orchestrator.common import Recorder


def test_chain_planner_parse_missing_plan_block_raises_clear_assertion() -> None:
    planner = ChainPlanner.__new__(ChainPlanner)
    recorder = Recorder(input="question")

    with pytest.raises(AssertionError, match="No tasks parsed from plan"):
        planner._parse("<analysis>ok</analysis>", recorder)


def test_chain_planner_parse_still_extracts_tasks_from_valid_plan() -> None:
    planner = ChainPlanner.__new__(ChainPlanner)
    recorder = Recorder(input="question")

    plan = planner._parse(
        '<analysis>ok</analysis><plan>[{"name": "agent-a", "task": "do work"}]</plan>',
        recorder,
    )

    assert plan.analysis == "ok"
    assert len(plan.tasks) == 1
    assert plan.tasks[0].agent_name == "agent-a"
    assert plan.tasks[0].task == "do work"
    assert plan.tasks[0].is_last_task is True


def test_task_recorder_input_defaults_to_list() -> None:
    recorder = TaskRecorder()

    assert recorder.input == []
    assert isinstance(recorder.input, list)
