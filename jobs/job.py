import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.cloud import storage

load_dotenv()

sys.path.append(str(Path(__file__).parent.parent))
import readnews

BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PROMPTS_DIR = Path(__file__).parent / "prompts"
MODEL = "models/gemini-2.5-flash"
SUMMARY_PRIORITY_THRESHOLD = int(os.environ.get("SUMMARY_PRIORITY_THRESHOLD", 60))

client = genai.Client(api_key=GEMINI_API_KEY)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def rate_entry(entry: dict, system_prompt: str) -> dict:
    response = client.models.generate_content(
        model=MODEL,
        contents=json.dumps(entry),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    print(f"RAW RESPONSE: {response.text}")
    ratings = json.loads(response.text) #type: ignore
    return {**entry, **ratings}

def rate_all(entries: list[dict]) -> list[dict]:
    print(f"Rating {len(entries)} entries in one batch...")
    system_prompt = load_prompt("rate_entry")
    response = client.models.generate_content(
        model=MODEL,
        contents=json.dumps(entries),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    print(f"RAW RESPONSE: {response.text[:500]}")
    ratings = json.loads(response.text)
    rated = []
    for entry, rating in zip(entries, ratings):
        try:
            rated.append({**entry, **rating})
        except Exception:
            rated.append({**entry, "priority": 0, "breadth": "none", "rationale": ""})
    return rated

def sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda x: x.get("priority", 0), reverse=True)


def summarize(entries: list[dict], top_n: int = 20) -> str:
    candidates = entries[:top_n]  # already sorted by priority descending
    if not candidates:
        return "No stories available for summarization."
    system_prompt = load_prompt("summarize")
    response = client.models.generate_content(
        model=MODEL,
        contents=json.dumps(candidates),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
        ),
    )
    return response.text #type: ignore

def write_to_gcs(data: str, blob_name: str):
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    bucket.blob(blob_name).upload_from_string(data, content_type="application/json")
    print(f"Wrote {blob_name} to gs://{BUCKET_NAME}/")


def run():
    print("Fetching feeds...")
    raw_json = readnews.run()
    entries = json.loads(raw_json)

    print(f"Rating {len(entries)} entries...")
    rated = rate_all(entries)

    print("Sorting by priority...")
    sorted_entries = sort_entries(rated)

    print("Generating report...")
    report = summarize(sorted_entries)

    print("Writing to GCS...")
    write_to_gcs(json.dumps(sorted_entries), "news.json")
    write_to_gcs(json.dumps({"report": report}), "report.json")

    print("Done.")


if __name__ == "__main__":
    run()
