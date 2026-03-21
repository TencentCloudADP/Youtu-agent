import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from importlib import resources
from pathlib import Path

import agents as ag
import tornado.web
import tornado.websocket

from utu.agents import OrchestratorAgent
from utu.agents.orchestra import OrchestraStreamEvent
from utu.agents.orchestra_agent import OrchestraAgent
from utu.agents.orchestrator import OrchestratorStreamEvent
from utu.agents.simple_agent import SimpleAgent
from utu.config import AgentConfig
from utu.config.loader import ConfigLoader
from utu.meta.simple_agent_generator import SimpleAgentGeneratedEvent, SimpleAgentGenerator
from utu.utils import DIR_ROOT, EnvUtils

from .common import (
    AskContent,
    ErrorContent,
    Event,
    ExampleContent,
    InitContent,
    ListAgentsContent,
    SwitchAgentContent,
    SwitchAgentRequest,
    UserAnswer,
    UserQuery,
    UserRequest,
    handle_generated_agent,
    handle_new_agent,
    handle_orchestra_events,
    handle_orchestrator_events,
    handle_raw_stream_events,
    handle_tool_call_output,
)

CONFIG_PATH = DIR_ROOT / "configs" / "agents"
WORKSPACE_ROOT = "/tmp/utu_webui_workspace"


class Session:
    def __init__(self, session_id: str = None):
        if session_id is None:
            session_id = Session.gen_session_id()
        self.session_id = session_id
        self.workspace = WORKSPACE_ROOT + "/" + self.session_id
        self.init_workspace()

    @staticmethod
    def gen_session_id():
        return str(uuid.uuid4())

    def init_workspace(self):
        os.makedirs(self.workspace, exist_ok=True)

    def clean_up_workspace(self):
        os.rmdir(self.workspace)


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def initialize(self, default_config_filename: str, example_query: str = ""):
        self.default_config_filename = default_config_filename
        logging.info(f"initialize websocket, default config: {default_config_filename}")
        self.agent: SimpleAgent | OrchestraAgent | OrchestratorAgent | None = None
        self.history = None  # recorder for multi-turn chat. Now only used for OrchestraAgent
        self.default_config = None
        self.session = None
        self.example_query = example_query

    async def prepare(self):
        if self.default_config_filename:
            logging.info("instantiate default agent")
            self.default_config = ConfigLoader.load_agent_config(self.default_config_filename)
            await self.instantiate_agent(self.default_config)

        self.query_queue = asyncio.Queue()

    def create_session(self):
        session = Session()
        self.session = session
        return session

    def delete_session(self):
        session = self.session
        session.clean_up_workspace()

    def check_origin(self, origin):
        # Allow all origins to connect
        return True

    def _get_config_name(self):
        return os.path.relpath(self.default_config_filename)

    async def ask_user(self, question: str) -> str:
        event_to_send = Event(
            type="ask",
            data=AskContent(type="ask", question=question, ask_id=str(uuid.uuid4())),
        )
        await self.send_event(event_to_send)
        answer = await self.answer_queue.get()

        assert isinstance(answer, UserAnswer)
        assert answer.ask_id == event_to_send.data.ask_id
        return answer.answer

    def _get_current_agent_content(self):
        agent = self._get_config_name()
        agent_type = "simple"
        sub_agents = None
        if isinstance(self.agent, OrchestraAgent):
            agent_type = "orchestra"
            sub_agents = list(self.agent.config.workers.keys())
            sub_agents.append("PlannerAgent")
            sub_agents.append("ReporterAgent")
        elif isinstance(self.agent, OrchestratorAgent):
            agent_type = "orchestrator"
            sub_agents = [w["name"] for w in self.agent.config.orchestrator_workers_info]
        elif isinstance(self.agent, SimpleAgent):
            agent_type = "simple"
        else:
            agent_type = "other"
            if isinstance(self.agent, SimpleAgentGenerator):
                sub_agents = [
                    "clarification_agent",
                    "tool_selection_agent",
                    "instructions_generation_agent",
                    "name_generation_agent",
                ]

        return {
            "default_agent": agent,
            "agent_type": agent_type,
            "sub_agents": sub_agents,
        }

    async def open(self):
        # start query worker
        self.query_worker_task = asyncio.create_task(self.handle_query_worker())
        self.answer_queue = asyncio.Queue()

        self.create_session()

        content = self._get_current_agent_content()
        await self.send_event(Event(type="init", data=InitContent(**content)))
        if self.example_query != "":
            await self.send_event(Event(type="example", data=ExampleContent(type="example", query=self.example_query)))

    async def send_event(self, event: Event):
        logging.debug(f"Sending event: {event.model_dump()}")
        self.write_message(event.model_dump())

    async def _handle_error(self, message: str):
        await self.send_event(Event(type="error", data=ErrorContent(type="error", message=message)))
        await self.send_event(Event(type="finish"))

    async def _handle_query_noexcept(self, query: UserQuery):
        if query.query.strip() == "":
            raise ValueError("Query cannot be empty")

        if self.agent is None:
            raise RuntimeError("Agent is not initialized")

        logging.debug(f"Received query: {query.query}")

        if isinstance(self.agent, OrchestraAgent):
            stream = self.agent.run_streamed(query.query)
        elif isinstance(self.agent, SimpleAgent):
            # self.agent.input_items.append({"role": "user", "content": query.query})
            stream = self.agent.run_streamed(query.query, save=True)
        elif isinstance(self.agent, SimpleAgentGenerator):
            stream = self.agent.run_streamed(query.query)
        elif isinstance(self.agent, OrchestratorAgent):
            stream = self.agent.run_streamed(query.query, self.history)
            self.history = stream
        else:
            raise ValueError(f"Unsupported agent type: {type(self.agent).__name__}")

        async for event in stream.stream_events():
            logging.debug(f"Received event: {event}")
            event_to_send = None
            if isinstance(event, ag.RawResponsesStreamEvent):
                event_to_send = await handle_raw_stream_events(event)
            elif isinstance(event, ag.RunItemStreamEvent):
                event_to_send = await handle_tool_call_output(event)
            elif isinstance(event, ag.AgentUpdatedStreamEvent):
                event_to_send = await handle_new_agent(event)
            elif isinstance(event, OrchestraStreamEvent):
                event_to_send = await handle_orchestra_events(event)
            elif isinstance(event, SimpleAgentGeneratedEvent):
                event_to_send = await handle_generated_agent(event)
            elif isinstance(event, OrchestratorStreamEvent):
                event_to_send = await handle_orchestrator_events(event)
            else:
                pass
            if event_to_send:
                await self.send_event(event_to_send)
        event_to_send = Event(type="finish")
        logging.debug(f"Sending event: {event_to_send.model_dump()}")
        await self.send_event(event_to_send)
        if isinstance(self.agent, SimpleAgent):
            input_list = stream.to_input_list()
            self.agent.input_items = input_list
            self.agent.current_agent = stream.last_agent

    async def _handle_list_agents_noexcept(self):
        config_path = Path(CONFIG_PATH).resolve()
        example_config_files = config_path.glob("examples/*.yaml")
        simple_agent_config_files = config_path.glob("simple/*.yaml")
        orchestra_agent_config_files = config_path.glob("orchestra/*.yaml")
        orchestrator_agent_config_files = config_path.glob("orchestrator/*.yaml")
        generated_agent_config_files = config_path.glob("generated/*.yaml")

        config_files = (
            list(example_config_files)
            + list(simple_agent_config_files)
            + list(orchestra_agent_config_files)
            + list(orchestrator_agent_config_files)
            + list(generated_agent_config_files)
        )
        agents = [str(file.relative_to(config_path)) for file in config_files]
        await self.send_event(
            Event(
                type="list_agents",
                data=ListAgentsContent(type="list_agents", agents=agents),
            )
        )

    async def instantiate_agent(self, config: AgentConfig):
        print(config)
        if config.type == "simple":
            self.agent = SimpleAgent(config=config)
            await self.agent.build()
        elif config.type == "orchestrator":
            self.agent = OrchestratorAgent(config=config)
        elif config.type == "orchestra":
            # WARN: deprecated
            self.agent = OrchestraAgent(config=config)
            # await self.agent.build()
        else:
            raise ValueError(f"Unsupported agent type: {config.type}")

    async def _handle_switch_agent_noexcept(self, switch_agent_request: SwitchAgentRequest):
        config = ConfigLoader.load_agent_config(switch_agent_request.config_file)

        # set workdir for bash tool
        for key, value in config.toolkits.items():
            if key == "BashTool":
                value.config["workspace_root"] = self.session.workspace

        await self.instantiate_agent(config)
        content = self._get_current_agent_content()
        await self.send_event(
            Event(
                type="switch_agent",
                data=SwitchAgentContent(
                    type="switch_agent",
                    ok=True,
                    name=switch_agent_request.config_file,
                    agent_type=content["agent_type"],
                    sub_agents=content["sub_agents"],
                ),
            )
        )

    async def _handle_query(self, query: UserQuery):
        try:
            await self._handle_query_noexcept(query)
        except Exception as e:
            logging.error(f"Error processing query: {str(e)}")
            await self._handle_error(f"Error processing query: {str(e)}")
            logging.error(traceback.format_exc())

    async def _handle_list_agents(self):
        try:
            await self._handle_list_agents_noexcept()
        except Exception as e:
            logging.error(f"Error processing list agents: {str(e)}")
            await self._handle_error(f"Error processing list agents: {str(e)}")
            logging.error(traceback.format_exc())

    async def _handle_switch_agent(self, switch_agent_request: SwitchAgentRequest):
        try:
            await self._handle_switch_agent_noexcept(switch_agent_request)
        except Exception as e:
            logging.error(f"Error processing switch agent: {str(e)}")
            logging.error(traceback.format_exc())
            await self.send_event(
                Event(
                    type="switch_agent",
                    data=SwitchAgentContent(type="switch_agent", ok=False, name=switch_agent_request.config_file),
                )
            )

    async def _handle_answer_noexcept(self, answer: UserAnswer):
        await self.answer_queue.put(answer)

    async def _handle_answer(self, answer: UserAnswer):
        try:
            await self._handle_answer_noexcept(answer)
        except Exception as e:
            logging.error(f"Error processing answer: {str(e)}")
            await self._handle_error(f"Error processing answer: {str(e)}")
            logging.error(traceback.format_exc())

    async def _handle_gen_agent_noexcept(self):
        #!TODO (fpg2012) switch self.agent to SimpleAgentGenerator workflow
        self.agent = SimpleAgentGenerator(ask_function=self.ask_user, mode="webui")
        await self.agent.build()
        await self.send_event(Event(type="gen_agent", data=None))

    async def _handle_gen_agent(self):
        try:
            await self._handle_gen_agent_noexcept()
        except Exception as e:
            logging.error(f"Error processing gen agent: {str(e)}")
            await self._handle_error(f"Error processing gen agent: {str(e)}")
            logging.error(traceback.format_exc())

    async def handle_query_worker(self):
        while True:
            query = await self.query_queue.get()
            await self._handle_query(query)

    async def on_message(self, message: str):
        try:
            data = json.loads(message)
            print(data)
            msg_type = data.get('type')
            if msg_type == "query":
                query_str = data.get('query')
                if query_str and query_str.strip():
                    query_obj = UserQuery(query=query_str)
                    await self.query_queue.put(query_obj)
                else:
                    await self._handle_error("Query cannot be empty")
            elif msg_type == "answer":
                answer = data.get('answer')
                ask_id = data.get('ask_id')
                if answer and ask_id:
                    answer_obj = UserAnswer(answer=answer, ask_id=ask_id)
                    await self.answer_queue.put(answer_obj)
                else:
                    await self._handle_error("Invalid answer data")
            else:
                request = UserRequest(**data)
                if request.type == "list_agents":
                    await self._handle_list_agents()
                elif request.type == "switch_agent":
                    await self._handle_switch_agent(request.content)
                elif request.type == "gen_agent":
                    await self._handle_gen_agent()
                else:
                    logging.error(f"Unhandled message type: {msg_type}")
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON received: {message}")
            await self._handle_error(f"Invalid JSON received: {message}")
        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")
            await self._handle_error(f"Error processing message: {str(e)}")
            logging.error(traceback.format_exc())

    def on_close(self):
        logging.error("WebSocket closed")


class FileUploadHandler(tornado.web.RequestHandler):
    def initialize(self, workspace: str):
        self.workspace = workspace

    def set_default_headers(self):
        # Allow CORS from any origin
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")

    def options(self):
        # CORS preflight
        self.set_status(204)
        self.finish()

    def post(self):
        file = self.request.files["file"][0]
        timestamp = time.time()
        filename = f"{timestamp}_{file['filename']}"
        with open(os.path.join(self.workspace, filename), "wb") as f:
            f.write(file["body"])
        self.write({"filename": os.path.join(self.workspace, filename)})


class WebUIAgents:
    def __init__(self, default_config: str, example_query: str = ""):
        self.default_config = default_config
        self.workspace = EnvUtils.get_env("UTU_WEBUI_WORKSPACE_ROOT", WORKSPACE_ROOT)
        if not os.path.exists(self.workspace):
            os.makedirs(self.workspace)
        self.download_path = os.path.join(self.workspace, "download")
        # hack
        with resources.as_file(resources.files("utu_agent_ui.static").joinpath("index.html")) as static_dir:
            self.static_path = str(static_dir).replace("index.html", "")
        self.example_query = example_query

    def make_app(self, autoload: bool | None = None) -> tornado.web.Application:
        if autoload is None:
            autoload = EnvUtils.get_env("UTU_WEBUI_AUTOLOAD", "false") == "true"
        return tornado.web.Application(
            [
                (
                    r"/ws",
                    WebSocketHandler,
                    {"default_config_filename": self.default_config, "example_query": self.example_query},
                ),
                (
                    r"/",
                    tornado.web.RedirectHandler,
                    {"url": "/index.html"},
                ),
                (r"/upload", FileUploadHandler, {"workspace": self.workspace}),
                (
                    r"/(.*)",
                    tornado.web.StaticFileHandler,
                    {"path": self.static_path, "default_filename": "index.html"},
                ),
            ],
            debug=autoload,
        )

    async def __launch(self, port: int = 8848, ip: str = "127.0.0.1", autoload: bool | None = None):
        app = self.make_app(autoload=autoload)
        app.listen(port, address=ip)
        logging.info(f"Server started at http://{ip}:{port}/")
        await asyncio.Event().wait()

    async def launch_async(self, port: int = 8848, ip: str = "127.0.0.1", autoload: bool | None = None):
        await self.__launch(port=port, ip=ip, autoload=autoload)

    def launch(self, port: int = 8848, ip: str = "127.0.0.1", autoload: bool | None = None):
        print(f"Starting server at http://{ip}:{port}/")
        asyncio.run(self.__launch(port=port, ip=ip, autoload=autoload))


if __name__ == "__main__":
    webui = WebUIAgents()
    webui.launch()
