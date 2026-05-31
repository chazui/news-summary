# NewsSummary

News aggregation and analysis application. Fetches RSS feeds from Bloomberg and NYT, rates each story using Gemini, generates a market report, and serves results via a FastAPI backend to a static frontend.

## Components

- **Job** (`jobs/`) — Cloud Run Job. Fetches RSS feeds, rates each story with Gemini, sorts by priority, generates a market report, writes `news.json` and `report.json` to GCS.
- **API** (`api/`) — Cloud Run Service. FastAPI. Reads from GCS and serves `/v1/news`, `/v1/report`, and `/v1/health`.
- **Frontend** (`frontend/`) — Static HTML/CSS/JS. Served from a public GCS bucket.

## Environment Variables

| Variable            | Used By  | Description                                               |
|---------------------|----------|-----------------------------------------------------------|
| `GCS_BUCKET_NAME`   | job, api | GCS bucket name for data blobs                            |
| `GEMINI_API_KEY`    | job      | Google Gemini API key (stored in Secret Manager)          |
| `FRONTEND_ORIGIN`   | api      | Allowed CORS origin, e.g. https://storage.googleapis.com  |
| `CACHE_TTL_SECONDS` | api      | In-memory cache TTL in seconds (default: 300)             |

## Local Development

Copy `.env.example` to `.env` and fill in values. Then:

```bash
# Run the job locally
cd news-summary
python jobs/job.py

# Run the API locally
cd api
uvicorn main:app --reload --port 8080
```

## Prompts

Gemini prompts are stored in `prompts/` as Markdown files. Edit them to tune
rating criteria or report style without modifying Python source. No rebuild
required — prompts are read from disk at runtime.

- `prompts/rate_entry.md` — system prompt for per-story batch rating
- `prompts/summarize.md`  — system prompt for the market report

---

## GCP Deployment

### Prerequisites

- GCP project with billing enabled and **No organization** selected at creation
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Project set as active (`gcloud config set project YOUR_PROJECT_ID`)
- Gemini API key obtained from Google AI Studio

### 1. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com
```

### 2. Create the data bucket

```bash
gcloud storage buckets create gs://YOUR_PROJECT_ID-data \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### 3. Store the Gemini API key in Secret Manager

```bash
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create GEMINI_API_KEY \
  --data-file=- \
  --replication-policy=automatic
```

### 4. Grant service account permissions

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:$SA --role=roles/storage.admin

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:$SA --role=roles/logging.logWriter

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:$SA --role=roles/artifactregistry.repoAdmin

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:$SA --role=roles/run.invoker

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=user:YOUR_GMAIL_ACCOUNT \
  --role=roles/cloudbuild.builds.editor
```

### 5. Create Artifact Registry repository

```bash
gcloud artifacts repositories create cloud-run-source-deploy \
  --repository-format=docker \
  --location=us-central1 \
  --description="Cloud Run container images"
```

### 6. Create cloudbuild.yaml for the job

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '--no-cache', '-f', 'jobs/Dockerfile', '-t', 'us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-job', '.']
images:
  - 'us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-job'
```

### 7. Build and deploy the job

Run from the project root directory:

```bash
gcloud builds submit . --config cloudbuild.yaml

gcloud run jobs create news-summary-job \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-job \
  --region us-central1 \
  --set-env-vars GCS_BUCKET_NAME=YOUR_PROJECT_ID-data \
  --update-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest
```

### 8. Run the job once to populate GCS

```bash
gcloud run jobs execute news-summary-job --region us-central1
```

Confirm output files were written:

```bash
gcloud storage ls gs://YOUR_PROJECT_ID-data/
```

You should see `news.json` and `report.json`.

### 9. Update cloudbuild.yaml for the API

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '--no-cache', '-f', 'api/Dockerfile', '-t', 'us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-api', '.']
images:
  - 'us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-api'
```

### 10. Build and deploy the API

```bash
gcloud builds submit . --config cloudbuild.yaml

gcloud run deploy news-summary-api \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-api \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GCS_BUCKET_NAME=YOUR_PROJECT_ID-data,FRONTEND_ORIGIN=https://storage.googleapis.com
```

Get the service URL:

```bash
gcloud run services describe news-summary-api \
  --region us-central1 \
  --format "value(status.url)"
```

Grant public access:

```bash
gcloud run services add-iam-policy-binding news-summary-api \
  --region us-central1 \
  --member=allUsers \
  --role=roles/run.invoker
```

Verify:

```bash
curl YOUR_SERVICE_URL/v1/health
```

### 11. Schedule the job

```bash
gcloud scheduler jobs create http news-summary-cron \
  --schedule "0 6-19 * * *" \
  --time-zone "America/Chicago" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT_ID/jobs/news-summary-job:run" \
  --message-body "{}" \
  --oauth-service-account-email $(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")-compute@developer.gserviceaccount.com \
  --location us-central1
```

### 12. Deploy the frontend

Update `API_BASE` in `frontend/index.html` to your Cloud Run service URL, then:

```bash
gcloud storage buckets create gs://YOUR_FRONTEND_BUCKET \
  --location=us-central1 \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://YOUR_FRONTEND_BUCKET \
  --member=allUsers \
  --role=roles/storage.objectViewer

gcloud storage cp frontend/index.html gs://YOUR_FRONTEND_BUCKET/
```

Frontend is accessible at:

```
https://storage.googleapis.com/YOUR_FRONTEND_BUCKET/index.html
```

## Updating the Frontend

No rebuild required. Edit `frontend/index.html` then:

```bash
gcloud storage cp frontend/index.html gs://YOUR_FRONTEND_BUCKET/
```

Hard refresh the browser (Cmd+Shift+R / Ctrl+Shift+R) to bypass cache.

## Updating the Job

After editing any file in `jobs/` or `prompts/`:

```bash
# Update cloudbuild.yaml to point at the job image, then:
gcloud builds submit . --config cloudbuild.yaml

gcloud run jobs update news-summary-job \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-job \
  --region us-central1

gcloud run jobs execute news-summary-job --region us-central1
```

## Updating the API

After editing `api/main.py`:

```bash
# Update cloudbuild.yaml to point at the API image, then:
gcloud builds submit . --config cloudbuild.yaml

gcloud run services update news-summary-api \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/news-summary-api \
  --region us-central1
```

## Viewing Logs

```bash
# Job logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=news-summary-job" \
  --limit 100 \
  --format "value(timestamp,textPayload,jsonPayload.message)" \
  --order desc \
  --project YOUR_PROJECT_ID

# API logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=news-summary-api" \
  --limit 50 \
  --format "value(timestamp,textPayload,jsonPayload.message)" \
  --order desc \
  --project YOUR_PROJECT_ID
```

## Notes

- Create the GCP project with **No organization** to avoid IAM policy restrictions on public access
- Always run `gcloud builds submit` from the project root directory where `jobs/`, `api/`, and `readnews.py` are visible
- The `cloudbuild.yaml` must be updated to point at the correct image (job or API) before each build
- Use `--no-cache` in `cloudbuild.yaml` to guarantee the latest source files are included in the image
- The Cloud Run service URL is assigned at deploy time — retrieve it with `gcloud run services describe` rather than assuming a format
- `SUMMARY_PRIORITY_THRESHOLD` has been removed; the job now sends the top 20 stories by priority score to the summarization agent