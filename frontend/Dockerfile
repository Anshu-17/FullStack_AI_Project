# Streamlit UI. Talks to the backend at $API_URL.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.lock.txt .
RUN pip install -r requirements.lock.txt
COPY . .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.headless=true", "--server.address=0.0.0.0", "--server.port=8501"]
