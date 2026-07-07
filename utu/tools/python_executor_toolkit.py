import pathlib
import uuid
from datetime import datetime

from ..config import ToolkitConfig
from ..env import ShellLocalEnv
from ..utils import get_logger
from .base import AsyncBaseToolkit, register_tool
from .local_env.python import (
    cleanup_python_execution_session,
    create_python_execution_session,
    execute_python_code_async,
)
from .utils import E2BUtils

logger = get_logger(__name__)


class PythonExecutorToolkit(AsyncBaseToolkit):
    """
    A tool for executing Python code in a sandboxed environment.
    """

    def __init__(self, config: ToolkitConfig | dict | None = None):
        super().__init__(config)
        self._python_session = None

        if self.env_mode == "local":
            self.setup_workspace()
        elif self.env_mode == "e2b":
            pass
        else:
            raise ValueError(f"Unsupported env_mode {self.env_mode} for PythonExecutorToolkit!")

    def setup_workspace(self, workspace_root: str = None):
        if self.env_mode != "local":
            logger.warning(f"PythonExecutorToolkit should not setup workspace in env_mode {self.env_mode}!")
            return
        if workspace_root is None:
            if isinstance(self.env, ShellLocalEnv):
                workspace_root = self.env.workspace
            elif "workspace_root" in self.config.config:
                workspace_root = self.config.config["workspace_root"]
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_id = str(uuid.uuid4())[:8]
                workspace_root = f"/tmp/utu/python_executor/{timestamp}_{unique_id}"
        workspace_dir = pathlib.Path(workspace_root)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root = str(workspace_root)

    async def _get_python_session(self):
        if self._python_session is None:
            self._python_session = await create_python_execution_session()
        return self._python_session

    @register_tool
    async def execute_python_code(self, code: str, timeout: int = 30) -> dict:
        """
        Executes Python code and returns the output.

        Args:
            code (str): The Python code to execute.
            timeout (int): The execution timeout in seconds. Defaults to 30.

        Returns:
            dict: A dictionary containing the execution results.
        """
        if self.env_mode == "local":
            session = await self._get_python_session()
            return await execute_python_code_async(
                code,
                self.workspace_root,
                timeout=timeout,
                session=session,
            )
        else:
            assert self.e2b_sandbox is not None, "E2B sandbox is not set up!"
            result = await self.e2b_sandbox.run_code(code, language="python", timeout=timeout)
            return E2BUtils.execution_to_str(result)

    async def cleanup(self):
        """Clean up resources including the persistent local python session."""
        await cleanup_python_execution_session(self._python_session)
        self._python_session = None
        await super().cleanup()
