from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_production_app_serves_index_assets_and_history_routes(tmp_path: Path):
    frontend_dir = tmp_path / "frontend"
    assets_dir = frontend_dir / "assets"
    assets_dir.mkdir(parents=True)
    index_html = '<!doctype html><html><body><div id="app">ProcessMind</div></body></html>'
    (frontend_dir / "index.html").write_text(index_html, encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = create_app(frontend_dir)

    with TestClient(app) as client:
        root = client.get("/")
        history_route = client.get("/extract", headers={"accept": "text/html"})
        asset = client.get("/assets/app.js")
        ping = client.get("/api/startup-ping")

    assert root.status_code == 200
    assert root.text == index_html
    assert history_route.status_code == 200
    assert history_route.text == index_html
    assert asset.status_code == 200
    assert asset.text == "console.log('ok')"
    assert ping.status_code == 200
    assert ping.json() == {"status": "ok", "app": "ProcessMind", "kind": "api"}


def test_spa_fallback_does_not_hide_missing_api_or_static_assets(tmp_path: Path):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<html>ProcessMind</html>", encoding="utf-8")
    app = create_app(frontend_dir)

    with TestClient(app) as client:
        responses = [
            client.get("/api/this-endpoint-does-not-exist"),
            client.get("/api/this-endpoint-does-not-exist", headers={"accept": "text/html"}),
            client.get("/assets/this-chunk-does-not-exist.js"),
            client.get("/assets/this-chunk-does-not-exist.js", headers={"accept": "text/html"}),
            client.get("/this-chunk-does-not-exist.js", headers={"accept": "text/html"}),
            client.get("/route-that-does-not-exist", headers={"accept": "*/*"}),
        ]

    assert [response.status_code for response in responses] == [404] * len(responses)
    assert all(response.headers["content-type"].startswith("application/json") for response in responses[:2])


def test_api_root_keeps_json_response_without_production_frontend():
    app = create_app(None)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["service"] == "ProcessMind API"
