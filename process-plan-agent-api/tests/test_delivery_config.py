from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_docker_context_and_web_copy_are_restricted():
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for required in (
        ".git",
        ".runtime",
        "data",
        "**/node_modules",
        "**/dist",
        ".env",
        "**/process_settings.json",
    ):
        assert required in dockerignore

    dockerfile = (PROJECT_ROOT / "Dockerfile.web").read_text(encoding="utf-8")
    assert "COPY process-plan-agent-ui /app" not in dockerfile
    assert "COPY process-plan-agent-ui/src /app/src" in dockerfile
    assert "COPY process-plan-agent-ui/public /app/public" in dockerfile


def test_param_question_strategy_is_shared_across_delivery_targets():
    shared_path = PROJECT_ROOT / "docs" / "配置模板" / "第五步参数问答策略.json"
    assert shared_path.is_file()
    assert shared_path.read_text(encoding="utf-8").find('"version": "1.0.0"') >= 0
    assert not (
        PROJECT_ROOT
        / "process-plan-agent-ui"
        / "src"
        / "config"
        / "paramQuestionStrategy.json"
    ).exists()

    api_dockerfile = (PROJECT_ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    web_dockerfile = (PROJECT_ROOT / "Dockerfile.web").read_text(encoding="utf-8")
    assert "COPY docs/配置模板/第五步参数问答策略.json /app/docs/配置模板/第五步参数问答策略.json" in api_dockerfile
    assert "COPY docs/配置模板/第五步参数问答策略.json /docs/配置模板/第五步参数问答策略.json" in web_dockerfile

    frontend_strategy = (
        PROJECT_ROOT / "process-plan-agent-ui" / "src" / "config" / "paramQuestionStrategy.ts"
    ).read_text(encoding="utf-8")
    assert "../../../docs/配置模板/第五步参数问答策略.json" in frontend_strategy


def test_delivery_uses_locked_dependencies_and_current_scripts():
    root_requirements = (PROJECT_ROOT / "requirement.txt").read_text(encoding="utf-8")
    api_requirements = (
        PROJECT_ROOT / "process-plan-agent-api" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert api_requirements == root_requirements
    assert ">=" not in api_requirements

    bootstrap = (PROJECT_ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    assert 'pip install -r "$ROOT_DIR/requirement.txt"' in bootstrap
    assert "npm ci" in bootstrap
    assert "npm install" not in bootstrap

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "start-macos.command" not in readme
    assert "stop-macos.command" not in readme
    assert "processmind-minimal-runtime-20260709" not in readme
    assert "OFFLINE-DEPLOY.md" not in readme


def test_compose_forwards_runtime_configuration():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for key in (
        "DATABASE_URL",
        "KNOWLEDGE_SEARCH_PROVIDER",
        "KNOWLEDGE_SEARCH_API_URL",
        "KNOWLEDGE_SEARCH_API_KEY",
        "PROCESSMIND_KMAI_MAX_COMBINATIONS",
        "PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS",
    ):
        assert f"{key}:" in compose

    env_example = (PROJECT_ROOT / ".env.compose.example").read_text(encoding="utf-8")
    assert "sqlite+aiosqlite:////runtime-data/db/process_mind.db" in env_example
