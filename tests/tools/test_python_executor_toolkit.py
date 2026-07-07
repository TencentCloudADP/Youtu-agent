import asyncio

from utu.config import ConfigLoader
from utu.env import E2BEnv
from utu.tools import PythonExecutorToolkit

toolkit = PythonExecutorToolkit(ConfigLoader.load_toolkit_config("python_executor"))


async def test_python_executor_toolkit():
    test_code = """
import numpy as np
a = 1
a
"""
    result = await toolkit.execute_python_code(code=test_code)
    print(result)
    assert result["success"]
    assert "1" in result["message"]

    test_code_with_plot = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
y = np.sin(x)

plt.figure(figsize=(8, 6))
plt.plot(x, y, 'b-', label='sin(x)')
plt.title('Sine Function')
plt.grid(True)

print("Image generated")
"""
    result_plot = await toolkit.execute_python_code(code=test_code_with_plot)
    print(result_plot)
    assert result_plot["success"]
    assert "Image generated" in result_plot["message"]
    assert len(result_plot["files"]) == 1
    assert "output_image.png" in result_plot["files"][0]


async def test_ipython():
    toolkit_config = ConfigLoader.load_toolkit_config("python_executor")
    toolkit_config.env_mode = "local"
    toolkit = PythonExecutorToolkit(toolkit_config)

    _code = "import numpy as np\na = np.array([1, 2, 3])\na"
    result = await toolkit.execute_python_code(code=_code)
    print(result)
    assert result["success"]

    _code = "b = a + 1\nnp.sum(b)"
    result = await toolkit.execute_python_code(code=_code)
    print(result)
    assert result["success"]
    assert "9" in result["message"]


async def test_ipython_e2b():
    async with E2BEnv() as env:
        toolkit_config = ConfigLoader.load_toolkit_config("python_executor")
        toolkit_config.env_mode = "e2b"
        toolkit = PythonExecutorToolkit(toolkit_config)
        toolkit.setup_env(env)

        _code = "import numpy as np\na = np.array([1, 2, 3])\na"
        result = await toolkit.execute_python_code(code=_code)
        print(result)
        _code = "b = a + 1\nnp.sum(b)"
        result = await toolkit.execute_python_code(code=_code)
        print(result)


if __name__ == "__main__":
    asyncio.run(test_ipython())
    # asyncio.run(test_ipython_e2b())
