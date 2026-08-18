import json
import re

from ...config import AgentConfig, ConfigLoader
from ...utils import AgentsUtils, FileUtils, get_logger
from ..common import DataClassWithStreamEvents
from ..llm_agent import LLMAgent
from ..simple_agent import SimpleAgent
from .common import OrchestratorStreamEvent, Plan, Recorder, Task

logger = get_logger(__name__)


class ChainPlanner:
    """Task planner that handles task decomposition."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.prompts = FileUtils.load_prompts("agents/orchestrator/chain.yaml")

        if config.orchestrator_router is None:  # set default
            config.orchestrator_router = ConfigLoader.load_agent_config("orchestrator/router")
        self.router = SimpleAgent(config=config.orchestrator_router)

        examples_path = self.config.orchestrator_config.get("examples_path", "plan_examples/chain.json")
        self.planner_examples = FileUtils.load_json_data(examples_path)
        self.additional_instructions = self.config.orchestrator_config.get("additional_instructions", "")

    async def handle_input(self, recorder: Recorder) -> None | Plan:
        # handle input. return a plan
        async with self.router as router:
            input = recorder.history_messages + [{"role": "user", "content": recorder.input}]
            res = router.run_streamed(input)
            await self._process_streamed(res, recorder)
            recorder.history_messages = res.to_input_list()  # update chat history
            # add trajectory
            recorder.trajectories.append(AgentsUtils.get_trajectory_from_agent_result(res, "router"))
        need_plan = res.final_output.strip().endswith("<plan>")  # special token!
        if need_plan:
            return await self.create_plan(recorder)

    async def create_plan(self, recorder: Recorder) -> Plan:
        """Plan tasks based on the overall task and available agents."""
        # format examples to string. example: {question, available_agents, analysis, plan}
        examples_str = []
        for example in self.planner_examples:
            examples_str.append(
                f"<question>{example['question']}</question>\n"
                f"<available_agents>{example['available_agents']}</available_agents>\n"
                f"<analysis>{example['analysis']}</analysis>\n"
                f"<plan>{json.dumps(example['plan'], ensure_ascii=False)}</plan>"
            )
        examples_str = "\n".join(examples_str)
        sp = FileUtils.get_jinja_template_str(self.prompts["orchestrator_sp"]).render(planning_examples=examples_str)
        llm = LLMAgent(
            name="orchestrator",
            instructions=sp,
            model_config=self.config.orchestrator_model,
        )
        up = FileUtils.get_jinja_template_str(self.prompts["orchestrator_up"]).render(
            additional_instructions=self.additional_instructions,
            question=recorder.input,
            available_agents=self.config.orchestrator_workers_info,
            # background_info=await self._get_background_info(recorder),
        )
        if recorder.history_plan:
            input = recorder.history_plan + [{"role": "user", "content": up}]
        else:
            input = up
        recorder._event_queue.put_nowait(OrchestratorStreamEvent(name="plan.start"))
        res = llm.run_streamed(input)
        await self._process_streamed(res, recorder)
        plan = self._parse(res.final_output, recorder)
        recorder._event_queue.put_nowait(OrchestratorStreamEvent(name="plan.done", item=plan))
        # set tasks & record trajectories
        recorder.add_plan(plan)
        recorder.trajectories.append(AgentsUtils.get_trajectory_from_agent_result(res, "orchestrator"))
        return plan

    def _parse(self, text: str, recorder: Recorder) -> Plan:
        match = re.search(r"<analysis>(.*?)</analysis>", text, re.DOTALL)
        analysis = match.group(1).strip() if match else ""

        match = re.search(r"<plan>\s*\[(.*?)\]\s*</plan>", text, re.DOTALL)
        plan_content = match.group(1).strip() if match else ""
        tasks: list[Task] = []
        task_pattern = r'\{"name":\s*"([^"]+)",\s*"task":\s*"([^"]+)"\s*\}'
        task_matches = re.findall(task_pattern, plan_content, re.IGNORECASE)
        for agent_name, task_desc in task_matches:
            tasks.append(Task(agent_name=agent_name, task=task_desc))
        # check validity
        assert len(tasks) > 0, "No tasks parsed from plan"
        tasks[-1].is_last_task = True  # FIXME: polish this
        return Plan(input=recorder.input, analysis=analysis, tasks=tasks)

    async def get_next_task(self, recorder: Recorder) -> Task | None:
        """Get the next task to be executed."""
        if not recorder.tasks:
            raise ValueError("No tasks available. Please create a plan first.")
        if recorder.current_task_id >= len(recorder.tasks):
            return None
        task = recorder.tasks[recorder.current_task_id]
        recorder.current_task_id += 1
        return task

    async def _process_streamed(self, res: DataClassWithStreamEvents, recorder: Recorder):
        async for event in res.stream_events():
            recorder._event_queue.put_nowait(event)
