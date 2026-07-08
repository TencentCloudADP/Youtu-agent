import asyncio
import time
import traceback
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from typing import Any

from agents import Agent, RunResult, StreamEvent, TResponseInputItem

from ..utils import AgentsUtils, get_logger

logger = get_logger(__name__)


# from agents._run_impl import QueueCompleteSentinel
class QueueCompleteSentinel:
    pass


@dataclass
class DataClassWithStreamEvents:
    _is_complete: bool = False
    _stored_exception: Exception | None = field(default=None, repr=False)

    # Queues that the background run_loop writes to
    _event_queue: asyncio.Queue[StreamEvent] = field(default_factory=asyncio.Queue, repr=False)
    # Store the asyncio tasks that we're waiting on
    _run_impl_task: asyncio.Task[Any] | None = field(default=None, repr=False)

    def cancel(self) -> None:
        """Cancels the streaming run, stopping all background tasks and marking the run as
        complete."""
        self._cleanup_tasks()  # Cancel all running tasks
        self._is_complete = True  # Mark the run as complete to stop event streaming

        # Optionally, clear the event queue to prevent processing stale events
        while not self._event_queue.empty():
            self._event_queue.get_nowait()

    async def stream_events(self) -> AsyncIterator[StreamEvent]:
        while True:
            self._check_errors()
            if self._stored_exception:
                logger.debug("Breaking due to stored exception")
                self._is_complete = True
                break

            if self._is_complete and self._event_queue.empty():
                break

            try:
                item = await self._event_queue.get()
            except asyncio.CancelledError:
                logger.debug("Breaking due to asyncio.CancelledError")
                break

            if isinstance(item, QueueCompleteSentinel):
                self._event_queue.task_done()
                # Check for errors, in case the queue was completed due to an exception
                self._check_errors()
                break

            yield item
            self._event_queue.task_done()

        self._cleanup_tasks()

        if self._stored_exception:
            raise self._stored_exception

    def _cleanup_tasks(self):
        if self._run_impl_task and not self._run_impl_task.done():
            self._run_impl_task.cancel()

    def _check_errors(self):
        # Check the tasks for any exceptions
        if self._run_impl_task and self._run_impl_task.done():
            run_impl_exc = self._run_impl_task.exception()
            if run_impl_exc and isinstance(run_impl_exc, Exception):
                # if isinstance(run_impl_exc, AgentsException) and run_impl_exc.run_data is None:
                #     run_impl_exc.run_data = self._create_error_details()
                logger.error(f"run_impl_exc: {run_impl_exc}")
                logger.error(
                    "".join(traceback.format_exception(type(run_impl_exc), run_impl_exc, run_impl_exc.__traceback__))
                )
                self._stored_exception = run_impl_exc

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if not k.startswith("_")}


@dataclass
class TaskRecorder(DataClassWithStreamEvents):
    task: str = ""
    trace_id: str = ""
    input: str | list[TResponseInputItem] = field(default_factory=dict)

    # from RunResultStreaming
    final_output: str = ""
    last_agent: Agent[Any] | None = None

    trajectories: list = field(default_factory=list)  # record agent trajectories
    raw_run_results: list[RunResult] = field(default_factory=list)

    # additional infos
    additional_infos: dict = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def to_input_list(self) -> list[TResponseInputItem]:
        return self.get_run_result().to_input_list()

    def add_run_result(self, run_result: RunResult, agent_name: str = None):
        self.raw_run_results.append(run_result)
        self.trajectories.append(
            AgentsUtils.get_trajectory_from_agent_result(run_result, agent_name or run_result.last_agent.name)
        )
        # sync with RunResultStreaming fields
        self.last_agent = run_result.last_agent
        self.final_output = run_result.final_output

    def get_run_result(self) -> RunResult:
        return self.raw_run_results[-1]

    def set_final_output(self, final_output: str):
        self.final_output = final_output

    # set additional infos. NOT USED NOW!
    def set_attr(self, key: str, value: Any):
        self.additional_infos[key] = value

    def get_attr(self, key: str) -> Any:
        return self.additional_infos.get(key)
