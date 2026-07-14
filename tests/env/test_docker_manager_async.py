import asyncio
import threading

import pytest

from utu.env.utils import docker_manager
from utu.env.utils.docker_manager import DockerManager


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeContainer:
    id = "container-id-123456"


class FakeContainers:
    def run(self, *args, **kwargs):
        return FakeContainer()


class FakeClient:
    containers = FakeContainers()


class FakePortManager:
    def allocate_port(self) -> int:
        return 9002

    def get_host_ip(self) -> str:
        return "127.0.0.1"


@pytest.mark.asyncio
async def test_start_container_readiness_check_does_not_block_event_loop(monkeypatch):
    manager = DockerManager.__new__(DockerManager)
    manager.image_name = "test:latest"
    manager.num_preload = 0
    manager.num_max = -1
    manager.client = FakeClient()
    manager.port_manager = FakePortManager()
    manager.containers = {}
    manager.lock = asyncio.Lock()

    probe_started = threading.Event()
    allow_probe_to_finish = threading.Event()
    probe_observed_event_loop_progress = []
    probe_count = 0

    def get(_url, timeout):
        nonlocal probe_count
        assert timeout == 2
        probe_count += 1
        if probe_count == 1:
            probe_started.set()
            probe_observed_event_loop_progress.append(allow_probe_to_finish.wait(timeout=1))
            return FakeResponse(503)
        return FakeResponse(200)

    original_sleep = asyncio.sleep
    retry_delays = []

    async def sleep(delay):
        retry_delays.append(delay)
        await original_sleep(0)

    async def mark_event_loop_progress():
        while not probe_started.is_set():
            await original_sleep(0)
        allow_probe_to_finish.set()

    monkeypatch.setattr(docker_manager.requests, "get", get)
    monkeypatch.setattr(docker_manager.asyncio, "sleep", sleep)

    progress_task = asyncio.create_task(mark_event_loop_progress())
    result = await manager.start_container("test")
    await progress_task

    assert result["success"] is True
    assert probe_observed_event_loop_progress == [True]
    assert retry_delays == [1]
