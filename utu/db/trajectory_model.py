import json
import time
from typing import TYPE_CHECKING

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    from ..agents.common import TaskRecorder


class TrajectoryModel(SQLModel, table=True):
    __tablename__ = "trajectory"

    id: int | None = Field(default=None, primary_key=True)

    trace_id: str | None = Field(default=None)
    trace_url: str | None = Field(default=None)
    d_input: str | None = Field(default=None)
    d_output: str | None = Field(default=None)
    trajectories: str | None = Field(default=None)
    time_cost: float | None = Field(default=None)

    @classmethod
    def from_task_recorder(cls, task_recorder: "TaskRecorder") -> "TrajectoryModel":
        # if isinstance(task_recorder, TaskRecorder):
        d_input = getattr(task_recorder, "task", "") or getattr(task_recorder, "input", "")
        started_at = getattr(task_recorder, "started_at", None)
        time_cost = None
        if isinstance(started_at, (int, float)):
            time_cost = max(0.0, time.time() - started_at)

        return cls(
            trace_id=task_recorder.trace_id,
            trace_url="",
            d_input=d_input,
            d_output=task_recorder.final_output,
            trajectories=json.dumps(task_recorder.trajectories, ensure_ascii=False),
            time_cost=time_cost,
        )
