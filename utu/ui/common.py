from typing import Any, Literal

import agents as ag
from pydantic import BaseModel, model_validator

from utu.agents.orchestra import OrchestraStreamEvent
from utu.agents.orchestrator import OrchestratorStreamEvent
from utu.meta.simple_agent_generator import SimpleAgentGeneratedEvent
from utu.utils.log import get_logger


class UnknowEventError(Exception):
    def __init__(self, event_name: str, event_type: str):
        super().__init__(f"Unknown event name: {event_name}, event type: {event_type}")


class WorkerDescription(BaseModel):
    name: str
    desc: str
    strengths: list[str]
    weaknesses: list[str]


class OrchestraDescription(BaseModel):
    workers: list[WorkerDescription]
    planner: str
    reporter: str


class TextDeltaContent(BaseModel):
    type: Literal["reason", "tool_call", "tool_call_argument", "tool_call_output", "text"]
    delta: str
    inprogress: bool = False
    callid: str | None = None
    argument: str | None = None


class PlanItem(BaseModel):
    analysis: str
    todo: list[str]


class WorkerItem(BaseModel):
    task: str
    output: str


class ReportItem(BaseModel):
    output: str


class PlanItemOrchestrator(BaseModel):
    analysis: str
    tasks: list[str]


class TaskItemOrchestrator(BaseModel):
    agent_name: str
    task: str
    is_reporter: bool
    report: str | None = None


class OrchestraContent(BaseModel):
    type: Literal["plan", "worker", "report", "plan_start", "report_start"]
    item: PlanItem | WorkerItem | ReportItem | None = None


class ExampleContent(BaseModel):
    type: Literal["example"] = "example"
    query: str


class NewAgentContent(BaseModel):
    type: Literal["new"] = "new"
    name: str


class ListAgentsContent(BaseModel):
    type: Literal["list_agents"] = "list_agents"
    agents: list[str]


class SwitchAgentContent(BaseModel):
    type: Literal["switch_agent"] = "switch_agent"
    ok: bool
    name: str
    agent_type: Literal["simple", "orchestra", "orchestrator", "other"]
    sub_agents: list[str] | None = None


class InitContent(BaseModel):
    type: Literal["init"] = "init"
    default_agent: str
    agent_type: Literal["simple", "orchestra", "orchestrator", "other"]
    sub_agents: list[str] | None = None


class AskContent(BaseModel):
    type: Literal["ask"] = "ask"
    question: str
    ask_id: str


class GeneratedAgentContent(BaseModel):
    type: Literal["generated_agent_config"] = "generated_agent_config"
    filename: str
    config_content: str


class ErrorContent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class OrchestratorContent(BaseModel):
    """Orchestrator event"""

    type: Literal["orchestrator"] = "orchestrator"
    sub_type: Literal[
        "plan.start",  # alway with none item
        "plan.done",  # alway with plan item
        "task.start",  # alway with task item
        "task.done",  # alway with task item (with report)
    ]
    item: PlanItemOrchestrator | TaskItemOrchestrator | None = None


class Event(BaseModel):
    type: Literal[
        "raw",
        "init",
        "orchestra",
        "orchestrator",
        "finish",
        "example",
        "new",
        "list_agents",
        "switch_agent",
        "ask",
        "gen_agent",
        "generated_agent_config",
        "error",
    ]
    data: (
        TextDeltaContent
        | OrchestraContent
        | OrchestratorContent
        | GeneratedAgentContent
        | ExampleContent
        | NewAgentContent
        | ListAgentsContent
        | SwitchAgentContent
        | InitContent
        | AskContent
        | ErrorContent
        | None
    ) = None


class UserQuery(BaseModel):
    query: str


class SwitchAgentRequest(BaseModel):
    config_file: str


class UserAnswer(BaseModel):
    answer: str
    ask_id: str


class UserRequest(BaseModel):
    type: Literal["query", "list_agents", "switch_agent", "answer", "gen_agent"]
    content: UserQuery | SwitchAgentRequest | UserAnswer | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_query(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("type") == "query" and data.get("content") is None:
            query = data.get("query")
            if query is not None:
                data = {**data, "content": {"query": query}}
        return data


async def handle_raw_stream_events(event: ag.RawResponsesStreamEvent) -> Event | None:
    def _send_delta(
        delta: str,
        type: Literal["text", "reason", "tool_call_argument", "tool_call_output"],
        inprogress: bool = True,
        allow_empty: bool = True,
    ):
        if delta != "" or allow_empty:
            event_to_send = Event(
                type="raw",
                data=TextDeltaContent(
                    type=type,
                    delta=delta,
                    inprogress=inprogress,
                ),
            )
            return event_to_send
        return None

    event_to_send = None
    if event.data.type == "response.output_text.delta":
        event_to_send = _send_delta(event.data.delta, "text", allow_empty=False)
    elif event.data.type == "response.output_text.done":
        event_to_send = _send_delta("", "text", inprogress=False)
    elif event.data.type == "response.reasoning_text.delta":
        if isinstance(event.data.delta, list):
            event.data.delta = "".join([d["text"] for d in event.data.delta])
        event_to_send = _send_delta(event.data.delta, "reason", allow_empty=False)
    elif event.data.type == "response.reasoning_summary_text.done":
        event_to_send = _send_delta("", "reason", inprogress=False)
    elif event.data.type == "response.function_call_arguments.delta":
        pass
    elif event.data.type == "response.output_item.done":
        item = event.data.item
        if item.type == "function_call":
            event_to_send = Event(
                type="raw",
                data=TextDeltaContent(
                    type="tool_call",
                    delta=item.name,
                    argument=item.arguments,
                    callid=item.call_id,
                    inprogress=True,
                ),
            )
        elif item.type == "reasoning":
            event_to_send = _send_delta("", "reason", inprogress=False)
        elif item.type == "message":
            pass
    elif event.data.type == "response.function_call_arguments.done":
        pass
    elif event.data.type == "response.output_item.added":
        item = event.data.item
        if item.type == "function_call":
            pass
        elif item.type == "reasoning":
            event_to_send = _send_delta("", "reason", inprogress=True)
        elif item.type == "message":
            event_to_send = _send_delta("", "text", inprogress=True)
        else:
            event_to_send = None
    else:
        event_to_send = None
    return event_to_send


async def handle_orchestra_events(event: OrchestraStreamEvent) -> Event | None:
    item = event.item
    if event.name == "plan":
        todo_str = []
        for subtask in item.todo:
            task_info = f"{subtask.task} ({subtask.agent_name})"
            todo_str.append(task_info)
        plan_item = PlanItem(analysis=item.analysis, todo=todo_str)
        event_to_send = Event(type="orchestra", data=OrchestraContent(type="plan", item=plan_item))
    elif event.name == "worker":
        worker_item = WorkerItem(task=item.task, output=item.output)
        event_to_send = Event(type="orchestra", data=OrchestraContent(type="worker", item=worker_item))
    elif event.name == "report":
        report_item = ReportItem(output=item.output)
        event_to_send = Event(type="orchestra", data=OrchestraContent(type="report", item=report_item))
    elif event.name == "plan_start":
        event_to_send = Event(
            type="orchestra",
            data=OrchestraContent(type="plan_start", item=None),
        )
    elif event.name == "report_start":
        event_to_send = Event(
            type="orchestra",
            data=OrchestraContent(type="report_start", item=None),
        )
    else:
        get_logger(__name__).error(f"Unknown orchestra event name: {event.name}")
        event_to_send = None
    return event_to_send


async def handle_tool_call_output(event: ag.RunItemStreamEvent) -> Event | None:
    item = event.item
    if item.type == "tool_call_output_item":
        event_to_send = Event(
            type="raw",
            data=TextDeltaContent(
                type="tool_call_output",
                delta=str(item.output),
                callid=item.raw_item["call_id"],
                inprogress=False,
            ),
        )
        return event_to_send
    return None


async def handle_new_agent(event: ag.AgentUpdatedStreamEvent) -> Event | None:
    if event.new_agent:
        if hasattr(event.new_agent, "name"):
            new_agent_name = f"{event.new_agent.name}"
        else:
            new_agent_name = event.new_agent.__class__.__name__

        event_to_send = Event(
            type="new",
            data=NewAgentContent(type="new", name=new_agent_name),
        )
    else:
        pass
    return event_to_send


async def handle_generated_agent(event: SimpleAgentGeneratedEvent) -> Event | None:
    event_to_send = Event(
        type="generated_agent_config",
        data=GeneratedAgentContent(filename=event.filename, config_content=event.config_content),
    )
    return event_to_send


async def handle_orchestrator_events(event: OrchestratorStreamEvent) -> Event | None:
    event_to_send = None
    if event.name == "plan.start":
        event_to_send = Event(
            type="orchestrator", data=OrchestratorContent(type="orchestrator", sub_type="plan.start", item=None)
        )
    elif event.name == "plan.done":
        item = PlanItemOrchestrator(
            analysis=event.item.analysis, tasks=[f"{task.task} ({task.agent_name})" for task in event.item.tasks]
        )
        event_to_send = Event(
            type="orchestrator", data=OrchestratorContent(type="orchestrator", sub_type="plan.done", item=item)
        )
    elif event.name == "task.start":
        if event.item:
            item = TaskItemOrchestrator(
                agent_name=event.item.agent_name, task=event.item.task, is_reporter=event.item.is_last_task, report=""
            )
            event_to_send = Event(
                type="orchestrator", data=OrchestratorContent(type="orchestrator", sub_type="task.start", item=item)
            )
    elif event.name == "task.done":
        if event.item:
            item = TaskItemOrchestrator(
                agent_name=event.item.agent_name,
                task=event.item.task,
                is_reporter=event.item.is_last_task,
                report=event.item.result,
            )
        else:
            item = None
        event_to_send = Event(
            type="orchestrator", data=OrchestratorContent(type="orchestrator", sub_type="task.done", item=item)
        )
    else:
        get_logger(__name__).error(f"Unknown orchestrator event name: {event.name}")
    return event_to_send
