from types import SimpleNamespace

from utu.db import TrajectoryModel


def test_from_task_recorder_records_elapsed_time(monkeypatch):
    monkeypatch.setattr("utu.db.trajectory_model.time.time", lambda: 15.0)
    recorder = SimpleNamespace(
        trace_id="trace-1",
        task="hello",
        input="",
        final_output="done",
        trajectories=[],
        started_at=10.0,
    )

    trajectory = TrajectoryModel.from_task_recorder(recorder)

    assert trajectory.time_cost == 5.0
    assert trajectory.d_input == "hello"
    assert trajectory.d_output == "done"
