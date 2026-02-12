FROM python:3.13.11-slim

#ENV STREAMLIT_SERVER_HEADLESS=true
ENV PYTHONDONTWRITEBYTECODE 1

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

RUN mkdir -p /home/appuser/.streamlit && \
    cat <<EOF > /home/appuser/.streamlit/config.toml
[server]
enableCORS = false
enableXsrfProtection = false
headless = true
port = 8501
address = "0.0.0.0"
EOF
RUN chown -R appuser:appgroup /home/appuser

EXPOSE 8501

# Switch to the non-root user before running the application
USER appuser

ENTRYPOINT ["streamlit", "run", "Home.py", "--server.port=8501", "--server.address=0.0.0.0"]
