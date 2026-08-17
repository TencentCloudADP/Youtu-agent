"""
- [x] feat: support multi-turn chat
- [ ] feat: add reporter
    additional instructions for the last agent! (as the reporter)
- [ ] feat: replan
- [ ] add name & description for all agent types
"""

import asyncio

from agents import trace

from ..config import AgentConfig, ConfigLoader
from ..db import DBService, TrajectoryModel
from ..utils import AgentsUtils, FileUtils, get_logger
from .common import QueueCompleteSentinel
from .orchestrator import ChainPlanner, OrchestratorStreamEvent, Recorder, Task
from .simple_agent import SimpleAgent

logger = get_logger(__name__)
PROMPTS = FileUtils.load_prompts("agents/orchestrator/chain.yaml")


class OrchestratorAgent:
    def __init__(self, config: AgentConfig):
        self._handle_config(config)

        self.orchestrator = ChainPlanner(self.config)
        self.workers = self._setup_workers()

    @property
    def name(self) -> str:
        return self.config.orchestrator_config.get("name", "BaseOrchestratorAgent")

    def _handle_config(self, config: AgentConfig) -> None:
        add_chitchat_subagent = config.orchestrator_config.get("add_chitchat_subagent", True)
        if add_chitchat_subagent:
            config.orchestrator_workers["ChitchatAgent"] = ConfigLoader.load_agent_config("simple/chitchat")
            config.orchestrator_workers_info.append(
                {
                    "name": "ChitchatAgent",
                    "description": "Engages in light, informal conversations and handles straightforward queries. Can optionally invoke search or Python tools for simple fact checks or quick calculations.",  # noqa: E501
                }
            )
        self.config = config

    def _setup_workers(self) -> dict[str, SimpleAgent]:
        # TODO: manipulate SP of agents when as workers
        workers = {}
        for name, config in self.config.orchestrator_workers.items():
            assert config.type == "simple", f"Only support SimpleAgent as worker in orchestra agent, get {config}"
            workers[name] = SimpleAgent(config=config)
        return workers

    async def run(self, input: str, history: Recorder = None, trace_id: str = None) -> Recorder:
        recorder = self.run_streamed(input, history, trace_id)
        async for _ in recorder.stream_events():
            pass
        return recorder

    def run_streamed(self, input: str, history: Recorder = None, trace_id: str = None) -> Recorder:
        trace_id = trace_id or AgentsUtils.gen_trace_id()
        if history:
            recorder = history.new(input=input, trace_id=trace_id)
        else:
            recorder = Recorder(input=input, trace_id=trace_id)
        recorder._run_impl_task = asyncio.create_task(self._start_streaming(recorder))
        return recorder

    async def _start_streaming(self, recorder: Recorder):
        with trace(workflow_name=self.name, trace_id=recorder.trace_id):
            try:
                planner = await self.orchestrator.handle_input(recorder)
                if planner:  # has a plan
                    while True:
                        task = await self.orchestrator.get_next_task(recorder)
                        if task is None:
                            logger.error("No task available! This should not happen, please check the planner!")
                            break
                        await self._run_task(recorder, task)
                        if task.is_last_task:
                            recorder.add_final_output(task.result)
                            break
                # log to db
                DBService.add(TrajectoryModel.from_task_recorder(recorder))
            except Exception as e:
                logger.error(f"Error processing task: {str(e)}")
                recorder._event_queue.put_nowait(QueueCompleteSentinel())
                recorder._is_complete = True
                raise e
            finally:
                recorder._event_queue.put_nowait(QueueCompleteSentinel())
                recorder._is_complete = True

    async def _run_task(self, recorder: Recorder, task: Task):
        worker = self.workers[task.agent_name]
        await worker.build()
        # build context for task
        task_with_context = FileUtils.get_jinja_template_str(PROMPTS["worker"]).render(
            problem=recorder.input,
            plan=recorder.get_plan_str(),
            trajectory=recorder.get_trajectory_str(),
            task=task,
        )
        # add history
        input = recorder.history_messages + [{"role": "user", "content": task_with_context}]
        # run the task
        recorder._event_queue.put_nowait(OrchestratorStreamEvent(name="task.start", item=task))
        result = await worker.run_streamed(input)
        async for event in result.stream_events():
            recorder._event_queue.put_nowait(event)
        task.result = result.final_output  # set result
        recorder._event_queue.put_nowait(OrchestratorStreamEvent(name="task.done", item=task))
        # record trajectory
        recorder.trajectories.append(AgentsUtils.get_trajectory_from_agent_result(result))
