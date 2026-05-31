FROM python:3.11-slim

WORKDIR /app

COPY jobs/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY readnews.py .
COPY jobs/job.py .
COPY prompts/ prompts/

CMD ["python", "job.py"]
