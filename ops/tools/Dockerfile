#Main app
FROM python:3.13.11-slim

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY scripts/ .

# Switch to the non-root user before running the application
USER appuser