from dataclasses import dataclass, field
from typing import Literal

from ..common import TaskRecorder


@dataclass
class Subtask:
    task_id: int
    task_name: str
    task_description: str = None
    task_status: Literal["not started", "in progress", "completed", "success", "failed", "partial success"] = (
        "not started"
    )
    task_result: str = None
    task_result_detailed: str = None
    assigned_agent: str = None

    @property
    def formatted_with_result(self) -> str:
        infos = [
            f"<task_id:{self.task_id}>{self.task_name}</task_id:{self.task_id}>",
            f"<task_status>{self.task_status}</task_status>",
        ]
        if self.task_result is not None:
            infos.append(f"<task_result>{self.task_result}</task_result>")
        return "\n".join(infos)


@dataclass
class WorkspaceTaskRecorder(TaskRecorder):
    overall_task: str = ""
    executor_agent_kwargs_list: list[dict] = field(default_factory=list)
    task_plan: list[Subtask] = field(default_factory=list)

    @property
    def executor_agents_info(self) -> str:
        """Get the executor agents info."""
        return "\n".join(
            f"- {agent_kwargs['name']}: {agent_kwargs['description']}"  # TODO: add tool infos
            for agent_kwargs in self.executor_agent_kwargs_list
        )

    @property
    def executor_agents_names(self) -> str:
        return str([agent_kwargs["name"] for agent_kwargs in self.executor_agent_kwargs_list])

    # -----------------------------------------------------------
    @property
    def formatted_task_plan_list_with_task_results(self) -> list[str]:
        """Format the task plan for display."""
        return [task.formatted_with_result for task in self.task_plan]

    @property
    def formatted_task_plan(self) -> str:
        """Format the task plan for display."""
        formatted_plan_list = []
        for task in self.task_plan:
            formatted_plan_list.append(f"{task.task_id}. {task.task_name} - Status: {task.task_status}")
        return "\n".join(formatted_plan_list)

    # -----------------------------------------------------------
    def plan_init(self, plan_list: list[Subtask]) -> None:
        self.task_plan = plan_list

    def plan_update(self, task: Subtask, updated_plan: list[str]) -> None:
        finished_tasks = self.task_plan[: task.task_id]
        new_tasks = [Subtask(task_id=task.task_id + i, task_name=t) for i, t in enumerate(updated_plan)]
        self.task_plan = finished_tasks + new_tasks

    # -----------------------------------------------------------
    @property
    def has_uncompleted_tasks(self) -> bool:
        if self.task_plan is None:
            return False
        for task in self.task_plan:
            if task.task_status == "not started":
                return True
        return False

    def get_next_task(self) -> Subtask | None:
        assert self.task_plan is not None, "No task plan available."
        for task in self.task_plan:
            if task.task_status == "not started":
                return task
        return None
