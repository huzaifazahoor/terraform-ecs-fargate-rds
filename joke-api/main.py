import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I told my computer I needed a break. It said: no problem, I'll go to sleep.",
    "There are 10 kinds of people: those who know binary and those who don't.",
    "Why did the developer go broke? He used up all his cache.",
    "A SQL query walks into a bar, sees two tables, and asks: can I join you?",
]


def get_conn():
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


@asynccontextmanager
async def lifespan(app):
    with get_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS jokes (id SERIAL PRIMARY KEY, text TEXT NOT NULL)")
        if conn.execute("SELECT COUNT(*) FROM jokes").fetchone()[0] == 0:
            for joke in JOKES:
                conn.execute("INSERT INTO jokes (text) VALUES (%s)", (joke,))
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/joke")
def joke():
    with get_conn() as conn:
        row = conn.execute("SELECT text FROM jokes ORDER BY random() LIMIT 1").fetchone()
    return {"joke": row[0]}