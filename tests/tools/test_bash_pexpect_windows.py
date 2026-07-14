from unittest.mock import Mock

from utu.tools.local_env.bash_pexpect import PexpectBash


def test_start_persistent_shell_uses_popen_spawn_on_windows(monkeypatch):
    child = Mock()
    spawn = Mock(return_value=child)
    monkeypatch.setattr("utu.tools.local_env.bash_pexpect.sys.platform", "win32")
    monkeypatch.setattr(PexpectBash, "_spawn_windows_shell", spawn)

    result, prompt = PexpectBash.start_persistent_shell(timeout=12)

    spawn.assert_called_once_with(12)
    child.sendline.assert_called_once_with("prompt PROMPT_$G")
    child.expect.assert_called_once_with("PROMPT_>")
    assert result is child
    assert prompt == "PROMPT_>"
