# -*- coding: utf-8 -*-
"""
简单守护进程：周期性检查 gateway / main-app / ocr-service 健康状态，异常时自动重启对应容器。

使用方式：
    python daemon/supervisor.py
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]
CHECK_INTERVAL_SECONDS = 15
REQUEST_TIMEOUT_SECONDS = 5


@dataclass
class ServiceConfig:
    name: str
    health_url: str


SERVICES: List[ServiceConfig] = [
    ServiceConfig(name="gateway", health_url="http://127.0.0.1:9000/gateway/health"),
    ServiceConfig(name="main-app", health_url="http://127.0.0.1:8000/health"),
    ServiceConfig(name="ocr-service", health_url="http://127.0.0.1:8001/health"),
]

_running = True


def _log(msg: str) -> None:
    print(f"[daemon] {msg}", flush=True)


def _handle_stop(signum, frame) -> None:  # noqa: ANN001
    global _running
    _running = False
    _log(f"收到信号 {signum}，准备退出")


def _compose_cmd(*args: str) -> List[str]:
    return ["docker", "compose", "-f", str(ROOT_DIR / "docker-compose.yml"), *args]


def _run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )


def ensure_services_started() -> None:
    _log("启动并托管所有服务")
    result = _run_cmd(_compose_cmd("up", "-d"))
    if result.returncode != 0:
        _log(f"启动失败: {result.stderr.strip()}")
        sys.exit(1)
    _log("服务已启动")


def restart_service(service_name: str) -> None:
    _log(f"服务异常，开始重启: {service_name}")
    result = _run_cmd(_compose_cmd("restart", service_name))
    if result.returncode != 0:
        _log(f"重启失败 {service_name}: {result.stderr.strip()}")
    else:
        _log(f"重启成功: {service_name}")


def check_health(client: httpx.Client, service: ServiceConfig) -> bool:
    try:
        resp = client.get(service.health_url, timeout=REQUEST_TIMEOUT_SECONDS)
        return resp.status_code == 200
    except Exception:
        return False


def monitor_loop() -> None:
    _log(f"守护进程开始运行，检查间隔 {CHECK_INTERVAL_SECONDS}s")
    fail_count: Dict[str, int] = {svc.name: 0 for svc in SERVICES}

    with httpx.Client() as client:
        while _running:
            for svc in SERVICES:
                ok = check_health(client, svc)
                if ok:
                    if fail_count[svc.name] > 0:
                        _log(f"服务恢复: {svc.name}")
                    fail_count[svc.name] = 0
                    continue

                fail_count[svc.name] += 1
                _log(f"健康检查失败: {svc.name} (连续 {fail_count[svc.name]} 次)")

                # 连续2次失败再重启，避免偶发抖动
                if fail_count[svc.name] >= 2:
                    restart_service(svc.name)
                    fail_count[svc.name] = 0

            time.sleep(CHECK_INTERVAL_SECONDS)

    _log("守护进程已停止")


def main() -> None:
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    ensure_services_started()
    monitor_loop()


if __name__ == "__main__":
    main()
