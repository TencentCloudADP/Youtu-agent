"""
https://github.com/pexpect/pexpect
@ii-agent/src/ii_agent/tools/bash_tool.py
"""

import re
import sys

try:
    import pexpect
except ImportError:
    pass


class PexpectBash:
    def __init__(self, timeout: int = 60):
        # self.require_confirmation = self.config.config.get("require_confirmation", False)
        # self.command_filters = self.config.config.get("command_filters", [])
        self.timeout = timeout
        self.child, self.custom_prompt = self.start_persistent_shell(timeout=self.timeout)
        self.banned_command_strs = [
            "git init",
            "git commit",
            "git add",
        ]

    @staticmethod
    def _spawn_windows_shell(timeout: int):
        """Start cmd.exe through pexpect's cross-platform subprocess backend."""
        from pexpect.popen_spawn import PopenSpawn

        return PopenSpawn("cmd.exe /Q", encoding="utf-8", timeout=timeout)

    @staticmethod
    def start_persistent_shell(timeout: int):
        # https://github.com/pexpect/pexpect/issues/321

        # Start a new Bash shell
        if sys.platform == "win32":
            child = PexpectBash._spawn_windows_shell(timeout)
            custom_prompt = "PROMPT_>"
            child.sendline("prompt PROMPT_$G")
            child.expect(custom_prompt)
        else:
            child = pexpect.spawn("/bin/bash", encoding="utf-8", echo=False, timeout=timeout)
            # Set a known, unique prompt
            # We use a random string that is unlikely to appear otherwise
            # so we can detect the prompt reliably.
            custom_prompt = "PEXPECT_PROMPT>> "
            child.sendline("stty -onlcr")
            child.sendline("unset PROMPT_COMMAND")
            child.sendline(f"PS1='{custom_prompt}'")
            # Force an initial read until the newly set prompt shows up
            child.expect(custom_prompt)
        return child, custom_prompt

    @staticmethod
    def run_command(child, custom_prompt: str, cmd: str) -> str:
        # Send the command
        child.sendline(cmd)
        # Wait until we see the prompt again
        child.expect(custom_prompt)
        # Output is everything printed before the prompt minus the command itself
        # pexpect puts the matched prompt in child.after and everything before it in child.before.

        raw_output = child.before.strip()
        ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        clean_output = ansi_escape.sub("", raw_output)

        if clean_output.startswith("\r"):
            clean_output = clean_output[1:]

        return clean_output

    def run(self, command: str) -> str:
        """Execute a bash command in your workspace and return its output."""
        # 1) filter: change command before execution. E.g. used in SSH or Docker.
        # original_command = command
        # command = self.apply_filters(original_command)
        # if command != original_command:
        #     logger.info(f"Command filtered: {original_command} -> {command}")

        # 2) banned command check
        for banned_str in self.banned_command_strs:
            if banned_str in command:
                return f"Command not executed due to banned string in command: {banned_str} found in {command}."

        # if self.require_confirmation:
        #     ...

        # confirm no bad stuff happened
        try:
            echo_result = self.run_command(self.child, self.custom_prompt, "echo hello")
            assert echo_result.strip() == "hello"
        except Exception:  # pylint: disable=broad-except
            self.child, self.custom_prompt = self.start_persistent_shell(self.timeout)

        # 3) Execute the command and capture output
        try:
            result = self.run_command(self.child, self.custom_prompt, command)
            return str(
                {
                    "command output": result,
                }
            )
        except Exception as e:  # pylint: disable=broad-except
            return str(
                {
                    "error": str(e),
                }
            )
        # TODO: add workspace tree in output
