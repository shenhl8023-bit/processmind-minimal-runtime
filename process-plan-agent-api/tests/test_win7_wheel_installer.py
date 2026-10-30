import importlib.util
from pathlib import Path
import sys
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_PATH = PROJECT_ROOT / "scripts" / "install-win7-wheels.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("processmind_win7_wheel_installer", INSTALLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_wheel(path: Path, *, tag: str = "py3-none-any"):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "demo_pkg/__init__.py",
            "VALUE = 'installed'\n",
        )
        archive.writestr(
            "demo_pkg-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: demo-pkg\nVersion: 1.0.0\n",
        )
        archive.writestr(
            "demo_pkg-1.0.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: %s\n" % tag,
        )


def _write_native_wheel(path: Path, payload: bytes, *, name: str = "pydantic-core"):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pydantic_core/_pydantic_core.cp38-win_amd64.pyd", payload)
        archive.writestr(
            "%s-2.27.2.dist-info/METADATA" % name.replace("-", "_"),
            "Metadata-Version: 2.1\nName: %s\nVersion: 2.27.2\n" % name,
        )
        archive.writestr(
            "%s-2.27.2.dist-info/WHEEL" % name.replace("-", "_"),
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\n"
            "Tag: cp38-cp38-win_amd64\n",
        )


def test_installer_extracts_locked_wheels_without_pip(tmp_path: Path):
    installer = _load_installer()
    wheelhouse = tmp_path / "wheelhouse"
    target = tmp_path / "site-packages"
    wheelhouse.mkdir()
    _write_wheel(wheelhouse / "demo_pkg-1.0.0-py3-none-any.whl")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("demo-pkg==1.0.0\n", encoding="utf-8")

    installed = installer.install_requirements(requirements, wheelhouse, target)

    assert installed == ["demo-pkg==1.0.0"]
    assert (target / "demo_pkg/__init__.py").read_text(encoding="utf-8") == "VALUE = 'installed'\n"
    assert (target / "demo_pkg-1.0.0.dist-info/METADATA").is_file()


def test_installer_rejects_a_non_win7_wheel(tmp_path: Path):
    installer = _load_installer()
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_wheel(wheelhouse / "demo_pkg-1.0.0-cp39-cp39-win_amd64.whl", tag="cp39-cp39-win_amd64")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("demo-pkg==1.0.0\n", encoding="utf-8")

    try:
        installer.install_requirements(requirements, wheelhouse, tmp_path / "site-packages")
    except installer.WheelInstallError as exc:
        assert "compatible" in str(exc).lower()
    else:
        raise AssertionError("an incompatible CPython wheel must be rejected")


def test_installer_rejects_pydantic_core_win10_only_imports(tmp_path: Path):
    installer = _load_installer()
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _write_native_wheel(
        wheelhouse / "pydantic_core-2.27.2-cp38-cp38-win_amd64.whl",
        b"bcryptprimitives.dll\x00ProcessPrng\x00",
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pydantic-core==2.27.2\n", encoding="utf-8")

    try:
        installer.install_requirements(requirements, wheelhouse, tmp_path / "site-packages")
    except installer.WheelInstallError as exc:
        assert "windows 7" in str(exc).lower()
    else:
        raise AssertionError("a Win10-only pydantic-core import must be rejected")
