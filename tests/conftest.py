import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAWCARE_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    from backend.main import app
    with TestClient(app) as c:
        yield c


MORNING, AFTERNOON, ADMIN, OTHER_ORG = ({"X-Staff-Id": str(i)} for i in (1, 2, 3, 4))
