# Backend image. Default command (start.sh) = migrations + seed + worker (background) + API on $PORT,
# for a single free Render web service. docker-compose.yml overrides the command to run the API and the
# worker as two separate services locally.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock.txt .
RUN pip install -r requirements.lock.txt

COPY . .
# Strip Windows line endings in case the file was edited on Windows, then make it executable.
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "./start.sh"]
