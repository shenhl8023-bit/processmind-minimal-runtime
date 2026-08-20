from pathlib import Path
import tempfile

import conftest as test_config


def test_pytest_unconfigure_cleans_test_data_root(monkeypatch):
    test_data_root = tempfile.TemporaryDirectory(prefix="processmind-cleanup-test-")
    test_data_path = Path(test_data_root.name)
    monkeypatch.setattr(test_config, "_TEST_DATA_ROOT", test_data_root)

    test_config.pytest_unconfigure(None)

    assert not test_data_path.exists()
