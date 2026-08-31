from fastapi.testclient import TestClient

from app.main import app


def test_local_alternate_vite_port_can_preflight_project_creation():
    with TestClient(app) as client:
        response = client.options(
            "/api/projects/",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5174"
