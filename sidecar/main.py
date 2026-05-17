import os
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
