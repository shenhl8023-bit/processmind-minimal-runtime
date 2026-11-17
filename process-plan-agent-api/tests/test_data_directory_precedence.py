import importlib.util
from pathlib import Path
import shutil

import pytest


@pytest.mark.parametrize('explicit_parent', [False, True])
@pytest.mark.parametrize('individual_overrides', [False, True])
def test_data_directory_precedence_with_legacy_files(tmp_path, monkeypatch, explicit_parent, individual_overrides):
    source = Path(__file__).resolve().parents[1] / 'app/core/paths.py'
    api = tmp_path / 'package/process-plan-agent-api'
    module_path = api / 'app/core/paths.py'
    module_path.parent.mkdir(parents=True)
    shutil.copyfile(str(source), str(module_path))
    (api / 'process_mind.db').touch()
    (api / 'uploads').mkdir()
    (api / 'process_settings.json').write_text('{}')
    for name in ['PROCESSMIND_DATA_DIR', 'PROCESSMIND_DB_PATH', 'PROCESSMIND_UPLOAD_DIR', 'PROCESSMIND_SETTINGS_PATH']:
        monkeypatch.delenv(name, raising=False)
    requested = tmp_path / 'requested'
    if explicit_parent:
        monkeypatch.setenv('PROCESSMIND_DATA_DIR', str(requested))
    if individual_overrides:
        monkeypatch.setenv('PROCESSMIND_DB_PATH', str(tmp_path / 'individual.db'))
        monkeypatch.setenv('PROCESSMIND_UPLOAD_DIR', str(tmp_path / 'individual-uploads'))
        monkeypatch.setenv('PROCESSMIND_SETTINGS_PATH', str(tmp_path / 'individual.json'))
    spec = importlib.util.spec_from_file_location('isolated_paths', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if individual_overrides:
        expected = (tmp_path / 'individual.db', tmp_path / 'individual-uploads', tmp_path / 'individual.json')
    elif explicit_parent:
        expected = (requested / 'db/process_mind.db', requested / 'uploads', requested / 'config/process_settings.json')
    else:
        expected = (api / 'process_mind.db', api / 'uploads', api / 'process_settings.json')
    assert (module.DEFAULT_DB_PATH, module.UPLOAD_DIR, module.SETTINGS_FILE_PATH) == expected
