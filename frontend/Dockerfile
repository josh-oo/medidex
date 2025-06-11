FROM python:3.13-alpine

ENV STREAMLIT_HOME /tmp/streamlit

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Copy the rest of the app
COPY . .
RUN mv .env.production .env

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "Home.py", "--server.port=8501", "--server.address=0.0.0.0"]