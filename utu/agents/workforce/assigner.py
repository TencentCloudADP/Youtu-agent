import re

from ...config import AgentConfig
from ...utils import FileUtils, get_logger
from ..llm_agent import LLMAgent
from .data import Subtask, WorkspaceTaskRecorder

logger = get_logger(__name__)

PROMPTS: dict[str, str] = FileUtils.load_prompts("agents/workforce/assigner.yaml")


class AssignerAgent:
    """Task assigner that handles task assignment.

    Usage::

        assigner_agent = AssignerAgent(assigner_agent)
        assigner_response = assigner_agent.assign_task(...)
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.llm = LLMAgent(model_config=config.workforce_planner_model)

    async def assign_task(self, recorder: WorkspaceTaskRecorder) -> Subtask | None:
        """Assigns a task to a worker node with the best capability."""
        next_task = recorder.get_next_task()
        if next_task is None:
            return None

        sp = PROMPTS["TASK_ASSIGN_SYS_PROMPT"].format(
            overall_task=recorder.overall_task,
            task_plan="\n".join(recorder.formatted_task_plan_list_with_task_results),
            executor_agents_info=recorder.executor_agents_info,
        )
        up = PROMPTS["TASK_ASSIGN_USER_PROMPT"].format(
            next_task=next_task.task_name,
            executor_agents_names=recorder.executor_agents_names,
        )
        self.llm.set_instructions(sp)
        assign_recorder = await self.llm.run(up)
        recorder.add_run_result(assign_recorder.get_run_result(), "assigner")  # add assigner trajectory

        # parse assign result
        assign_result = self._parse_assign_result(assign_recorder.final_output)
        next_task.task_description = assign_result["assign_task"]
        next_task.assigned_agent = assign_result["assign_agent"]
        return next_task

    def _parse_assign_result(self, response):
        try:
            agent_match = re.search(r"<selected_agent>(.*?)</selected_agent>", response, re.DOTALL)
            selected_agent = agent_match.group(1).strip()
            task_match = re.search(r"<detailed_task_description>(.*?)</detailed_task_description>", response, re.DOTALL)
            detailed_task = task_match.group(1).strip()
            return {"assign_agent": selected_agent, "assign_task": detailed_task}
        except Exception as e:
            logger.error(f"Failed to parse assignment result: {e}")
            logger.error(f"Response content: {response}")
            raise ValueError(f"Failed to parse assignment result: {e}") from e
