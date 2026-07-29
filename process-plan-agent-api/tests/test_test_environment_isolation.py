from app.core.paths import DEFAULT_DB_PATH, PROJECT_ROOT, UPLOAD_DIR


def test_pytest_never_uses_repository_production_data_directory():
    production_data_dir = (PROJECT_ROOT / "data").resolve()

    assert production_data_dir not in DEFAULT_DB_PATH.resolve().parents
    assert production_data_dir not in UPLOAD_DIR.resolve().parents
