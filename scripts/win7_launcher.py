#!/usr/bin/env python3
"""Win7-compatible local launcher for the packaged ProcessMind app."""

from __future__ import print_function

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Callable, Dict, Mapping, Optional, Sequence
from urllib.request import urlopen


HOST = "127.0.0.1"
DEFAULT_PORT = 8000
STATE_FILE_NAME = "processmind-win7.json"


class LauncherError(Exception):
    """An expected launcher failure that can be shown without a traceback."""


def package_root_from_file() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_runtime_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    values = os.environ if env is None else env
    configured = (values.get("PROCESSMIND_RUNTIME_DIR") or "").strip()
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured))).resolve()

    local_app_data = (values.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        return (Path(os.path.expandvars(os.path.expanduser(local_app_data))) / "ProcessMind").resolve()

    temporary = (values.get("TEMP") or values.get("TMP") or "").strip()
    if temporary:
        return (Path(os.path.expandvars(os.path.expanduser(temporary))) / "ProcessMind").resolve()

    user_profile = (values.get("USERPROFILE") or "").strip()
    if user_profile:
        return (
            Path(os.path.expandvars(os.path.expanduser(user_profile)))
            / "AppData"
            / "Local"
            / "ProcessMind"
        ).resolve()

    raise LauncherError(
        "PROCESSMIND_RUNTIME_DIR、LOCALAPPDATA、TEMP、TMP 和 USERPROFILE 均未指向可写运行时目录"
    )


def ensure_runtime_dir(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        with probe.open("a", encoding="utf-8"):
            pass
        probe.unlink()
    except (OSError, IOError) as exc:
        raise LauncherError("运行时目录不可写: %s" % exc)
    return path


def state_path(state_dir: Path) -> Path:
    return Path(state_dir).resolve() / STATE_FILE_NAME


def read_state(state_dir: Path) -> Optional[Dict[str, object]]:
    path = state_path(state_dir)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, IOError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_state(state_dir: Path, state: Mapping[str, object]) -> Path:
    state_dir = ensure_runtime_dir(state_dir)
    path = state_path(state_dir)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(dict(state), stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(str(temporary), str(path))
    return path


def remove_state(state_dir: Path) -> None:
    try:
        state_path(state_dir).unlink()
    except OSError:
        pass


def validate_port(port: object) -> int:
    try:
        value = int(port)
    except (TypeError, ValueError):
        raise LauncherError("端口必须是整数")
    if not 1 <= value <= 65535:
        raise LauncherError("端口必须在 1 到 65535 之间")
    return value


def check_port(host: str, port: object, timeout: float = 0.4) -> int:
    """Return 0 when free, 1 when listening, and 2 for an invalid port."""

    try:
        value = validate_port(port)
    except LauncherError:
        return 2
    try:
        with socket.create_connection((host, value), timeout=timeout):
            return 1
    except (socket.timeout, socket.error, OSError):
        return 0


def health(url: str, timeout: float = 2.0) -> bool:
    try:
        response = urlopen(url, timeout=timeout)
        try:
            status = getattr(response, "status", response.getcode())
            body = response.read(4097)
        finally:
            response.close()
        if status < 200 or status >= 300:
            return False
        payload = json.loads(body.decode("utf-8"))
        return (
            isinstance(payload, dict)
            and payload.get("status") == "ok"
            and payload.get("app") == "ProcessMind"
            and payload.get("kind") == "api"
        )
    except Exception:
        return False


def _browser_candidate_paths(env: Mapping[str, str]) -> Sequence[Path]:
    candidates = []
    explicit = (env.get("PROCESSMIND_BROWSER") or "").strip()
    if explicit:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(explicit))))

    roots = []
    for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        value = (env.get(key) or "").strip()
        if value:
            roots.append(Path(os.path.expandvars(os.path.expanduser(value))))

    relative_paths = (
        Path("Google") / "Chrome" / "Application" / "chrome.exe",
        Path("Microsoft") / "Edge" / "Application" / "msedge.exe",
    )
    for root in roots:
        for relative in relative_paths:
            candidates.append(root / relative)
    return candidates


def find_browser(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    values = os.environ if env is None else env
    for candidate in _browser_candidate_paths(values):
        if candidate.is_file():
            return candidate.resolve()
    return None


def open_browser(url: str, env: Optional[Mapping[str, str]] = None) -> bool:
    browser = find_browser(env)
    if browser is not None:
        subprocess.Popen(
            [str(browser), url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True

    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        startfile(url)
        return True

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except OSError:
        return False


def api_directory(package_root: Path) -> Path:
    return Path(package_root).resolve() / "process-plan-agent-api"


def frontend_directory(package_root: Path) -> Path:
    return Path(package_root).resolve() / "process-plan-agent-ui" / "dist"


def python_executable(package_root: Path) -> Path:
    return Path(package_root).resolve() / ".runtime" / "python" / "python.exe"


def build_environment(package_root: Path, state_dir: Path, env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    package_root = Path(package_root).resolve()
    state_dir = ensure_runtime_dir(state_dir)
    values = dict(os.environ if env is None else env)
    values.update(
        {
            "PROCESSMIND_RUNTIME_DIR": str(state_dir),
            "PROCESSMIND_DATA_DIR": str(state_dir / "data"),
            "PROCESSMIND_FRONTEND_DIR": str(frontend_directory(package_root)),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    api_root = str(api_directory(package_root))
    values["PYTHONPATH"] = api_root + (os.pathsep + values["PYTHONPATH"] if values.get("PYTHONPATH") else "")
    return values


def build_start_command(package_root: Path, port: object) -> Sequence[str]:
    package_root = Path(package_root).resolve()
    return [
        str(python_executable(package_root)),
        "-B",
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        str(api_directory(package_root)),
        "--host",
        HOST,
        "--port",
        str(validate_port(port)),
    ]


def query_process_commandline(pid: int) -> str:
    try:
        completed = subprocess.run(
            ["wmic", "process", "where", "ProcessId=%d" % int(pid), "get", "CommandLine", "/value"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError):
        return ""
    for line in completed.stdout.splitlines():
        if line.lower().startswith("commandline="):
            return line.split("=", 1)[1].strip()
    return ""


def managed_command_matches(commandline: str, package_root: Path) -> bool:
    normalized = (commandline or "").replace("/", "\\").lower()
    root = str(Path(package_root).resolve()).replace("/", "\\").lower().rstrip("\\")
    api_root = str(api_directory(package_root)).replace("/", "\\").lower().rstrip("\\")
    return "app.main:app" in normalized and (root in normalized or api_root in normalized)


def terminate_process(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError):
        return False
    return completed.returncode == 0


def stop_process(
    pid: int,
    package_root: Path,
    query: Optional[Callable[[int], str]] = None,
    terminate: Optional[Callable[[int], bool]] = None,
) -> bool:
    query = query or query_process_commandline
    terminate = terminate or terminate_process
    commandline = query(int(pid))
    if not managed_command_matches(commandline, package_root):
        return False
    return bool(terminate(int(pid)))


def _wait_for_health(port: int, process: subprocess.Popen, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    endpoint = "http://%s:%d/api/startup-ping" % (HOST, port)
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        if health(endpoint, timeout=0.5):
            return True
        time.sleep(0.25)
    return False


def start_application(
    package_root: Path,
    port: object = DEFAULT_PORT,
    state_dir: Optional[Path] = None,
    should_open_browser: bool = True,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    package_root = Path(package_root).resolve()
    port = validate_port(port)
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir(env))
    python = python_executable(package_root)
    api_root = api_directory(package_root)
    frontend_root = frontend_directory(package_root)
    if not python.is_file():
        raise LauncherError("缺少包内 Python 运行时: %s" % python)
    if not api_root.is_dir():
        raise LauncherError("缺少后端目录: %s" % api_root)
    if not (frontend_root / "index.html").is_file():
        raise LauncherError("缺少前端构建产物: %s" % frontend_root)

    existing = read_state(runtime_dir)
    endpoint = "http://%s:%d/api/startup-ping" % (HOST, port)
    if existing and int(existing.get("port", -1)) == port and health(endpoint):
        if should_open_browser and not open_browser("http://%s:%d/" % (HOST, port), env):
            print("浏览器未找到，请手动打开 http://%s:%d/" % (HOST, port))
        return int(existing.get("pid", 0))

    if check_port(HOST, port) == 1:
        raise LauncherError("端口 %d 已被其他程序占用" % port)

    logs = runtime_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    process_env = build_environment(package_root, runtime_dir, env)
    command = build_start_command(package_root, port)
    stdout_path = logs / "api.out.log"
    stderr_path = logs / "api.err.log"
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            list(command),
            cwd=str(api_root),
            env=process_env,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    state = {
        "pid": process.pid,
        "port": port,
        "package_root": str(package_root),
        "api_root": str(api_root),
        "started_at": datetime.utcnow().isoformat() + "Z",
    }
    write_state(runtime_dir, state)
    if not _wait_for_health(port, process):
        terminate_process(process.pid)
        remove_state(runtime_dir)
        raise LauncherError("后端未能在 20 秒内通过健康检查，请查看 %s" % stderr_path)

    url = "http://%s:%d/" % (HOST, port)
    print("ProcessMind 已启动: %s (PID %d)" % (url, process.pid))
    if should_open_browser and not open_browser(url, env):
        print("浏览器未找到，请手动打开 %s" % url)
    return process.pid


def stop_application(package_root: Path, state_dir: Optional[Path] = None) -> bool:
    package_root = Path(package_root).resolve()
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir())
    state = read_state(runtime_dir)
    if not state or not state.get("pid"):
        remove_state(runtime_dir)
        print("ProcessMind 当前未运行")
        return False
    stopped = stop_process(int(state["pid"]), package_root)
    remove_state(runtime_dir)
    if stopped:
        print("ProcessMind 已停止")
    else:
        print("ProcessMind 进程已退出或 PID 已被复用，未终止不匹配的进程")
    return stopped


def status_application(package_root: Path, state_dir: Optional[Path] = None) -> bool:
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir())
    state = read_state(runtime_dir)
    if not state:
        print("ProcessMind 未运行")
        return False
    port = int(state.get("port", DEFAULT_PORT))
    running = health("http://%s:%d/api/startup-ping" % (HOST, port))
    print(json.dumps({"running": running, "pid": state.get("pid"), "port": port}, ensure_ascii=False))
    return running


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ProcessMind Win7 local launcher")
    parser.add_argument("command", choices=("start", "stop", "status"))
    parser.add_argument("--package-root", type=Path, default=package_root_from_file())
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            start_application(args.package_root, args.port, args.state_dir, not args.no_browser)
            return 0
        if args.command == "stop":
            stop_application(args.package_root, args.state_dir)
            return 0
        status_application(args.package_root, args.state_dir)
        return 0
    except LauncherError as exc:
        print("ProcessMind 启动器错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
