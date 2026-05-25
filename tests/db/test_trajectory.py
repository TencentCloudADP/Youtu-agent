# from utu.agents.common import TaskRecorder
from utu.agents import SimpleAgent
from utu.db import DBService, TrajectoryModel


async def test_traj_model():
    """Test TrajectoryModel. The recorded trajectory should be saved to db and can be visualized."""
    agent = SimpleAgent(config="simple/base")
    task_recorder = await agent.run("hello")
    trajectory = TrajectoryModel.from_task_recorder(task_recorder)
    DBService.add(trajectory)


def test_trajectory_model_uses_recorder_time_cost():
    from utu.agents.common import TaskRecorder

    recorder = TaskRecorder(task="hello", input="hello", trace_id="trace-test")
    recorder.completed_at = recorder.started_at + 2.5

    trajectory = TrajectoryModel.from_task_recorder(recorder)

    assert trajectory.time_cost == 2.5


def test_trajectory_model_leaves_unfinished_time_cost_empty():
    from utu.agents.common import TaskRecorder

    recorder = TaskRecorder(task="hello", input="hello", trace_id="trace-test")

    trajectory = TrajectoryModel.from_task_recorder(recorder)

    assert trajectory.time_cost is None
