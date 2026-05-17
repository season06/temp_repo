import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Patch cx_Oracle before importing main
mock_pool = MagicMock()
mock_conn = MagicMock()
mock_cursor = MagicMock()
mock_pool.acquire.return_value = mock_conn
mock_conn.cursor.return_value = mock_cursor

with patch.dict("sys.modules", {"cx_Oracle": MagicMock(SessionPool=MagicMock(return_value=mock_pool))}):
    from main import app  # noqa: E402

client = TestClient(app)


def test_query_returns_rows():
    mock_cursor.description = [("NAME",), ("STATUS",)]
    mock_cursor.fetchall.return_value = [("cpnt_a", "ACTIVE"), ("cpnt_b", "INACTIVE")]

    resp = client.post("/query", json={"sql": "SELECT name, status FROM cpnt", "params": {}})

    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == ["name", "status"]
    assert data["rows"][0] == {"name": "cpnt_a", "status": "ACTIVE"}


def test_query_db_error_returns_400():
    import cx_Oracle as mock_cx
    mock_cursor.execute.side_effect = mock_cx.DatabaseError("ORA-00942: table or view does not exist")

    resp = client.post("/query", json={"sql": "SELECT * FROM no_such_table", "params": {}})

    assert resp.status_code == 400
    mock_cursor.execute.side_effect = None  # reset


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
