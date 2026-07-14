"""
统一管理项目级路径，避免各模块自行拼接目录。
"""
from __future__ import annotations

import os
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_DB_PATH = API_ROOT / "process_mind.db"
LEGACY_UPLOAD_DIR = API_ROOT / "uploads"
LEGACY_SETTINGS_FILE = API_ROOT / "process_settings.json"

DATA_DIR = Path(os.getenv("PROCESSMIND_DATA_DIR", str(PROJECT_ROOT / "data")))
DB_DIR = DATA_DIR / "db"
CONFIG_DIR = DATA_DIR / "config"

_default_db_path = LEGACY_DB_PATH if LEGACY_DB_PATH.exists() else (DB_DIR / "process_mind.db")
DEFAULT_DB_PATH = Path(os.getenv("PROCESSMIND_DB_PATH", str(_default_db_path)))

_default_upload_dir = LEGACY_UPLOAD_DIR if LEGACY_UPLOAD_DIR.exists() else (DATA_DIR / "uploads")
UPLOAD_DIR = Path(os.getenv("PROCESSMIND_UPLOAD_DIR", str(_default_upload_dir)))

KNOWLEDGE_DIR = API_ROOT / "knowledge"
ROUTE_RULE_KNOWLEDGE_DIR = KNOWLEDGE_DIR / "route_rules"
PROMPT_TEMPLATES_PATH = API_ROOT / "prompt_templates.md"
THIRD_STEP_RULE_TREE_PATH = PROJECT_ROOT / "docs" / "配置模板" / "第三步规则分析-问题树节点配置.template.json"

_default_settings_path = (
    LEGACY_SETTINGS_FILE if LEGACY_SETTINGS_FILE.exists() else (CONFIG_DIR / "process_settings.json")
)
SETTINGS_FILE_PATH = Path(os.getenv("PROCESSMIND_SETTINGS_PATH", str(_default_settings_path)))
