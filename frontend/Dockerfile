FROM python:3.13-alpine

#ENV STREAMLIT_SERVER_HEADLESS=true
ENV PYTHONDONTWRITEBYTECODE 1

RUN addgroup -S appgroup && adduser -S -G appgroup appuser

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .
RUN mv .env.production .env

EXPOSE 8501

# Switch to the non-root user before running the application
USER appuser

ENTRYPOINT ["streamlit", "run", "Home.py", "--server.port=8501", "--server.address=0.0.0.0"]