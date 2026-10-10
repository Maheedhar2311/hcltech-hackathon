# One image for both services (API and UI). docker-compose.yml chooses the command.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

# CPU-only PyTorch first (sentence-transformers needs it; the CPU wheel is much smaller than the CUDA one).
RUN pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY data/documents ./data/documents

ENV PYTHONPATH=/app/src

EXPOSE 8000 8501
