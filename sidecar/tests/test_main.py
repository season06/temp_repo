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
    from main import app, validate_select_only, validate_no_star  # noqa: E402

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


# --- validate_select_only ---

def test_validate_select_only_valid():
    assert validate_select_only("SELECT id FROM cpnt") is None
    assert validate_select_only("select name FROM sop WHERE id = :id") is None
    assert validate_select_only("  \n  SELECT col FROM tbl") is None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte") is None
    assert validate_select_only("WITH cte AS (SELECT id FROM cpnt) SELECT id FROM cte") is None


def test_validate_select_only_invalid():
    assert validate_select_only("INSERT INTO cpnt VALUES (1)") is not None
    assert validate_select_only("UPDATE cpnt SET name = 'x'") is not None
    assert validate_select_only("DELETE FROM cpnt") is not None
    assert validate_select_only("DROP TABLE cpnt") is not None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) DELETE FROM cpnt") is not None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) UPDATE cpnt SET name = 'x'") is not None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) INSERT INTO cpnt VALUES (1)") is not None


# --- validate_no_star ---

def test_validate_no_star_valid():
    assert validate_no_star("SELECT id, name FROM cpnt") is None
    assert validate_no_star("SELECT price * 2 FROM tbl") is None
    assert validate_no_star("SELECT (a+b) * c FROM tbl") is None
    assert validate_no_star("SELECT a * b FROM tbl") is None


def test_validate_no_star_invalid():
    assert validate_no_star("SELECT * FROM cpnt") is not None
    assert validate_no_star("SELECT t.* FROM cpnt t") is not None
    assert validate_no_star("SELECT COUNT(*) FROM cpnt") is not None
    assert validate_no_star("SELECT *, id FROM cpnt") is not None
    assert validate_no_star("SELECT col FROM (SELECT * FROM tbl)") is not None
    assert validate_no_star("WITH cte AS (SELECT * FROM t) SELECT id FROM cte") is not None
    assert validate_no_star("WITH cte AS (SELECT t.* FROM t) SELECT id FROM cte") is not None
