import importlib.util
from pathlib import Path
import socket
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = REPO_ROOT / "scripts" / "win7_launcher.py"


def _load_launcher():
    spec = importlib.util.spec_from_file_location("processmind_win7_launcher", LAUNCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_directory_precedence_and_state_roundtrip(tmp_path: Path):
    launcher = _load_launcher()
    explicit = tmp_path / "explicit"
    local = tmp_path / "local"
    temporary = tmp_path / "temp"
    env = {
        "PROCESSMIND_RUNTIME_DIR": str(explicit),
        "LOCALAPPDATA": str(local),
        "TEMP": str(temporary),
    }

    assert launcher.resolve_runtime_dir(env) == explicit.resolve()
    env.pop("PROCESSMIND_RUNTIME_DIR")
    assert launcher.resolve_runtime_dir(env) == (local / "ProcessMind").resolve()
    env.pop("LOCALAPPDATA")
    assert launcher.resolve_runtime_dir(env) == (temporary / "ProcessMind").resolve()

    state = {"pid": 1234, "port": 8000, "package_root": "C:/ProcessMind"}
    launcher.write_state(temporary, state)
    assert launcher.read_state(temporary) == state


def test_check_port_reports_free_and_listening_ports():
    launcher = _load_launcher()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        assert launcher.check_port("127.0.0.1", port) == 1

    assert launcher.check_port("127.0.0.1", port) == 0
    assert launcher.check_port("127.0.0.1", 0) == 2


def test_find_browser_prefers_an_installed_chrome_candidate(tmp_path: Path):
    launcher = _load_launcher()
    chrome = tmp_path / "Program Files" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"fake")

    env = {"PROGRAMFILES": str(tmp_path / "Program Files")}

    assert launcher.find_browser(env) == chrome


def test_stop_process_refuses_an_unrelated_command_line(tmp_path: Path):
    launcher = _load_launcher()
    terminated = []

    result = launcher.stop_process(
        1234,
        tmp_path / "ProcessMind",
        query=lambda _pid: r"C:\Other\python.exe -m uvicorn app.main:app --port 8000",
        terminate=lambda pid: terminated.append(pid),
    )

    assert result is False
    assert terminated == []


def test_managed_command_requires_an_exact_package_path(tmp_path: Path):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    windows_root = str(package_root.resolve()).replace("/", "\\")
    windows_api = windows_root + "\\process-plan-agent-api"

    assert launcher.managed_command_matches(
        '"%s\\.runtime\\python\\python.exe" -m uvicorn app.main:app '
        '--app-dir "%s" --host 127.0.0.1 --port 8000' % (windows_root, windows_api),
        package_root,
    )
    assert not launcher.managed_command_matches(
        '"%sOther\\.runtime\\python\\python.exe" -m uvicorn app.main:app '
        '--app-dir "%sOther" --host 127.0.0.1 --port 8000' % (windows_root, windows_api),
        package_root,
    )


def test_build_start_command_has_one_port_argument(tmp_path: Path):
    launcher = _load_launcher()
    command = list(launcher.build_start_command(tmp_path / "ProcessMind", 8000))

    assert command.count("--port") == 1
    assert command[-1] == "8000"


def test_status_cleans_malformed_state_port(tmp_path: Path, capsys):
    launcher = _load_launcher()
    state_dir = tmp_path / "runtime"
    launcher.write_state(state_dir, {"pid": 1234, "port": "invalid"})

    assert launcher.status_application(tmp_path / "ProcessMind", state_dir) is False
    assert launcher.read_state(state_dir) is None
    assert "端口无效" in capsys.readouterr().out
