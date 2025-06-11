FROM python:3.11-alpine

RUN addgroup -S appgroup && adduser -S -G appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

RUN apk update && apk add --no-cache curl

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY database.py .
COPY .env.production .env

EXPOSE 8001

# Switch to the non-root user before running the application
USER appuser

#uvicorn database:app --host 0.0.0.0 --port 8001
ENTRYPOINT ["uvicorn", "database:app", "--host", "0.0.0.0", "--port", "8001"]