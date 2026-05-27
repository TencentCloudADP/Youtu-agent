import builtins
import importlib
import sys
from types import ModuleType


def reload_local_python_with_stubbed_ipython_without_matplotlib(monkeypatch):
    class FakeInteractiveShell:
        cleared = False

        @classmethod
        def clear_instance(cls):
            cls.cleared = True

        @classmethod
        def instance(cls, config=None):
            return cls()

        def run_cell(self, code):
            exec(code, {})

    class FakeConfig:
        def __init__(self):
            self.HistoryManager = type("HistoryManager", (), {})()

    ipython_module = ModuleType("IPython")
    ipython_core_module = ModuleType("IPython.core")
    ipython_shell_module = ModuleType("IPython.core.interactiveshell")
    ipython_shell_module.InteractiveShell = FakeInteractiveShell
    traitlets_module = ModuleType("traitlets")
    traitlets_config_module = ModuleType("traitlets.config")
    traitlets_loader_module = ModuleType("traitlets.config.loader")
    traitlets_loader_module.Config = FakeConfig

    for name, module in {
        "IPython": ipython_module,
        "IPython.core": ipython_core_module,
        "IPython.core.interactiveshell": ipython_shell_module,
        "traitlets": traitlets_module,
        "traitlets.config": traitlets_config_module,
        "traitlets.config.loader": traitlets_loader_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("matplotlib is not installed")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    sys.modules.pop("utu.tools.local_env.python", None)
    sys.modules.pop("matplotlib", None)
    sys.modules.pop("matplotlib.pyplot", None)
    return importlib.import_module("utu.tools.local_env.python")


def test_local_python_import_keeps_ipython_when_matplotlib_is_missing(monkeypatch):
    local_python = reload_local_python_with_stubbed_ipython_without_matplotlib(monkeypatch)

    assert local_python.InteractiveShell is not None
    assert local_python.Config is not None
    assert local_python.plt is None


def test_execute_python_code_without_matplotlib_when_shell_is_provided(tmp_path, monkeypatch):
    local_python = reload_local_python_with_stubbed_ipython_without_matplotlib(monkeypatch)

    shell = local_python.create_ipython_shell()
    result = local_python.execute_python_code_sync("print('ok')", str(tmp_path), shell=shell)

    assert result["success"]
    assert "ok" in result["message"]


def test_create_ipython_shell_reports_missing_ipython(monkeypatch):
    from utu.tools.local_env import python as local_python

    monkeypatch.setattr(local_python, "InteractiveShell", None)
    monkeypatch.setattr(local_python, "Config", None)

    try:
        local_python.create_ipython_shell()
    except ImportError as exc:
        assert "IPython is required" in str(exc)
    else:
        raise AssertionError("expected missing IPython to raise ImportError")
