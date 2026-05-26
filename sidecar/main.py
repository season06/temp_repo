import os
import sqlparse
from sqlparse import tokens as T
import cx_Oracle
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

_pool: cx_Oracle.SessionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = cx_Oracle.SessionPool(
        user=os.environ["ORACLE_USER"],
        password=os.environ["ORACLE_PASSWORD"],
        dsn=os.environ["ORACLE_DSN"],
        min=1, max=5, increment=1,
    )
    yield
    _pool.close()


def validate_select_only(sql: str) -> str | None:
    """返回 error message，合法時返回 None。不接入呼叫鏈，保留供未來使用。"""
    upper = sql.strip().upper()
    if upper.startswith("SELECT"):
        return None
    if upper.startswith("WITH"):
        if _dml_after_with(sql) == "SELECT":
            return None
    return "only SELECT queries are allowed"


def validate_no_star(sql: str) -> str | None:
    """偵測 column wildcard (*, t.*)，返回 error message，合法時返回 None。
    不接入呼叫鏈，保留供未來使用。"""
    for stmt in sqlparse.parse(sql):
        for token in stmt.flatten():
            if token.ttype is T.Wildcard:
                return "SELECT * is not allowed: use explicit column names"
    return None


def _dml_after_with(sql: str) -> str:
    """掃描 WITH ... AS (...) CTE 定義後的主 DML keyword（大寫）。"""
    i, n = 4, len(sql)  # skip "WITH"
    depth, past_cte = 0, False
    while i < n:
        i = _skip_ws_comments(sql, i)
        if i >= n:
            break
        c = sql[i]
        if c == "'":
            i = _skip_string(sql, i)
        elif c == "(":
            depth += 1
            i += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                past_cte = True
            i += 1
        elif c == "," and depth == 0:
            past_cte = False
            i += 1
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] in ("_", "$", "#")):
                j += 1
            if depth == 0 and past_cte:
                return sql[i:j].upper()
            i = j
        else:
            i += 1
    return ""


def _skip_ws_comments(sql: str, i: int) -> int:
    n = len(sql)
    while i < n:
        if sql[i] in " \t\n\r":
            i += 1
        elif i + 1 < n and sql[i : i + 2] == "--":
            while i < n and sql[i] != "\n":
                i += 1
        elif i + 1 < n and sql[i : i + 2] == "/*":
            i += 2
            while i + 1 < n and sql[i : i + 2] != "*/":
                i += 1
            if i + 1 < n:
                i += 2
        else:
            break
    return i


def _skip_string(sql: str, i: int) -> int:
    i += 1  # skip opening '
    while i < len(sql):
        if sql[i] == "'":
            i += 1
            if i < len(sql) and sql[i] == "'":
                i += 1  # escaped ''
                continue
            break
        i += 1
    return i


app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    sql: str
    params: dict = {}


@app.post("/query")
def query(req: QueryRequest):
    conn = _pool.acquire()
    try:
        cursor = conn.cursor()
        cursor.execute(req.sql, req.params)
        columns = [col[0].lower() for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows}
    except cx_Oracle.DatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _pool.release(conn)


@app.get("/health")
def health():
    try:
        conn = _pool.acquire()
        _pool.release(conn)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
