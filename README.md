# NewsSummary

News aggregation and analysis application.

## Components

- **Job** (`jobs/`) — Cloud Run Job. Fetches RSS feeds, rates each story with
  Gemini, sorts by priority, generates a market report, writes `news.json` and
  `report.json` to GCS.
- **API** (`api/`) — Cloud Run Service. FastAPI. Reads from GCS and serves
  `/v1/news`, `/v1/report`, and `/v1/health`.
- **Frontend** (`frontend/`) — Static HTML/CSS/JS. Served from GCS.

## Environment Variables

| Variable                    | Used By  | Description                                      |
|-----------------------------|----------|--------------------------------------------------|
| `GCS_BUCKET_NAME`           | job, api | GCS bucket name for data blobs                   |
| `GEMINI_API_KEY`            | job      | Google Gemini API key                            |
| `FRONTEND_ORIGIN`           | api      | Allowed CORS origin, e.g. https://mydomain.news  |
| `CACHE_TTL_SECONDS`         | api      | In-memory cache TTL in seconds (default: 300)    |
| `SUMMARY_PRIORITY_THRESHOLD`| job      | Minimum priority score for summarization (default: 60) |

## Local Development

Copy `.env.example` to `.env` and fill in values. Then:

```bash
# Run the job locally
cd mynews
python jobs/job.py

# Run the API locally
cd api
uvicorn main:app --reload --port 8080
```

## GCP Deployment

### 1. Create the data bucket
```bash
gsutil mb -l us-central1 gs://YOUR_BUCKET_NAME
```

### 2. Deploy the job
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/mynews-job --dockerfile jobs/Dockerfile .
gcloud run jobs create mynews-job \
  --image gcr.io/YOUR_PROJECT/mynews-job \
  --region us-central1 \
  --set-env-vars GCS_BUCKET_NAME=YOUR_BUCKET,GEMINI_API_KEY=YOUR_KEY
```

### 3. Deploy the API
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/mynews-api --dockerfile api/Dockerfile .
gcloud run deploy mynews-api \
  --image gcr.io/YOUR_PROJECT/mynews-api \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GCS_BUCKET_NAME=YOUR_BUCKET,FRONTEND_ORIGIN=https://mydomain.news
```

### 4. Schedule the job
```bash
gcloud scheduler jobs create http mynews-cron \
  --schedule "*/15 * * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT/jobs/mynews-job:run" \
  --message-body "{}" \
  --oauth-service-account-email YOUR_SA@YOUR_PROJECT.iam.gserviceaccount.com \
  --location us-central1
```

### 5. Deploy the frontend
```bash
gsutil mb -l us-central1 gs://mydomain.news
gsutil web set -m index.html gs://mydomain.news
gsutil iam ch allUsers:objectViewer gs://mydomain.news
gsutil cp frontend/index.html gs://mydomain.news/
```

### 6. Run the job once to populate GCS before the first scheduled run
```bash
gcloud run jobs execute mynews-job --region us-central1
```

## Service Account Permissions

The job and API containers require the `Storage Object Admin` role on the data
bucket. The Cloud Scheduler service account requires the `Cloud Run Invoker`
role on the job. Configure both in IAM before the first deployment.

## Prompts

Gemini prompts are stored in `prompts/` as Markdown files. Edit them to tune
rating criteria or report style without modifying Python source.

- `prompts/rate_entry.md` — system prompt for per-story rating
- `prompts/summarize.md`  — system prompt for the market report
