import pytest

from utu.agents.common import TaskRecorder
from utu.agents.orchestrator.chain import ChainPlanner


def test_chain_planner_parse_missing_plan_block_raises_clear_error():
    """Missing <plan> block should raise AssertionError, not AttributeError."""
    planner = object.__new__(ChainPlanner)
    recorder = TaskRecorder()
    text_without_plan = "<analysis>some analysis</analysis>\nNo plan here"

    with pytest.raises(AssertionError, match="No tasks parsed from plan"):
        planner._parse(text_without_plan, recorder)


def test_chain_planner_parse_valid_plan_block_still_works():
    """A well-formed plan block should still be parsed correctly."""
    planner = object.__new__(ChainPlanner)
    recorder = TaskRecorder()
    text = (
        "<analysis>break it down</analysis>\n"
        '<plan>[{"name": "agent_a", "task": "do a"}, {"name": "agent_b", "task": "do b"}]</plan>'
    )

    plan = planner._parse(text, recorder)

    assert plan.analysis == "break it down"
    assert len(plan.tasks) == 2
    assert plan.tasks[0].agent_name == "agent_a"
    assert plan.tasks[0].task == "do a"
    assert plan.tasks[1].agent_name == "agent_b"
    assert plan.tasks[1].task == "do b"


def test_task_recorder_input_default_is_list():
    """TaskRecorder.input should default to a list, matching its annotation."""
    recorder = TaskRecorder()

    assert recorder.input == []
    assert isinstance(recorder.input, list)
