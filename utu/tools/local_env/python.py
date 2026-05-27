"""
- [ ] polish _execute_python_code_sync
"""

import asyncio
import base64
import contextlib
import glob
import io
import os
import re
import traceback
from typing import TYPE_CHECKING

try:
    from IPython.core.interactiveshell import InteractiveShell
    from traitlets.config.loader import Config
except ImportError:
    InteractiveShell = None
    Config = None

try:
    import matplotlib
    import matplotlib.pyplot as plt

    matplotlib.use("Agg")
except ImportError:
    plt = None

if TYPE_CHECKING:
    from IPython.core.history import HistoryManager
    from traitlets.config.loader import Config as BaseConfig

    class Config(BaseConfig):
        HistoryManager: HistoryManager


# Used to clean ANSI escape sequences
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
    if InteractiveShell is None or Config is None:
        raise ImportError("IPython is required for local python execution")

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
    This function is intended to be run in a separate thread.

    Args:
        code: Python code to execute
        workdir: Working directory for execution
        shell: Optional existing IPython shell instance to reuse
    """
    original_dir = os.getcwd()
    shell_was_passed = shell is not None  # Track if shell was passed in
    try:
        # Clean up code format
        code_clean = code.strip()
        if code_clean.startswith("```python"):
            code_clean = code_clean.split("```python")[1].split("```")[0].strip()
        code_clean = CODE_HEADER + code_clean

        # Create and change to working directory
        os.makedirs(workdir, exist_ok=True)
        os.chdir(workdir)

        # Get file list before execution
        files_before = set(glob.glob("*"))

        # Create a new IPython shell instance or reuse existing one
        if shell is None:
            if InteractiveShell is None or Config is None:
                raise ImportError("IPython is required for local python execution")

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

            if plt is not None and plt.get_fignums():
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

        stdout_result = output.getvalue()
        stderr_result = error_output.getvalue()

        stdout_result = ANSI_ESCAPE.sub("", stdout_result)
        stderr_result = ANSI_ESCAPE.sub("", stderr_result)

        files_after = set(glob.glob("*"))
        new_files = list(files_after - files_before)
        new_files = [os.path.join(workdir, f) for f in new_files]

        # Don't clear the shell instance if it was passed in (reuse mode)
        # Only clear if we created a new one
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


async def execute_python_code_async(code: str, workdir: str, timeout: int = 30, shell=None) -> dict:
    """
    Asynchronous execution of Python code.

    Args:
        code: Python code to execute
        workdir: Working directory for execution
        timeout: Execution timeout in seconds
        shell: Optional existing IPython shell instance to reuse
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,  # Use the default thread pool executor
                execute_python_code_sync,
                code,
                str(workdir),
                shell,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "status": False,
            "output": "",
            "files": [],
            "error": f"Code execution timed out ({timeout} seconds)",
        }
