import json
import sys

from .python import cleanup_ipython_shell, create_ipython_shell, execute_python_code_sync


def main() -> None:
    shell = create_ipython_shell()
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue

            operation = request.get("op")
            if operation == "close":
                break
            if operation != "execute":
                continue

            result = execute_python_code_sync(
                request["code"],
                request["workdir"],
                shell=shell,
            )
            sys.stdout.write(
                json.dumps(
                    {
                        "request_id": request["request_id"],
                        "result": result,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            sys.stdout.flush()
    finally:
        cleanup_ipython_shell(shell)


if __name__ == "__main__":
    main()
