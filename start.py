#!/usr/bin/env python
"""
身体健康智慧问答助手 - 启动管理脚本

用法：
    python start.py         启动前后端
    python start.py init    初始化项目（安装依赖）
    python start.py start   启动前后端
    python start.py stop    停止前后端
    python start.py status  查看服务状态
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PYTHON = BACKEND / "venv" / "Scripts" / "python.exe"
VENV_PIP = BACKEND / "venv" / "Scripts" / "pip.exe"

BACKEND_PORT = 8000
FRONTEND_PORT = 3000


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_pid_on_port(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"], encoding="utf-8", errors="ignore"
        )
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                return int(parts[-1])
    except Exception:
        pass
    return None


def kill_port(port: int):
    pid = get_pid_on_port(port)
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        print(f"  已停止端口 {port} 上的进程 (PID={pid})")
    else:
        print(f"  端口 {port} 无运行中的进程")


def check_python():
    print("[检查] Python 环境...")
    try:
        v = sys.version_info
        print(f"  Python {v.major}.{v.minor}.{v.micro}")
        if v < (3, 10):
            print("  [警告] 建议使用 Python 3.10+")
        return True
    except Exception:
        print("  [错误] Python 不可用")
        return False


def check_node():
    print("[检查] Node.js 环境...")
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  Node.js {r.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    print("  [错误] 未检测到 Node.js，请先安装 Node.js 18+")
    return False


def init_venv():
    if VENV_PYTHON.exists():
        print("[1/4] 虚拟环境已存在，跳过创建")
        return True
    print("[1/4] 创建后端虚拟环境...")
    r = subprocess.run([sys.executable, "-m", "venv", str(BACKEND / "venv")], cwd=BACKEND)
    if r.returncode != 0:
        print("  [错误] 创建虚拟环境失败")
        return False
    print("  虚拟环境创建成功")
    return True


def install_backend_deps():
    print("[2/4] 安装后端依赖...")
    subprocess.run([str(VENV_PIP), "install", "--upgrade", "pip"], cwd=BACKEND, capture_output=True)
    r = subprocess.run(
        [str(VENV_PIP), "install", "-r", "requirements.txt"],
        cwd=BACKEND,
    )
    if r.returncode != 0:
        print("  [错误] 安装 requirements.txt 失败")
        return False
    print("  后端依赖安装完成")
    return True


def install_hertz_deps():
    hertz_txt = BACKEND / "hertz.txt"
    if not hertz_txt.exists():
        print("[3/4] 未找到 hertz.txt，跳过")
        return True
    print("[3/4] 安装 Hertz 官方依赖...")
    r = subprocess.run(
        [
            str(VENV_PIP), "install", "-r", "hertz.txt",
            "-i", "https://hertz:hertz@hzpypi.hzsystems.cn/simple/",
        ],
        cwd=BACKEND,
    )
    if r.returncode != 0:
        print("  [错误] 安装 Hertz 依赖失败，请确认机器码已激活或网络可访问")
        return False
    print("  Hertz 依赖安装完成")
    return True


def install_frontend_deps():
    print("[4/4] 安装前端依赖...")
    if not (FRONTEND / "package.json").exists():
        print("  [错误] 未找到 frontend/package.json")
        return False
    r = subprocess.run(["npm", "install"], cwd=FRONTEND)
    if r.returncode != 0:
        print("  [错误] 前端依赖安装失败")
        return False
    print("  前端依赖安装完成")
    return True


def cmd_init(args):
    print("=" * 50)
    print("身体健康智慧问答助手 - 初始化项目")
    print("=" * 50)

    if not check_python():
        return
    check_node()

    if not init_venv():
        return
    if not install_backend_deps():
        return
    if not install_hertz_deps():
        return
    if not install_frontend_deps():
        return

    print("\n" + "=" * 50)
    print("初始化完成！运行 python start.py start 启动系统")
    print("=" * 50)


def cmd_start(args):
    print("=" * 50)
    print("身体健康智慧问答助手 - 启动系统")
    print("=" * 50)

    if not VENV_PYTHON.exists():
        print("[错误] 虚拟环境未初始化，请先运行: python start.py init")
        return

    if not (FRONTEND / "node_modules").exists():
        print("[错误] 前端依赖未安装，请先运行: python start.py init")
        return

    managed_processes: list[tuple[str, subprocess.Popen]] = []

    if is_port_in_use(BACKEND_PORT):
        pid = get_pid_on_port(BACKEND_PORT)
        print(f"[提示] 端口 {BACKEND_PORT} 已被占用，未启动后端新进程 (PID={pid or '未知'})")
    else:
        print(f"启动后端: http://127.0.0.1:{BACKEND_PORT}")
        backend_proc = subprocess.Popen(
            [str(VENV_PYTHON), "start_server.py", "--port", str(BACKEND_PORT)],
            cwd=BACKEND,
        )
        managed_processes.append(("后端", backend_proc))

    if is_port_in_use(FRONTEND_PORT):
        pid = get_pid_on_port(FRONTEND_PORT)
        print(f"[提示] 端口 {FRONTEND_PORT} 已被占用，未启动前端新进程 (PID={pid or '未知'})")
    else:
        print(f"启动前端: http://127.0.0.1:{FRONTEND_PORT}")
        frontend_proc = subprocess.Popen(
            [
                "npm.cmd" if sys.platform.startswith("win") else "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(FRONTEND_PORT),
            ],
            cwd=FRONTEND,
        )
        managed_processes.append(("前端", frontend_proc))

    if not managed_processes:
        print("\n未启动新的本项目进程。请确认 8000/3000 是否已被本项目占用。")
        print("可运行 python start.py status 查看占用 PID。")
        print("=" * 50)
        return

    url = f"http://127.0.0.1:{FRONTEND_PORT}"
    print("\n服务启动中，日志会持续显示在当前终端。")
    print(f"前端地址: {url}")
    print("按 Ctrl+C 停止本次启动的前后端进程。")
    print("=" * 50)

    # 给 Vite/Daphne 一点启动时间后打开浏览器；主进程继续留在终端接管 Ctrl+C。
    time.sleep(2)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        while True:
            alive = []
            for name, proc in managed_processes:
                code = proc.poll()
                if code is None:
                    alive.append((name, proc))
                else:
                    print(f"[退出] {name} 进程已退出，退出码={code}")
            managed_processes = alive
            if not managed_processes:
                print("所有由本次 start.py 启动的进程都已退出。")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在停止本次启动的项目进程...")
        for name, proc in managed_processes:
            if proc.poll() is not None:
                continue
            if sys.platform.startswith("win"):
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                )
            else:
                proc.terminate()
            print(f"  已请求停止{name}进程 (PID={proc.pid})")
        print("已停止本次启动的项目进程。")


def cmd_stop(args):
    print("=" * 50)
    print("身体健康智慧问答助手 - 停止系统")
    print("=" * 50)
    kill_port(BACKEND_PORT)
    kill_port(FRONTEND_PORT)
    print("已停止。")


def cmd_status(args):
    print("服务状态：")
    for name, port in [("后端", BACKEND_PORT), ("前端", FRONTEND_PORT)]:
        pid = get_pid_on_port(port)
        if pid:
            print(f"  {name}: 运行中 (端口={port}, PID={pid})")
        else:
            print(f"  {name}: 未运行 (端口={port})")


def main():
    parser = argparse.ArgumentParser(
        description="身体健康智慧问答助手 - 启动管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="初始化项目（安装依赖）")
    sub.add_parser("start", help="启动前后端服务")
    sub.add_parser("stop", help="停止前后端服务")
    sub.add_parser("status", help="查看服务状态")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
    }

    command = args.command or "start"
    if command in commands:
        commands[command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
