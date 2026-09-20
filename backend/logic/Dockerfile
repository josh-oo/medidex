# Main app
FROM python:3.13.11-slim

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

COPY logic/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY logic/main.py .
COPY logic/src/ ./src/
COPY logic/src_agent/ ./src_agent/
COPY app-init/placeholder.pdf /app/placeholder.pdf

ARG APP_UID=1000
ARG APP_GID=1000

RUN mkdir -p /data/resources/pdf_metadata
RUN mkdir -p /data/resources/pdfs
RUN chown -R appuser:appgroup /data/resources

# Switch to the non-root user before running the application
USER appuser

# uvicorn main:app --host 0.0.0.0 --port 8002
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]