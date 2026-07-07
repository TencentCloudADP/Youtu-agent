"""
- [ ] polish _execute_python_code_sync
"""

import asyncio
import base64
import contextlib
import glob
import io
import json
import os
import re
import subprocess
import sys
import time
import traceback
from typing import TYPE_CHECKING

try:
    import matplotlib
    import matplotlib.pyplot as plt
    from IPython.core.interactiveshell import InteractiveShell
    from traitlets.config.loader import Config

    matplotlib.use("Agg")
except ImportError:
    pass

if TYPE_CHECKING:
    from IPython.core.history import HistoryManager
    from traitlets.config.loader import Config as BaseConfig

    class Config(BaseConfig):
        HistoryManager: HistoryManager


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
MAX_MEMORY_GB = 16
CODE_HEADER = f"""
import resource
try:
    memory_limit_bytes = {MAX_MEMORY_GB * 1024 * 1024 * 1024}
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
except (ValueError, resource.error):
    pass
"""


def create_ipython_shell():
    """
    Create a persistent IPython shell instance for reuse across multiple executions.

    Returns:
        InteractiveShell: A configured IPython shell instance
    """
    InteractiveShell.clear_instance()

    config = Config()
    config.HistoryManager.enabled = False
    config.HistoryManager.hist_file = ":memory:"

    shell = InteractiveShell.instance(config=config)

    if hasattr(shell, "history_manager"):
        shell.history_manager.enabled = False

    return shell


def cleanup_ipython_shell(shell):
    """
    Clean up an IPython shell instance.

    Args:
        shell: The IPython shell instance to clean up
    """
    if shell is None:
        return

    try:
        shell.atexit_operations = lambda: None
        if hasattr(shell, "history_manager") and shell.history_manager:
            shell.history_manager.enabled = False
            shell.history_manager.end_session = lambda: None
        InteractiveShell.clear_instance()
    except Exception:  # pylint: disable=broad-except
        pass


def execute_python_code_sync(code: str, workdir: str, shell=None):
    """
    Synchronous execution of Python code.
    This function is intended to be run in a separate worker context.

    Args:
        code: Python code to execute
        workdir: Working directory for execution
        shell: Optional existing IPython shell instance to reuse
    """
    original_dir = os.getcwd()
    shell_was_passed = shell is not None
    try:
        code_clean = code.strip()
        if code_clean.startswith("```python"):
            code_clean = code_clean.split("```python")[1].split("```")[0].strip()
        code_clean = CODE_HEADER + code_clean

        os.makedirs(workdir, exist_ok=True)
        os.chdir(workdir)

        files_before = set(glob.glob("*"))

        if shell is None:
            InteractiveShell.clear_instance()

            config = Config()
            config.HistoryManager.enabled = False
            config.HistoryManager.hist_file = ":memory:"

            shell = InteractiveShell.instance(config=config)

        if hasattr(shell, "history_manager"):
            shell.history_manager.enabled = False

        output = io.StringIO()
        error_output = io.StringIO()

        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error_output):
            shell.run_cell(code_clean)

            if plt.get_fignums():
                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format="png")
                img_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")
                plt.close()

                image_name = "output_image.png"
                counter = 1
                while os.path.exists(image_name):
                    image_name = f"output_image_{counter}.png"
                    counter += 1

                with open(image_name, "wb") as f:
                    f.write(base64.b64decode(img_base64))

        stdout_result = ANSI_ESCAPE.sub("", output.getvalue())
        stderr_result = ANSI_ESCAPE.sub("", error_output.getvalue())

        files_after = set(glob.glob("*"))
        new_files = [os.path.join(workdir, f) for f in files_after - files_before]

        if not shell_was_passed:
            try:
                shell.atexit_operations = lambda: None
                if hasattr(shell, "history_manager") and shell.history_manager:
                    shell.history_manager.enabled = False
                    shell.history_manager.end_session = lambda: None
                InteractiveShell.clear_instance()
            except Exception:  # pylint: disable=broad-except
                pass

        success = True
        if "Error" in stderr_result or ("Error" in stdout_result and "Traceback" in stdout_result):
            success = False
        message = "Code execution completed, no output"
        if stdout_result.strip():
            message = f"Code execution completed\nOutput:\n{stdout_result.strip()}"

        return {
            "workdir": workdir,
            "success": success,
            "message": message,
            "status": True,
            "files": new_files,
            "error": stderr_result.strip(),
        }
    except Exception as e:  # pylint: disable=broad-except
        return {
            "workdir": workdir,
            "success": False,
            "message": f"Code execution failed, error message:\n{str(e)},\nTraceback:{traceback.format_exc()}",
            "status": False,
            "files": [],
            "error": str(e),
        }
    finally:
        os.chdir(original_dir)


def _timeout_result(timeout: float) -> dict:
    return {
        "success": False,
        "stdout": "",
        "stderr": "",
        "status": False,
        "output": "",
        "files": [],
        "error": f"Code execution timed out ({timeout} seconds)",
    }


def _worker_failure_result(error: str) -> dict:
    return {
        "success": False,
        "stdout": "",
        "stderr": "",
        "status": False,
        "output": "",
        "files": [],
        "error": error,
    }


class PythonExecutionSession:
    """Persistent local Python session backed by a killable subprocess worker."""

    def __init__(self):
        self._process: subprocess.Popen[str] | None = None
        self._next_request_id = 0

    def _start_worker(self) -> None:
        self._process = subprocess.Popen(
            [sys.executable, "-m", "utu.tools.local_env.python_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        os.set_blocking(self._process.stdout.fileno(), False)
        os.set_blocking(self._process.stderr.fileno(), False)

    async def _stop_worker(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return

        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.write(b'{"op": "close"}\n')
                process.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass
            process.stdin.close()

        async def wait_until_exit(timeout_seconds: float) -> bool:
            deadline = time.monotonic() + timeout_seconds
            while process.poll() is None and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            return process.poll() is not None

        exited = await wait_until_exit(0.2)
        if not exited:
            process.terminate()
            exited = await wait_until_exit(1)
        if not exited:
            process.kill()
            await wait_until_exit(1)

        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()
        if process.stderr is not None and not process.stderr.closed:
            process.stderr.close()

    async def _ensure_worker(self) -> None:
        if self._process is None or self._process.poll() is not None:
            await self._stop_worker()
            self._start_worker()

    async def restart(self) -> None:
        await self._stop_worker()
        self._start_worker()

    async def close(self) -> None:
        await self._stop_worker()

    async def execute(self, code: str, workdir: str, timeout: float) -> dict:
        await self._ensure_worker()
        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        request_id = self._next_request_id
        self._next_request_id += 1
        payload = json.dumps(
            {
                "op": "execute",
                "request_id": request_id,
                "code": code,
                "workdir": str(workdir),
            }
        ).encode("utf-8")

        try:
            self._process.stdin.write(payload + b"\n")
            self._process.stdin.flush()
        except (BrokenPipeError, ValueError):
            await self.restart()
            return _worker_failure_result("Local python worker failed before it could accept the request")

        deadline = time.monotonic() + timeout
        response_buffer = bytearray()
        while True:
            if self._process.poll() is not None:
                await self.restart()
                return _worker_failure_result("Local python worker exited unexpectedly")

            try:
                chunk = os.read(self._process.stdout.fileno(), 4096)
            except BlockingIOError:
                chunk = b""

            if chunk:
                response_buffer.extend(chunk)
                if b"\n" in response_buffer:
                    response_line, _, _ = response_buffer.partition(b"\n")
                    response = json.loads(response_line.decode("utf-8"))
                    break

            if time.monotonic() >= deadline:
                await self.restart()
                return _timeout_result(timeout)

            await asyncio.sleep(0.01)
        if response.get("request_id") != request_id:
            await self.restart()
            return _worker_failure_result("Local python worker returned a mismatched response")
        return response.get("result", _worker_failure_result("Local python worker returned an empty response"))


async def create_python_execution_session() -> PythonExecutionSession:
    session = PythonExecutionSession()
    await session._ensure_worker()
    return session


async def cleanup_python_execution_session(session: PythonExecutionSession | None) -> None:
    if session is not None:
        await session.close()


async def execute_python_code_async(
    code: str,
    workdir: str,
    timeout: float = 30,
    shell=None,
    session: PythonExecutionSession | None = None,
) -> dict:
    """
    Asynchronous execution of Python code.

    Args:
        code: Python code to execute
        workdir: Working directory for execution
        timeout: Execution timeout in seconds
        shell: Optional existing IPython shell instance to reuse
        session: Optional persistent local python session backed by a subprocess worker
    """
    if session is not None:
        return await session.execute(code, workdir, timeout)

    if isinstance(shell, PythonExecutionSession):
        return await shell.execute(code, workdir, timeout)

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,
                execute_python_code_sync,
                code,
                str(workdir),
                shell,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        return _timeout_result(timeout)
