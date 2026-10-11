FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + schemes + the prebuilt index (data/index) are baked into the image,
# so no persistent disk or ingestion step is needed at runtime.
COPY app ./app
COPY data ./data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
