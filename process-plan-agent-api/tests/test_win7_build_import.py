from pathlib import Path
import re
import subprocess
import sys


def test_embedded_python_build_import_uses_explicit_api_path(tmp_path):
    script = Path(__file__).resolve().parents[2] / 'scripts/build-win7-runtime.ps1'
    command = re.search(r'& \$PythonExe -c "([^"]*import app\.main[^"]*)"([^\n]*)', script.read_text())
    assert command is not None
    api = tmp_path / 'api'
    (api / 'app').mkdir(parents=True)
    (api / 'app/__init__.py').write_text('')
    (api / 'app/main.py').write_text('LOADED = True')
    # Isolated mode omits cwd/PYTHONPATH like the Windows embeddable _pth runtime.
    arguments = [str(api)] if '$apiRoot' in command.group(2) else []
    result = subprocess.run([sys.executable, '-I', '-B', '-c', command.group(1)] + arguments,
                            cwd=str(api), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
