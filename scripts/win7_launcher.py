#!/usr/bin/env python3
"""Win7-compatible local launcher for the packaged ProcessMind app."""

from __future__ import print_function

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable, Dict, Mapping, Optional, Sequence


HOST = "127.0.0.1"
DEFAULT_PORT = 8000
STATE_FILE_NAME = "processmind-win7.json"


class LauncherError(Exception):
    """An expected launcher failure that can be shown without a traceback."""


def _win7_prerequisite_error(exc: BaseException) -> LauncherError:
    installer = package_root_from_file() / "prerequisites" / "install-kb2533623.bat"
    return LauncherError(
        "包内 Python 无法加载 _socket.pyd（%s）。Win7 请先以管理员身份运行 %s，"
        "安装 KB2533623（或包含该修复的后续更新），然后重启系统再启动 ProcessMind。"
        % (exc, installer)
    )


def _load_socket_module():
    """Load socket only when needed so Win7 prerequisite errors stay actionable."""
    try:
        import socket as socket_module
    except (ImportError, OSError) as exc:
        raise _win7_prerequisite_error(exc)
    return socket_module


def _load_urlopen():
    try:
        from urllib.request import urlopen
    except (ImportError, OSError) as exc:
        raise _win7_prerequisite_error(exc)
    return urlopen


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
        with tempfile.TemporaryFile(dir=str(path), prefix=".write-test-"):
            pass
    except (OSError, IOError) as exc:
        raise LauncherError("运行时目录不可写: %s" % exc)
    return path


@contextmanager
def lifecycle_lock(runtime_dir: Path):
    # Never remove the lock file: unlinking can let concurrent commands lock
    # different files. The OS releases the byte/file lock if the launcher dies.
    try:
        stream = (runtime_dir / "processmind-win7.lock").open("a+b")
    except OSError as exc:
        raise LauncherError("无法打开启停锁: %s" % exc)
    with stream:
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(bytes([0]))
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LauncherError("另一个启停或状态命令正在执行，或无法获取锁；请稍后重试: %s" % exc)
        yield


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
    socket_module = _load_socket_module()
    try:
        with socket_module.create_connection((host, value), timeout=timeout):
            return 1
    except (socket_module.timeout, socket_module.error, OSError):
        return 0


def health(url: str, timeout: float = 2.0) -> bool:
    urlopen = _load_urlopen()
    try:
        response = urlopen(url, timeout=timeout)
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
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
        try:
            subprocess.Popen(
                [str(browser), url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except OSError:
            return False

    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        try:
            startfile(url)
            return True
        except OSError:
            return False

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
    # psutil is part of the pinned offline runtime and reads Unicode command
    # lines directly, avoiding WMIC availability and redirected output encoding.
    try:
        import psutil
        return subprocess.list2cmdline(psutil.Process(int(pid)).cmdline())
    except (ImportError, OSError, ValueError):
        pass
    except Exception:
        # AccessDenied/NoSuchProcess must not crash the launcher. WMIC is a
        # bounded compatibility fallback, not an authority to kill blindly.
        pass
    try:
        completed = subprocess.run(
            ["wmic", "process", "where", "ProcessId=%d" % int(pid), "get", "CommandLine", "/value"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            errors="replace",
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ""
    for line in completed.stdout.splitlines():
        if line.lower().startswith("commandline="):
            return line.split("=", 1)[1].strip()
    return ""


def managed_command_matches(commandline: str, package_root: Path) -> bool:
    normalized = (commandline or "").replace("/", "\\").lower()
    root = str(Path(package_root).resolve()).replace("/", "\\").lower().rstrip("\\")
    api_root = str(api_directory(package_root)).replace("/", "\\").lower().rstrip("\\")
    if "app.main:app" not in normalized:
        return False
    tokens = [
        token.strip().strip('"').strip("'").replace("/", "\\").lower().rstrip("\\")
        for token in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', str(commandline or ""))
    ]
    return root in tokens or api_root in tokens


def query_listener_pid(port: int) -> Optional[int]:
    """Return the loopback listener PID, zero if absent, None if unknown."""
    port = validate_port(port)
    try:
        import psutil
        matches = {
            item.pid for item in psutil.net_connections(kind="tcp")
            if item.status == psutil.CONN_LISTEN and item.laddr
            and item.laddr.port == port
            and item.laddr.ip in (HOST, "0.0.0.0", "::", "::1") and item.pid
        }
        return next(iter(matches)) if len(matches) == 1 else (0 if not matches else None)
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return None
        matches = set()
        for line in result.stdout.decode("ascii", errors="replace").splitlines():
            fields = line.split()
            if len(fields) != 5 or fields[0].upper() != "TCP":
                continue
            address, separator, number = fields[1].rpartition(":")
            if separator and number == str(port) and address in (HOST, "0.0.0.0", "[::]", "[::1]"):
                if fields[3].upper() == "LISTENING" and fields[4].isdigit():
                    matches.add(int(fields[4]))
        return next(iter(matches)) if len(matches) == 1 else (0 if not matches else None)
    except (OSError, subprocess.TimeoutExpired):
        return None


def process_exists(pid: int) -> Optional[bool]:
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not handle:
                error = ctypes.get_last_error()
                return False if error == 87 else (True if error == 5 else None)
            try:
                status = kernel.WaitForSingleObject(handle, 0)
                return True if status == 258 else (False if status == 0 else None)
            finally:
                kernel.CloseHandle(handle)
        except (OSError, AttributeError):
            return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None


def _state_belongs_to_package(state: Mapping[str, object], package_root: Path, port: int) -> bool:
    try:
        if validate_port(state.get("port")) != port:
            return False
        recorded_root = Path(str(state.get("package_root", ""))).expanduser().resolve()
        pid = int(state.get("pid"))
    except (OSError, TypeError, ValueError, LauncherError):
        return False
    if recorded_root != Path(package_root).resolve() or pid <= 0:
        return False
    # A PID may have been reused by another ProcessMind installation. Listener
    # equality plus a generic health response cannot establish package identity.
    return managed_command_matches(query_process_commandline(pid), package_root)


def recover_state(package_root: Path, runtime_dir: Path, port: int) -> Optional[Dict[str, object]]:
    pid = query_listener_pid(port)
    if not pid or not managed_command_matches(query_process_commandline(pid), package_root):
        return None
    state = {"pid": pid, "port": port, "package_root": str(package_root),
             "api_root": str(api_directory(package_root)), "recovered": True}
    write_state(runtime_dir, state)
    return state


def terminate_process(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            errors="replace",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return process_exists(pid) is False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if process_exists(pid) is False:
            return True
        time.sleep(0.1)
    return False


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
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir(env))
    with lifecycle_lock(runtime_dir):
        return _start_application(package_root, port, runtime_dir, should_open_browser, env)


def _start_application(
    package_root: Path,
    port: object,
    state_dir: Path,
    should_open_browser: bool,
    env: Optional[Mapping[str, str]],
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
    if existing:
        try:
            old_pid = int(existing.get("pid", 0))
            old_port = validate_port(existing.get("port", DEFAULT_PORT))
        except (TypeError, ValueError, LauncherError):
            raise LauncherError("状态文件无效，请先运行 stop-win7.cmd 检查")
        old_root = Path(str(existing.get("package_root", ""))).resolve()
        old_command = query_process_commandline(old_pid) if old_pid > 0 else ""
        old_live = managed_command_matches(old_command, old_root) or process_exists(old_pid) is not False
        if old_live and (old_root != package_root or old_port != port):
            raise LauncherError("已有运行状态：目录 %s，端口 %d；请先用原目录关闭，不能覆盖状态" % (old_root, old_port))
        if old_live and not old_command:
            raise LauncherError("无法确认已有进程状态，不能覆盖状态文件；请先执行 stop-win7.cmd")
    if existing and _state_belongs_to_package(existing, package_root, port) and health(endpoint):
        if should_open_browser and not open_browser("http://%s:%d/" % (HOST, port), env):
            print("浏览器未找到，请手动打开 http://%s:%d/" % (HOST, port))
        return int(existing.get("pid", 0))

    if existing and _state_belongs_to_package(existing, package_root, port):
        raise LauncherError("已记录的进程仍在运行但健康检查失败，请先执行 stop-win7.cmd；状态文件已保留")

    if health(endpoint):
        recovered = recover_state(package_root, runtime_dir, port)
        if not recovered:
            raise LauncherError("端口 %d 已有 ProcessMind，但无法确认属于当前目录；请使用原启动目录关闭" % port)
        if should_open_browser and not open_browser("http://%s:%d/" % (HOST, port), env):
            print("浏览器未找到，请手动打开 http://%s:%d/" % (HOST, port))
        print("ProcessMind 已在运行，已恢复状态: http://%s:%d/" % (HOST, port))
        return int(recovered["pid"])

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
    try:
        write_state(runtime_dir, state)
    except OSError as exc:
        stopped = process.poll() is not None or terminate_process(process.pid)
        if stopped:
            raise LauncherError("无法保存启动状态（%s）；本次启动的进程已停止，请检查状态目录后重试" % exc)
        raise LauncherError(
            "无法保存启动状态（%s）；本次进程 PID %d 未确认停止。请从当前目录运行 "
            "stop-win7.cmd --port %d 重新识别并关闭；错误日志: %s"
            % (exc, process.pid, port, stderr_path)
        )
    if not _wait_for_health(port, process):
        if process.poll() is not None or terminate_process(process.pid):
            remove_state(runtime_dir)
        raise LauncherError("后端未能在 20 秒内通过健康检查，请查看 %s；若状态仍在，请运行 stop-win7.cmd 重试关闭" % stderr_path)

    url = "http://%s:%d/" % (HOST, port)
    print("ProcessMind 已启动: %s (PID %d)" % (url, process.pid))
    if should_open_browser and not open_browser(url, env):
        print("浏览器未找到，请手动打开 %s" % url)
    return process.pid


def stop_application(package_root: Path, state_dir: Optional[Path] = None, port: Optional[int] = None) -> bool:
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir())
    with lifecycle_lock(runtime_dir):
        return _stop_application(package_root, runtime_dir, port)


def _stop_application(package_root: Path, state_dir: Path, port: Optional[int]) -> bool:
    package_root = Path(package_root).resolve()
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir())
    state = read_state(runtime_dir)
    if not state or not state.get("pid"):
        target_port = validate_port(port if port is not None else DEFAULT_PORT)
        state = recover_state(package_root, runtime_dir, target_port)
        if not state:
            listener = query_listener_pid(target_port)
            if listener or (listener is None and check_port(HOST, target_port)):
                raise LauncherError("端口 %d 仍有服务，无法确认属于当前目录；未关闭其他进程" % target_port)
            remove_state(runtime_dir)
            print("ProcessMind 当前未运行")
            return False
    if Path(str(state.get("package_root", ""))).resolve() != package_root:
        raise LauncherError("运行状态属于其他安装目录，请使用原目录的 stop-win7.cmd 关闭：%s" % state.get("package_root", ""))
    try:
        pid = int(state["pid"])
        target_port = validate_port(state.get("port", DEFAULT_PORT))
        if pid <= 0:
            raise ValueError("invalid PID")
    except (TypeError, ValueError, LauncherError):
        raise LauncherError("状态文件 PID 或端口无效，未终止任何进程；请检查状态文件")
    if port is not None and validate_port(port) != target_port:
        raise LauncherError("状态记录的端口为 %d，与 --port 不一致" % target_port)
    if process_exists(pid) is False:
        recovered = recover_state(package_root, runtime_dir, target_port)
        if recovered:
            pid = int(recovered["pid"])
    commandline = query_process_commandline(pid)
    stopped = stop_process(pid, package_root, query=lambda _pid: commandline)
    if not stopped and process_exists(pid) is False and not check_port(HOST, target_port):
        remove_state(runtime_dir)
        print("ProcessMind 进程已退出，已清理状态")
        return False
    if stopped:
        remove_state(runtime_dir)
        print("ProcessMind 已停止")
    else:
        raise LauncherError("未能确认进程已停止，状态文件已保留。请检查进程权限或使用原目录重试；不会终止不匹配的进程。")
    return stopped


def status_application(package_root: Path, state_dir: Optional[Path] = None, port: Optional[int] = None) -> bool:
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir())
    with lifecycle_lock(runtime_dir):
        return _status_application(package_root, runtime_dir, port)


def _status_application(package_root: Path, state_dir: Path, port: Optional[int]) -> bool:
    package_root = Path(package_root).resolve()
    runtime_dir = ensure_runtime_dir(state_dir or resolve_runtime_dir())
    state = read_state(runtime_dir)
    if not state:
        state = recover_state(package_root, runtime_dir, validate_port(port if port is not None else DEFAULT_PORT))
    if not state:
        print("ProcessMind 未运行")
        return False
    try:
        target_port = validate_port(state.get("port", DEFAULT_PORT))
    except LauncherError:
        print("ProcessMind 状态文件中的端口无效，状态已保留；请检查状态文件，不代表进程已退出")
        return False
    if port is not None and validate_port(port) != target_port:
        raise LauncherError("状态记录的端口为 %d，与 --port 不一致" % target_port)
    try:
        recorded_pid = int(state.get("pid", 0))
    except (TypeError, ValueError):
        recorded_pid = 0
    if (Path(str(state.get("package_root", ""))).resolve() == package_root
            and process_exists(recorded_pid) is False):
        state = recover_state(package_root, runtime_dir, target_port) or state
    owned = _state_belongs_to_package(state, package_root, target_port)
    running = owned and health("http://%s:%d/api/startup-ping" % (HOST, target_port))
    print(json.dumps({"running": running, "owned": owned, "pid": state.get("pid"), "port": target_port,
                      "package_root": state.get("package_root")}, ensure_ascii=False))
    return running


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ProcessMind Win7 local launcher")
    parser.add_argument("command", choices=("start", "stop", "status"))
    parser.add_argument("--package-root", type=Path, default=package_root_from_file())
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            start_application(args.package_root, args.port if args.port is not None else DEFAULT_PORT, args.state_dir, not args.no_browser)
            return 0
        if args.command == "stop":
            stop_application(args.package_root, args.state_dir, args.port)
            return 0
        return 0 if status_application(args.package_root, args.state_dir, args.port) else 1
    except LauncherError as exc:
        print("ProcessMind 启动器错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
