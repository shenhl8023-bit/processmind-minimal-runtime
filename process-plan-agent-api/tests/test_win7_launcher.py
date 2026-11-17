import builtins
import importlib.util
import json
from pathlib import Path
import socket
import sys

import pytest


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


@pytest.mark.parametrize("root_key,relative", [
    ("PROGRAMFILES", "Mozilla Firefox/firefox.exe"),
    ("PROGRAMFILES(X86)", "Mozilla Firefox/firefox.exe"),
    ("LOCALAPPDATA", "Mozilla Firefox/firefox.exe"),
    ("LOCALAPPDATA", "Programs/Mozilla Firefox/firefox.exe"),
])
def test_open_browser_prefers_firefox_over_other_installed_browsers(
    tmp_path: Path, monkeypatch, root_key, relative,
):
    launcher = _load_launcher()
    env = {
        "PROGRAMFILES(X86)": str(tmp_path / "Program Files (x86)"),
        "PROGRAMFILES": str(tmp_path / "Program Files"),
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }
    for other in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"):
        path = Path(env["PROGRAMFILES(X86)"]) / other
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
    firefox = Path(env[root_key]) / relative
    firefox.parent.mkdir(parents=True, exist_ok=True)
    firefox.write_bytes(b"fake")
    opened = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command, **kwargs: opened.append(command))

    assert launcher.open_browser("http://127.0.0.1:8000/", env) is True

    assert opened == [[str(firefox.resolve()), "http://127.0.0.1:8000/"]]


def test_find_browser_keeps_explicit_choice_before_firefox(tmp_path: Path):
    launcher = _load_launcher()
    firefox = tmp_path / "Program Files" / "Mozilla Firefox" / "firefox.exe"
    firefox.parent.mkdir(parents=True)
    firefox.write_bytes(b"fake")
    custom = tmp_path / "Custom Browser" / "browser.exe"
    custom.parent.mkdir()
    custom.write_bytes(b"fake")

    assert launcher.find_browser({
        "PROGRAMFILES": str(tmp_path / "Program Files"),
        "PROCESSMIND_BROWSER": str(custom),
    }) == custom


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


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_build_environment_selects_packaged_model_settings_without_explicit_path(tmp_path: Path, configured):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    package_root.mkdir()
    settings_path = package_root / "model-settings.json"
    settings_path.write_text("[]", encoding="utf-8")
    env = {} if configured is None else {"PROCESSMIND_SETTINGS_PATH": configured}
    original_env = dict(env)

    child = launcher.build_environment(package_root, tmp_path / "state", env)

    assert child["PROCESSMIND_SETTINGS_PATH"] == str(settings_path)
    assert env == original_env


def test_build_environment_keeps_runtime_data_default_without_packaged_model_settings(tmp_path: Path):
    launcher = _load_launcher()

    child = launcher.build_environment(tmp_path / "ProcessMind", tmp_path / "state", {})

    assert "PROCESSMIND_SETTINGS_PATH" not in child
    assert child["PROCESSMIND_DATA_DIR"] == str((tmp_path / "state" / "data").resolve())


@pytest.mark.parametrize("packaged", [False, True])
def test_build_environment_preserves_explicit_model_settings_path(tmp_path: Path, packaged):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    package_root.mkdir()
    if packaged:
        (package_root / "model-settings.json").write_text("[]", encoding="utf-8")
    explicit_path = str(tmp_path / "custom" / "settings.json")

    child = launcher.build_environment(
        package_root, tmp_path / "state", {"PROCESSMIND_SETTINGS_PATH": explicit_path}
    )

    assert child["PROCESSMIND_SETTINGS_PATH"] == explicit_path


def test_status_preserves_malformed_port_state_for_owned_live_process(tmp_path: Path, capsys, monkeypatch):
    launcher = _load_launcher()
    state_dir = tmp_path / "runtime"
    root = tmp_path / "ProcessMind"
    original = {"pid": 1234, "port": "invalid", "package_root": str(root)}
    launcher.write_state(state_dir, original)
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root))

    assert launcher.status_application(root, state_dir) is False
    assert launcher.read_state(state_dir) == original
    assert "端口无效" in capsys.readouterr().out
    assert launcher.main(['stop', '--package-root', str(root), '--state-dir', str(state_dir)]) == 1
    assert launcher.read_state(state_dir) == original


def test_socket_load_failure_explains_win7_prerequisite(monkeypatch):
    launcher = _load_launcher()
    real_import = builtins.__import__

    def fail_socket(name, *args, **kwargs):
        if name == "socket":
            raise ImportError("DLL load failed while importing _socket: 参数错误")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_socket)
    with pytest.raises(launcher.LauncherError, match="KB2533623"):
        launcher.check_port("127.0.0.1", 8000)


def test_start_refuses_healthy_service_when_process_identity_is_unavailable(
    tmp_path: Path, monkeypatch
):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    (package_root / ".runtime" / "python").mkdir(parents=True)
    (package_root / ".runtime" / "python" / "python.exe").write_bytes(b"fake")
    (package_root / "process-plan-agent-api").mkdir()
    frontend = package_root / "process-plan-agent-ui" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")

    state_dir = tmp_path / "runtime"
    launcher.write_state(
        state_dir,
        {
            "pid": 4321,
            "port": 8000,
            "package_root": str(package_root),
        },
    )
    monkeypatch.setattr(launcher, "query_process_commandline", lambda _pid: "")
    monkeypatch.setattr(launcher, "process_exists", lambda _pid: True)
    monkeypatch.setattr(launcher, "query_listener_pid", lambda port: 4321)
    monkeypatch.setattr(launcher, "health", lambda _url, timeout=2.0: True)
    monkeypatch.setattr(
        launcher,
        "check_port",
        lambda *_args, **_kwargs: pytest.fail("healthy ProcessMind service was not reused"),
    )

    with pytest.raises(launcher.LauncherError, match="无法确认"):
        launcher.start_application(
            package_root,
            state_dir=state_dir,
            should_open_browser=False,
        )
    assert launcher.read_state(state_dir)['pid'] == 4321


def test_start_does_not_reuse_a_state_file_for_an_unrelated_process(
    tmp_path: Path, monkeypatch
):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    state = {
        "pid": 4321,
        "port": 8000,
        "package_root": str(package_root),
    }
    monkeypatch.setattr(
        launcher,
        "query_process_commandline",
        lambda _pid: r'C:\Other\python.exe -m uvicorn app.main:app --port 8000',
    )

    assert launcher._state_belongs_to_package(state, package_root, 8000) is False


def test_start_requires_ownership_when_state_file_is_missing(
    tmp_path: Path, monkeypatch
):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    (package_root / ".runtime" / "python").mkdir(parents=True)
    (package_root / ".runtime" / "python" / "python.exe").write_bytes(b"fake")
    (package_root / "process-plan-agent-api").mkdir()
    frontend = package_root / "process-plan-agent-ui" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(launcher, "health", lambda _url, timeout=2.0: True)
    monkeypatch.setattr(
        launcher,
        "check_port",
        lambda *_args, **_kwargs: pytest.fail("healthy ProcessMind service was not reused"),
    )

    monkeypatch.setattr(launcher, "query_listener_pid", lambda port: None)
    with pytest.raises(launcher.LauncherError, match="无法确认"):
        launcher.start_application(
            package_root,
            state_dir=tmp_path / "runtime",
            should_open_browser=False,
        )


def test_stop_refuses_reused_pid_even_when_it_is_a_healthy_processmind_listener(
    tmp_path: Path, monkeypatch
):
    launcher = _load_launcher()
    package_root = tmp_path / "ProcessMind"
    state_dir = tmp_path / "runtime"
    launcher.write_state(
        state_dir,
        {
            "pid": 4321,
            "port": 8000,
            "package_root": str(package_root),
        },
    )
    monkeypatch.setattr(launcher, "query_process_commandline", lambda _pid: "")
    monkeypatch.setattr(launcher, "process_exists", lambda _pid: True)
    monkeypatch.setattr(launcher, "query_listener_pid", lambda port: 4321)
    monkeypatch.setattr(launcher, "health", lambda _url, timeout=2.0: True)
    terminated = []
    monkeypatch.setattr(launcher, "terminate_process", lambda pid: terminated.append(pid) or True)

    with pytest.raises(launcher.LauncherError):
        launcher.stop_application(package_root, state_dir)
    assert terminated == []
    assert launcher.read_state(state_dir)['pid'] == 4321


def test_status_refuses_reused_pid_with_unavailable_commandline(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root, runtime = tmp_path / 'old-package', tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 18087, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: '')
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 4321)
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: True)
    assert launcher.status_application(root, runtime) is False
    assert launcher.read_state(runtime)['pid'] == 4321


def test_stop_recovers_matching_replacement_after_recorded_process_exits(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root, runtime = tmp_path / 'package', tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 18087, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'query_process_commandline',
                        lambda pid: _command(launcher, root) if pid == 5678 else '')
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 5678 if port == 18087 else 0)
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: pid != 4321)
    monkeypatch.setattr(launcher, 'check_port', lambda *a, **kw: 1)
    terminated = []
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: terminated.append(pid) or True)
    assert launcher.stop_application(root, runtime) is True
    assert terminated == [5678]
    assert launcher.read_state(runtime) is None


def test_status_recovers_matching_replacement_on_recorded_port(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root, runtime = tmp_path / 'package', tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 18087, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'query_process_commandline',
                        lambda pid: _command(launcher, root) if pid == 5678 else '')
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 5678 if port == 18087 else 0)
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: pid != 4321)
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: True)
    assert launcher.status_application(root, runtime) is True
    assert launcher.read_state(runtime)['pid'] == 5678


def test_failed_stop_retains_state_and_returns_error_to_the_command(tmp_path, monkeypatch):
    launcher = _load_launcher()
    package_root = tmp_path / 'ProcessMind'
    state_dir = tmp_path / 'runtime'
    state = {'pid': 4321, 'port': 8000, 'package_root': str(package_root)}
    launcher.write_state(state_dir, state)
    command = '"%s" -m uvicorn app.main:app --app-dir "%s" --port 8000' % (
        launcher.python_executable(package_root), launcher.api_directory(package_root))
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda _: command)
    monkeypatch.setattr(launcher, 'terminate_process', lambda _: False)
    monkeypatch.setattr(launcher, 'process_exists', lambda _: True)
    result = launcher.main(['stop', '--package-root', str(package_root), '--state-dir', str(state_dir)])
    assert result == 1
    assert launcher.read_state(state_dir) == state


def test_unavailable_wmic_uses_bundled_process_inspection_without_decoding_locale(tmp_path, monkeypatch):
    launcher = _load_launcher()
    command = [str(tmp_path / '中文目录' / 'python.exe'), '-m', 'uvicorn', 'app.main:app']
    class FakeProcess:
        def cmdline(self):
            return command
    import types
    monkeypatch.setitem(sys.modules, 'psutil', types.SimpleNamespace(Process=lambda _: FakeProcess()))
    def missing_wmic(*args, **kwargs):
        raise FileNotFoundError('wmic')
    monkeypatch.setattr(launcher.subprocess, 'run', missing_wmic)
    assert '中文目录' in launcher.query_process_commandline(4321)
    assert 'app.main:app' in launcher.query_process_commandline(4321)


def test_stop_does_not_erase_another_packages_live_state(tmp_path, monkeypatch):
    launcher = _load_launcher()
    state_dir = tmp_path / 'runtime'
    original = tmp_path / 'OldPackage'
    launcher.write_state(state_dir, {'pid': 4321, 'port': 8000, 'package_root': str(original)})
    command = '"%s" -m uvicorn app.main:app --app-dir "%s" --port 8000' % (
        launcher.python_executable(original), launcher.api_directory(original))
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda _: command)
    assert launcher.main(['stop', '--package-root', str(tmp_path / 'NewPackage'), '--state-dir', str(state_dir)]) == 1
    assert launcher.read_state(state_dir)['pid'] == 4321


def _package(tmp_path):
    root = tmp_path / 'ProcessMind'
    (root / '.runtime/python').mkdir(parents=True)
    (root / '.runtime/python/python.exe').write_bytes(b'fake')
    (root / 'process-plan-agent-api').mkdir()
    (root / 'process-plan-agent-ui/dist').mkdir(parents=True)
    (root / 'process-plan-agent-ui/dist/index.html').write_text('<html></html>')
    return root


def _command(launcher, root):
    return '"%s" -m uvicorn app.main:app --app-dir "%s" --host 127.0.0.1 --port 8000' % (
        launcher.python_executable(root), launcher.api_directory(root))


def test_missing_state_stop_recovers_only_the_matching_listener(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root = tmp_path / 'ProcessMind'
    state_dir = tmp_path / 'runtime'
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 4321, raising=False)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root))
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: True)
    assert launcher.stop_application(root, state_dir) is True
    assert launcher.read_state(state_dir) is None


def test_missing_state_start_recovers_listener_state_instead_of_returning_zero(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root = _package(tmp_path)
    state_dir = tmp_path / 'runtime'
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 4321, raising=False)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root))
    monkeypatch.setattr(launcher, 'health', lambda *args, **kwargs: True)
    assert launcher.start_application(root, state_dir=state_dir, should_open_browser=False) == 4321
    assert launcher.read_state(state_dir)['pid'] == 4321


def test_healthy_endpoint_does_not_authorize_killing_a_reused_uninspectable_pid(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root = tmp_path / 'ProcessMind'
    state_dir = tmp_path / 'runtime'
    launcher.write_state(state_dir, {'pid': 4321, 'port': 8000, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 5678, raising=False)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: '')
    monkeypatch.setattr(launcher, 'health', lambda *args, **kwargs: True)
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True, raising=False)
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: pytest.fail('unrelated PID must not be killed'))
    assert launcher.main(['stop', '--package-root', str(root), '--state-dir', str(state_dir)]) == 1
    assert launcher.read_state(state_dir)['pid'] == 4321


def test_status_returns_nonzero_for_a_stopped_service(tmp_path):
    launcher = _load_launcher()
    assert launcher.main(['status', '--package-root', str(tmp_path / 'ProcessMind'),
                          '--state-dir', str(tmp_path / 'runtime')]) == 1


def test_start_refuses_to_overwrite_live_state_for_another_port(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root = _package(tmp_path)
    state_dir = tmp_path / 'runtime'
    state = {'pid': 4321, 'port': 8000, 'package_root': str(root)}
    launcher.write_state(state_dir, state)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root))
    monkeypatch.setattr(launcher, 'health', lambda *args, **kwargs: False)
    monkeypatch.setattr(launcher, 'check_port', lambda *args, **kwargs: 0)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('second instance loses original state'))
    with pytest.raises(launcher.LauncherError, match='8000'):
        launcher.start_application(root, port=8001, state_dir=state_dir, should_open_browser=False)
    assert launcher.read_state(state_dir) == state


def test_failed_start_keeps_state_when_child_cannot_be_terminated(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root = _package(tmp_path)
    state_dir = tmp_path / 'runtime'
    class Process:
        pid = 4321
        def poll(self):
            return None
    monkeypatch.setattr(launcher, 'health', lambda *args, **kwargs: False)
    monkeypatch.setattr(launcher, 'check_port', lambda *args, **kwargs: 0)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *args, **kwargs: Process())
    monkeypatch.setattr(launcher, '_wait_for_health', lambda *args, **kwargs: False)
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: False)
    with pytest.raises(launcher.LauncherError):
        launcher.start_application(root, state_dir=state_dir, should_open_browser=False)
    assert launcher.read_state(state_dir)['pid'] == 4321


@pytest.mark.parametrize('cleanup_succeeds', [True, False])
def test_state_write_failure_cleans_up_new_child_and_returns_actionable_error(
    tmp_path, monkeypatch, capsys, cleanup_succeeds
):
    launcher = _load_launcher()
    root = _package(tmp_path)
    runtime = tmp_path / 'runtime'
    class Process:
        pid = 4321
        def poll(self):
            return None
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: False)
    monkeypatch.setattr(launcher, 'check_port', lambda *a, **kw: 0)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: Process())
    def fail_state(*args):
        raise PermissionError('state temporarily locked')
    monkeypatch.setattr(launcher, 'write_state', fail_state)
    terminated = []
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: terminated.append(pid) or cleanup_succeeds)
    assert launcher.main(['start', '--package-root', str(root), '--state-dir', str(runtime),
                          '--port', '18087', '--no-browser']) == 1
    assert terminated == [4321]
    error = capsys.readouterr().err
    assert 'state temporarily locked' in error
    if cleanup_succeeds:
        assert '已停止' in error
    else:
        assert '4321' in error and '--port 18087' in error and '未确认停止' in error
    assert launcher.read_state(runtime) is None


def test_taskkill_success_is_not_reported_until_process_is_gone(tmp_path, monkeypatch):
    launcher = _load_launcher()
    import types
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *args, **kwargs: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    monkeypatch.setattr(launcher.time, 'sleep', lambda seconds: None)
    clock = iter([0, 0, 10])
    monkeypatch.setattr(launcher.time, 'monotonic', lambda: next(clock, 10))
    assert launcher.terminate_process(4321) is False


def test_netstat_fallback_identifies_exact_listener_when_psutil_cannot_inspect(tmp_path, monkeypatch):
    launcher = _load_launcher()
    import types
    monkeypatch.setitem(sys.modules, 'psutil', types.SimpleNamespace())
    output = b'  TCP    0.0.0.0:8000  0.0.0.0:0  LISTENING  4321\r\n  TCP 127.0.0.1:18000 0.0.0.0:0 LISTENING 5678\r\n  TCP 127.0.0.1:8000 127.0.0.1:62100 ESTABLISHED 4321\r\n'
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *a, **kw: types.SimpleNamespace(returncode=0, stdout=output))
    assert launcher.query_listener_pid(8000) == 4321
    assert launcher.query_listener_pid(8001) == 0


def test_status_does_not_report_another_install_as_running(tmp_path, monkeypatch):
    launcher = _load_launcher()
    runtime = tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 8000, 'package_root': str(tmp_path / 'old')})
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: True)
    assert launcher.status_application(tmp_path / 'new', runtime) is False


def test_stop_rejects_mismatched_explicit_port_without_killing(tmp_path, monkeypatch):
    launcher = _load_launcher()
    root, runtime = tmp_path / 'package', tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 8000, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: pytest.fail('wrong port killed'))
    assert launcher.main(['stop', '--package-root', str(root), '--state-dir', str(runtime), '--port', '8001']) == 1
    assert launcher.read_state(runtime)['port'] == 8000


def test_process_existence_can_be_verified_without_psutil(monkeypatch):
    launcher = _load_launcher()
    import subprocess
    import types
    monkeypatch.setitem(sys.modules, 'psutil', types.SimpleNamespace())
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        assert launcher.process_exists(process.pid) is True
        process.terminate()
        process.wait(timeout=5)
        assert launcher.process_exists(process.pid) is False
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_overlapping_starts_do_not_spawn_a_second_child_or_overwrite_state(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    launcher = _load_launcher()
    root = _package(tmp_path)
    runtime = tmp_path / 'runtime'
    first_spawning = threading.Event()
    release_first = threading.Event()
    children = []
    class Process:
        def __init__(self, pid):
            self.pid = pid
        def poll(self):
            return None
    def spawn(*args, **kwargs):
        pid = 4321 + len(children)
        children.append(pid)
        if pid == 4321:
            first_spawning.set()
            assert release_first.wait(5)
        return Process(pid)
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: False)
    monkeypatch.setattr(launcher, 'check_port', lambda *a, **kw: 0)
    monkeypatch.setattr(launcher, '_wait_for_health', lambda *a, **kw: True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(launcher.start_application, root, 18087, runtime, False)
        try:
            assert first_spawning.wait(5)
            with pytest.raises(launcher.LauncherError, match='正在执行'):
                launcher.start_application(root, 18087, runtime, False)
        finally:
            release_first.set()
        assert first.result(timeout=5) == 4321
    assert children == [4321]
    assert launcher.read_state(runtime)['pid'] == 4321


def test_all_lifecycle_commands_share_a_crash_released_process_lock(tmp_path):
    import subprocess
    launcher = _load_launcher()
    root = _package(tmp_path)
    runtime = tmp_path / 'runtime'
    code = (
        "import runpy,sys,time; from pathlib import Path; "
        "m=runpy.run_path(sys.argv[1]); "
        "r=m['ensure_runtime_dir'](Path(sys.argv[2])); "
        "lock=m['lifecycle_lock'](r); lock.__enter__(); "
        "print('locked',flush=True); time.sleep(30)"
    )
    process = subprocess.Popen([sys.executable, '-c', code, str(LAUNCHER_PATH), str(runtime)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'locked'
        with pytest.raises(launcher.LauncherError, match='正在执行'):
            launcher.start_application(root, 18087, runtime, False)
        with pytest.raises(launcher.LauncherError, match='正在执行'):
            launcher.stop_application(root, runtime, 18087)
        with pytest.raises(launcher.LauncherError, match='正在执行'):
            launcher.status_application(root, runtime, 18087)
    finally:
        process.terminate()
        process.wait(timeout=5)
    assert launcher.status_application(root, runtime, 18087) is False


def test_basic_trial_uses_an_independent_runtime_and_pins_delivered_profile(tmp_path: Path):
    import json
    launcher = _load_launcher()
    package = tmp_path / 'trial-package'
    package.mkdir()
    profile = package / 'product-profile.json'
    profile.write_text(json.dumps({'edition': 'basic-trial', 'template_mapping_enabled': False,
                                   'expires_at': '2026-12-31T00:00:00+08:00'}))
    env = {'LOCALAPPDATA': str(tmp_path / 'local'), 'PROCESSMIND_PROFILE_PATH': 'other-profile.json'}
    assert launcher.resolve_runtime_dir(env, package) == (tmp_path / 'local' / 'ProcessMindBasicTrial').resolve()
    child = launcher.build_environment(package, tmp_path / 'state', env)
    assert child['PROCESSMIND_PROFILE_PATH'] == str(profile.resolve())
    assert child['PROCESSMIND_DATA_DIR'] == str((tmp_path / 'state' / 'data').resolve())


def _observe_start(launcher, monkeypatch):
    commands, browsers = [], []
    class Child:
        pid = 4321
        def poll(self):
            return None
    def spawn(command, **kwargs):
        commands.append(command)
        return Child()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: False)
    monkeypatch.setattr(launcher, 'check_port', lambda *a, **kw: 0)
    monkeypatch.setattr(launcher, '_wait_for_health', lambda *a, **kw: True)
    monkeypatch.setattr(launcher, 'open_browser', lambda url, env=None: browsers.append(url) or True)
    return commands, browsers


@pytest.mark.parametrize('payload,explicit,expected', [
    (None, None, 8000),
    ('{"port":8001}', None, 8001),
    ('\ufeff{"port":18087}', None, 18087),
    ('{"port":8001}', 18088, 18088),
    ('broken config', 18088, 18088),
])
def test_start_port_configuration_reaches_process_browser_and_state(tmp_path, monkeypatch, payload, explicit, expected):
    launcher = _load_launcher()
    root = _package(tmp_path)
    if payload is not None:
        (root / 'launcher-config.json').write_text(payload, encoding='utf-8')
    runtime = tmp_path / 'runtime'
    commands, browsers = _observe_start(launcher, monkeypatch)
    args = ['start', '--package-root', str(root), '--state-dir', str(runtime)]
    if explicit is not None:
        args += ['--port', str(explicit)]
    assert launcher.main(args) == 0
    assert commands[0][-2:] == ['--port', str(expected)]
    assert browsers == ['http://127.0.0.1:%d/' % expected]
    assert launcher.read_state(runtime)['port'] == expected


@pytest.mark.parametrize('payload', [
    '{', '[]', '{}', '{"pot":8001}', '{"port":null}', '{"port":true}',
    '{"port":"8001"}', '{"port":8001.5}', '{"port":0}', '{"port":-1}',
    '{"port":65536}', '{"port":8001,"host":"0.0.0.0"}',
])
def test_invalid_port_config_explains_file_and_never_starts(tmp_path, monkeypatch, capsys, payload):
    launcher = _load_launcher()
    root = _package(tmp_path)
    config = root / 'launcher-config.json'
    config.write_text(payload, encoding='utf-8')
    runtime = tmp_path / 'runtime'
    commands, browsers = _observe_start(launcher, monkeypatch)
    assert launcher.main(['start', '--package-root', str(root), '--state-dir', str(runtime)]) == 1
    assert str(config) in capsys.readouterr().err
    assert commands == [] and browsers == []
    assert launcher.read_state(runtime) is None


@pytest.mark.parametrize('payload', ['{"port":8001}', 'broken config'])
def test_status_and_stop_use_recorded_port_even_after_config_changes(tmp_path, monkeypatch, payload):
    launcher = _load_launcher()
    root = _package(tmp_path)
    (root / 'launcher-config.json').write_text(payload, encoding='utf-8')
    runtime = tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 8000, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root))
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    urls, terminated = [], []
    def health(url, **kwargs):
        urls.append(url)
        return url == 'http://127.0.0.1:8000/api/startup-ping'
    monkeypatch.setattr(launcher, 'health', health)
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: terminated.append(pid) or True)
    assert launcher.status_application(root, runtime) is True
    assert urls == ['http://127.0.0.1:8000/api/startup-ping']
    assert launcher.stop_application(root, runtime) is True
    assert terminated == [4321]
    assert launcher.read_state(runtime) is None


@pytest.mark.parametrize('action', ['status', 'stop'])
def test_missing_state_recovers_on_configured_port(tmp_path, monkeypatch, action):
    launcher = _load_launcher()
    root = _package(tmp_path)
    (root / 'launcher-config.json').write_text('{"port":8001}', encoding='utf-8')
    runtime = tmp_path / 'runtime'
    monkeypatch.setattr(launcher, 'query_listener_pid', lambda port: 4321 if port == 8001 else 0)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root).replace('--port 8000', '--port 8001'))
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    monkeypatch.setattr(launcher, 'health', lambda url, **kw: ':8001/' in url)
    terminated = []
    monkeypatch.setattr(launcher, 'terminate_process', lambda pid: terminated.append(pid) or True)
    assert launcher.main([action, '--package-root', str(root), '--state-dir', str(runtime)]) == 0
    if action == 'status':
        assert launcher.read_state(runtime)['port'] == 8001
    else:
        assert terminated == [4321]
        assert launcher.read_state(runtime) is None


def test_config_change_reuses_running_instance_until_it_is_stopped(tmp_path, monkeypatch, capsys):
    launcher = _load_launcher()
    root = _package(tmp_path)
    (root / 'launcher-config.json').write_text('{"port":8001}', encoding='utf-8')
    runtime = tmp_path / 'runtime'
    launcher.write_state(runtime, {'pid': 4321, 'port': 8000, 'package_root': str(root)})
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, root))
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    monkeypatch.setattr(launcher, 'health', lambda url, **kw: ':8000/' in url)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: pytest.fail('second instance'))
    urls = []
    monkeypatch.setattr(launcher, 'open_browser', lambda url, env=None: urls.append(url) or True)
    assert launcher.start_application(root, state_dir=runtime) == 4321
    assert urls == ['http://127.0.0.1:8000/']
    assert launcher.read_state(runtime)['port'] == 8000
    output = capsys.readouterr().out
    assert '8001' in output and '重新启动' in output


def test_custom_port_cannot_bypass_live_old_directory_state(tmp_path, monkeypatch, capsys):
    launcher = _load_launcher()
    root = _package(tmp_path)
    old = tmp_path / '旧版目录'
    (root / 'launcher-config.json').write_text('{"port":8001}', encoding='utf-8')
    runtime = tmp_path / 'runtime'
    state = {'pid': 4321, 'port': 8000, 'package_root': str(old)}
    launcher.write_state(runtime, state)
    monkeypatch.setattr(launcher, 'query_process_commandline', lambda pid: _command(launcher, old))
    monkeypatch.setattr(launcher, 'process_exists', lambda pid: True)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: pytest.fail('parallel upgrade'))
    assert launcher.main(['start', '--package-root', str(root), '--state-dir', str(runtime)]) == 1
    assert str(old / 'stop-win7.cmd') in capsys.readouterr().err
    assert launcher.read_state(runtime) == state


def test_occupied_configured_port_reports_the_configuration_to_edit(tmp_path, monkeypatch, capsys):
    launcher = _load_launcher()
    root = _package(tmp_path)
    config = root / 'launcher-config.json'
    config.write_text('{"port":8001}', encoding='utf-8')
    runtime = tmp_path / 'runtime'
    monkeypatch.setattr(launcher, 'health', lambda *a, **kw: False)
    checked = []
    monkeypatch.setattr(launcher, 'check_port', lambda host, port: checked.append(port) or 1)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: pytest.fail('occupied port'))
    assert launcher.main(['start', '--package-root', str(root), '--state-dir', str(runtime)]) == 1
    assert checked == [8001]
    error = capsys.readouterr().err
    assert str(config) in error and '8001' in error
