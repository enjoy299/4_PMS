"""
环境预检模块 —— 借鉴 webapp-testing skill 的 with_server.py 能力，为 06 执行阶段提供：

  1. wait_for_url_ready(url)  开跑前探测被测系统 APP_URL 是否可达（TCP 端口连通）
  2. parse_servers_config()   解析可选的本地被测服务启动配置
  3. start_configured_servers / stop_servers  需要时拉起本地 dev server，用完回收

设计原则：
  - 只用标准库（socket / subprocess / urllib.parse），不引入新依赖。
  - 向后兼容：.env 未配置新项时，行为等价于「只做一次可达性探测」，不影响远程系统测试。
"""
import socket
import subprocess
import time
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger("env_ready")


class TargetNotReadyError(RuntimeError):
    """被测系统在超时时间内始终不可达。"""


def _resolve_host_port(url: str) -> tuple[str, int]:
    """从 URL 解析主机与端口（未显式给端口时按协议推断）。"""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    if parsed.port:
        return host, parsed.port
    scheme = (parsed.scheme or "http").lower()
    return host, 443 if scheme == "https" else 80


def is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """尝试建立 TCP 连接，成功即认为端口已开放（服务在跑）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.error, ConnectionRefusedError, OSError):
        return False


def wait_for_url_ready(url: str, timeout: int = 30, interval: float = 2.0) -> bool:
    """
    轮询探测目标 URL 对应的主机端口是否可达。

    参数：
        url:      被测系统地址（如 http://localhost:3000 或远程域名）
        timeout:  最长等待秒数
        interval: 每次探测间隔秒数

    返回：
        True 表示在超时前连通；False 表示始终不可达。
    """
    host, port = _resolve_host_port(url)
    logger.info(f"环境预检：探测被测系统 {host}:{port} 是否可达（超时 {timeout}s）...")
    start = time.time()
    attempt = 0
    while time.time() - start < timeout:
        attempt += 1
        if is_port_open(host, port):
            logger.info(f"[OK] 被测系统可达：{url}（第 {attempt} 次探测）")
            return True
        logger.info(f"  第 {attempt} 次探测未连通，{interval}s 后重试...")
        time.sleep(interval)
    logger.error(f"[FAIL] 在 {timeout}s 内无法连通被测系统：{url}")
    return False


def parse_servers_config(raw: str) -> list[dict]:
    """
    解析本地服务启动配置。

    格式：多个服务用 ';;' 分隔，每个服务为 '命令::端口'。
    例： "cd backend && python server.py::3000;;cd frontend && npm run dev::5173"

    返回：[{"cmd": ..., "port": ...}, ...]；raw 为空则返回 []。
    """
    if not raw or not raw.strip():
        return []
    servers = []
    for item in raw.split(";;"):
        item = item.strip()
        if not item:
            continue
        if "::" not in item:
            logger.warning(f"服务配置缺少 '::端口'，已忽略：{item}")
            continue
        cmd, _, port_s = item.rpartition("::")
        try:
            port = int(port_s.strip())
        except ValueError:
            logger.warning(f"服务端口非数字，已忽略：{item}")
            continue
        servers.append({"cmd": cmd.strip(), "port": port})
    return servers


def start_configured_servers(raw_config: str, per_server_timeout: int = 30) -> list[subprocess.Popen]:
    """
    按配置依次拉起本地服务，每个都等待端口就绪。返回已启动的进程列表（供后续回收）。

    未配置时返回 []，不产生任何副作用。
    """
    servers = parse_servers_config(raw_config)
    if not servers:
        return []
    processes: list[subprocess.Popen] = []
    for i, srv in enumerate(servers, 1):
        logger.info(f"启动本地服务 {i}/{len(servers)}：{srv['cmd']}")
        proc = subprocess.Popen(srv["cmd"], shell=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append(proc)
        if not wait_for_url_ready(f"http://localhost:{srv['port']}",
                                  timeout=per_server_timeout, interval=1.0):
            # 启动失败，回收已起的进程后抛错
            stop_servers(processes)
            raise TargetNotReadyError(
                f"本地服务未能就绪：{srv['cmd']}（端口 {srv['port']}）"
            )
        logger.info(f"[OK] 本地服务就绪，端口 {srv['port']}")
    return processes


def stop_servers(processes: list[subprocess.Popen]):
    """回收由 start_configured_servers 启动的所有进程。"""
    if not processes:
        return
    logger.info(f"回收 {len(processes)} 个本地服务...")
    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        except Exception as e:
            logger.warning(f"回收服务进程异常：{e}")
    logger.info("所有本地服务已停止")
