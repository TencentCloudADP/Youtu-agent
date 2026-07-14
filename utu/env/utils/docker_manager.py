# ruff: noqa: I001
import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

import requests
from requests.exceptions import RequestException

try:
    import docker
    from docker.errors import NotFound
except ImportError:
    pass

from .port_manager import PortManager

logger = logging.getLogger(__name__)


class ContainerStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ContainerInfo:
    id: int
    container_id: str | None = None
    port: int | None = None
    mcp_url: str | None = None
    status: ContainerStatus = ContainerStatus.STOPPED
    error_msg: str | None = None


class DockerManager:
    def __init__(self, image_name: str = "env_browser_chromium:latest", num_preload: int = 0, num_max: int = -1):
        """
        image_name: env_browser_chromium:latest
            port: 9001
        num_preload: 预启动的容器数量
        num_max: 最大容器数量
        """
        self.image_name = image_name
        self.num_preload = num_preload
        self.num_max = num_max

        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Docker连接成功")
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Docker连接失败: {e}")
            raise

        self.port_manager = PortManager()
        self.containers: dict[str, ContainerInfo] = {}
        self.lock = asyncio.Lock()

    #     if num_preload > 0:
    #         asyncio.create_task(self._preload_containers())

    # async def _preload_containers(self):
    #     """预启动容器"""
    #     logger.info(f"开始预启动 {self.num_preload} 个容器")
    #     tasks = []
    #     for i in range(self.num_preload):
    #         tasks.append(self.start_container(i))

    #     results = await asyncio.gather(*tasks, return_exceptions=True)
    #     success_count = sum(1 for r in results if not isinstance(r, Exception))
    #     logger.info(f"预启动完成，成功启动 {success_count}/{self.num_preload} 个容器")

    async def start_container(self, id: str) -> dict:
        """启动一个容器. 基于id确定唯一的实例"""
        async with self.lock:
            if self.num_max > 0:
                running_count = sum(1 for c in self.containers.values() if c.status == ContainerStatus.RUNNING)
                if running_count >= self.num_max:
                    return {"success": False, "error": f"已达到最大容器数量限制: {self.num_max}", "id": id}

            if id in self.containers:
                container_info = self.containers[id]
                if container_info.status == ContainerStatus.RUNNING:
                    return {
                        "success": True,
                        "message": "容器已在运行",
                        "id": id,
                        "port": container_info.port,
                        "mcp_url": container_info.mcp_url,
                        "container_id": container_info.container_id,
                    }
                elif container_info.status == ContainerStatus.STARTING:
                    return {"success": False, "error": "容器正在启动中", "id": id}

            container_info = ContainerInfo(id=id, status=ContainerStatus.STARTING)
            self.containers[id] = container_info

            try:
                port = self.port_manager.allocate_port()
                if port is None:
                    container_info.status = ContainerStatus.ERROR
                    container_info.error_msg = "无法分配可用端口"
                    return {"success": False, "error": "无法分配可用端口", "id": id}

                container_info.port = port
                container_info.mcp_url = f"http://{self.port_manager.get_host_ip()}:{port}/mcp/"

                container_name = f"{self.image_name.split(':')[0]}_{id}"
                container = self.client.containers.run(
                    self.image_name,
                    name=container_name,
                    ports={"9001/tcp": port},
                    detach=True,
                    remove=True,  # remove on stop
                    environment={
                        "CONTAINER_ID": str(id),
                        "ENV": "local",
                    },
                )

                container_info.container_id = container.id

                # 等待服务的 /ping 端点返回 200 状态码
                ping_url = f"http://{self.port_manager.get_host_ip()}:{port}/ping"
                max_retries = 30  # 最多尝试30次
                retry_interval = 1  # 每次间隔1秒
                service_ready = False

                logger.info(f"等待容器 {id} 服务就绪，检查 {ping_url}")

                for _ in range(max_retries):
                    try:
                        response = await asyncio.to_thread(requests.get, ping_url, timeout=2)
                        if response.status_code == 200:
                            service_ready = True
                            logger.info(f"容器 {id} 服务已就绪，/ping 返回 200")
                            break
                        logger.debug(f"容器 {id} 服务未就绪，/ping 返回状态码 {response.status_code}，重试中...")
                    except RequestException as e:
                        logger.debug(f"容器 {id} 服务未就绪，连接异常: {e}，重试中...")

                    await asyncio.sleep(retry_interval)

                if service_ready:
                    container_info.status = ContainerStatus.RUNNING
                else:
                    # 服务未就绪，标记为错误状态并停止容器
                    container_info.status = ContainerStatus.ERROR
                    container_info.error_msg = "服务未能在规定时间内就绪，/ping 未返回 200 状态码"
                    try:
                        container.stop(timeout=5)
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(f"停止未就绪容器 {id} 时出错: {e}")

                    if container_info.port:
                        self.port_manager.release_port(container_info.port)
                        container_info.port = None

                    return {"success": False, "error": container_info.error_msg, "id": id}

                logger.info(f"容器 {id} 启动成功，端口: {port}, Docker ID: {container.id[:12]}")

                return {
                    "success": True,
                    "message": "容器启动成功",
                    "id": id,
                    "port": port,
                    "mcp_url": container_info.mcp_url,
                    "container_id": container.id,
                }

            except Exception as e:  # pylint: disable=broad-except
                if container_info.port:
                    self.port_manager.release_port(container_info.port)

                container_info.status = ContainerStatus.ERROR
                container_info.error_msg = str(e)

                logger.error(f"容器 {id} 启动失败: {e}")
                return {"success": False, "error": f"容器启动失败: {str(e)}", "id": id}

    async def stop_container(self, id: str) -> dict:
        """停止一个容器 (并释放资源)"""
        async with self.lock:
            if id not in self.containers:
                return {"success": False, "error": "容器不存在", "id": id}

            container_info = self.containers[id]

            if container_info.status == ContainerStatus.STOPPED:
                return {"success": True, "message": "容器已停止", "id": id}
            elif container_info.status == ContainerStatus.STOPPING:
                return {"success": False, "error": "容器正在停止中", "id": id}

            container_info.status = ContainerStatus.STOPPING

            try:
                if container_info.container_id:
                    try:
                        container = self.client.containers.get(container_info.container_id)
                        container.stop(timeout=10)
                        logger.info(f"容器 {id} 停止成功")
                    except NotFound:
                        logger.warning(f"容器 {id} 的Docker实例不存在，可能已被删除")
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(f"停止容器 {id} 时出错: {e}")

                if container_info.port:
                    self.port_manager.release_port(container_info.port)

                container_info.status = ContainerStatus.STOPPED
                container_info.container_id = None
                container_info.port = None
                container_info.error_msg = None

                return {"success": True, "message": "容器停止成功", "id": id}

            except Exception as e:  # pylint: disable=broad-except
                container_info.status = ContainerStatus.ERROR
                container_info.error_msg = str(e)

                logger.error(f"停止容器 {id} 失败: {e}")

                return {"success": False, "error": f"停止容器失败: {str(e)}", "id": id}

    async def stop_container_by_cid(self, cid: str) -> dict:
        """停止一个容器"""
        try:
            container = self.client.containers.get(cid)
            container.stop(timeout=10)
            logger.info(f"容器 {cid} 停止成功")
            return {"success": True, "message": "容器停止成功", "id": cid}
        except NotFound:
            logger.warning(f"容器 {cid} 的Docker实例不存在，可能已被删除")
            return {"success": False, "error": "容器不存在", "id": cid}
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"停止容器 {cid} 时出错: {e}")
            return {"success": False, "error": f"停止容器失败: {str(e)}", "id": cid}

    async def stop_all_by_cid(self, container_ids: list[str]) -> dict:
        """停止所有容器"""
        # 并发停止所有容器
        tasks = [self.stop_container_by_cid(cid) for cid in container_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
        logger.info(f"停止容器完成，成功停止 {success_count}/{len(container_ids)} 个")

        return {
            "success": True,
            "message": "批量停止完成",
            "total_count": len(container_ids),
            "stopped_count": success_count,
            "results": results,
        }

    async def stop_all(self) -> dict:
        """停止所有容器"""
        container_ids = list(self.containers.keys())
        if not container_ids:
            return {"success": True, "message": "没有需要停止的容器", "stopped_count": 0}

        logger.info(f"开始停止所有容器，共 {len(container_ids)} 个")

        # 并发停止所有容器
        tasks = [self.stop_container(cid) for cid in container_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
        logger.info(f"停止容器完成，成功停止 {success_count}/{len(container_ids)} 个")

        return {
            "success": True,
            "message": "批量停止完成",
            "total_count": len(container_ids),
            "stopped_count": success_count,
            "results": results,
        }

    async def find_all(self, stop=False) -> dict:
        """查找系统中运行的所有容器"""
        try:
            start_time = asyncio.get_event_loop().time()
            containers = self.client.containers.list(all=True)

            found_containers = []
            for container in containers:
                image_prefix = self.image_name.split(":")[0]
                if not self._is_our_container(container, image_prefix):
                    continue
                found_containers.append(self._extract_container_info(container))

            total_time = asyncio.get_event_loop().time() - start_time
            logger.info(f"查找完成，发现 {len(found_containers)} 个相关容器，耗时 {total_time:.2f}秒")

            if stop:
                return await self.stop_all_by_cid([c["docker_id"] for c in found_containers])

            return {
                "success": True,
                "search_time": total_time,
                "total_found": len(found_containers),
                "found_containers": found_containers,
            }

        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"查找容器时出错: {e}")
            return {"success": False, "error": f"查找容器时出错: {str(e)}"}

    def _is_our_container(self, container, image_prefix: str) -> bool:
        """判断容器是否属于我们管理的类型"""
        # 检查镜像名称
        if hasattr(container, "image") and hasattr(container.image, "tags"):
            for tag in container.image.tags:
                if tag.startswith(image_prefix):
                    return True
        # 检查容器名称模式
        if container.name and container.name.startswith(f"{image_prefix}_"):
            return True
        # 检查环境变量
        if hasattr(container, "attrs") and "Config" in container.attrs:
            env_vars = container.attrs["Config"].get("Env", [])
            for env in env_vars:
                if env.startswith("CONTAINER_ID="):
                    return True
        return False

    def _extract_container_info(self, container) -> dict:
        """提取容器信息"""
        info = {
            "docker_id": container.id,
            "name": container.name,
            "status": container.status,
            "image": container.image.tags[0] if container.image.tags else "unknown",
            "created": container.attrs.get("Created", ""),
            "ports": {},
            "environment": {},
        }
        return info

    def get_status(self, id: str) -> dict:
        """获取容器状态"""
        if id not in self.containers:
            return {"success": False, "error": "容器不存在", "id": id}

        container_info = self.containers[id]

        # 如果容器正在运行，检查Docker实例状态
        if container_info.status == ContainerStatus.RUNNING and container_info.container_id:
            try:
                container = self.client.containers.get(container_info.container_id)
                docker_status = container.status

                # 如果Docker容器实际已停止，更新状态
                if docker_status != "running":
                    container_info.status = ContainerStatus.STOPPED
                    if container_info.port:
                        self.port_manager.release_port(container_info.port)
                        container_info.port = None
                    container_info.container_id = None

            except NotFound:
                # Docker容器不存在，更新状态
                container_info.status = ContainerStatus.STOPPED
                if container_info.port:
                    self.port_manager.release_port(container_info.port)
                    container_info.port = None
                container_info.container_id = None
            except Exception as e:  # pylint: disable=broad-except
                logger.error(f"检查容器 {id} 状态时出错: {e}")

        return {
            "success": True,
            "id": id,
            "status": container_info.status.value,
            "port": container_info.port,
            "container_id": container_info.container_id,
            "error_msg": container_info.error_msg,
        }

    def get_all_status(self) -> dict:
        """获取所有容器状态"""
        statuses = {}
        for cid in self.containers:
            statuses[cid] = self.get_status(cid)

        return {"success": True, "total_count": len(self.containers), "containers": statuses}

    def cleanup(self):
        """清理资源"""
        logger.info("开始清理Docker管理器资源")

        # 停止所有容器
        for container_info in self.containers.values():
            if container_info.status == ContainerStatus.RUNNING and container_info.container_id:
                try:
                    container = self.client.containers.get(container_info.container_id)
                    container.stop(timeout=5)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(f"清理容器时出错: {e}")

            # 释放端口
            if container_info.port:
                self.port_manager.release_port(container_info.port)

        self.containers.clear()
        logger.info("Docker管理器资源清理完成")
