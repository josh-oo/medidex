FROM python:3.13.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=off \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

COPY requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip \
	&& pip install --no-cache-dir -r requirements.txt

COPY ./ ./backend/

EXPOSE 8001

ENTRYPOINT ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]