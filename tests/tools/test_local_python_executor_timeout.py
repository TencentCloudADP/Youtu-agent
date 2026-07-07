import threading

import pytest


@pytest.mark.asyncio
async def test_local_python_timeout_recovers_without_leaking_executor_threads(monkeypatch, tmp_path):
    monkeypatch.setenv("UTU_LLM_TYPE", "openai")
    monkeypatch.setenv("UTU_LLM_MODEL", "dummy")

    from utu.config import ConfigLoader
    from utu.tools import PythonExecutorToolkit

    toolkit_config = ConfigLoader.load_toolkit_config("python_executor")
    toolkit_config.env_mode = "local"
    toolkit_config.config["workspace_root"] = str(tmp_path)
    toolkit = PythonExecutorToolkit(toolkit_config)

    try:
        result = await toolkit.execute_python_code("a = 41", timeout=5)
        assert result["success"]

        result = await toolkit.execute_python_code("a + 1", timeout=5)
        assert result["success"]
        assert "42" in result["message"]

        threads_before = sorted(t.name for t in threading.enumerate() if t.name.startswith("asyncio_"))
        timeout_result = await toolkit.execute_python_code("import time\ntime.sleep(10)", timeout=0.2)
        threads_after = sorted(t.name for t in threading.enumerate() if t.name.startswith("asyncio_"))

        assert not timeout_result["success"]
        assert timeout_result["error"] == "Code execution timed out (0.2 seconds)"
        assert threads_after == threads_before

        recovery_result = await toolkit.execute_python_code("print('ok')", timeout=5)
        assert recovery_result["success"]
        assert "ok" in recovery_result["message"]
    finally:
        await toolkit.cleanup()
