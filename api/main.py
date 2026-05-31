import json
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage

load_dotenv()

BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", 300))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["GET"],
)

_cache = {
    "news": {"data": None, "fetched_at": 0.0},
    "report": {"data": None, "fetched_at": 0.0},
}


def read_blob(blob_name: str, cache_key: str):
    now = time.time()
    entry = _cache[cache_key]
    if entry["data"] is None or (now - entry["fetched_at"]) > CACHE_TTL:
        gcs = storage.Client()
        blob = gcs.bucket(BUCKET_NAME).blob(blob_name)
        if not blob.exists():
            raise HTTPException(
                status_code=503,
                detail=f"{blob_name} not yet available."
            )
        entry["data"] = json.loads(blob.download_as_text())
        entry["fetched_at"] = now
    return entry["data"]


@app.get("/v1/news")
def get_news():
    data = read_blob("news.json", "news")
    return {"status": "ok", "count": len(data), "data": data}


@app.get("/v1/report")
def get_report():
    data = read_blob("report.json", "report")
    return {"status": "ok", "report": data.get("report", "")}


@app.get("/v1/health")
def health():
    return {"status": "ok"}
