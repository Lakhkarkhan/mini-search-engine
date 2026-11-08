FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INDEX_PATH=/data/index.json.gz

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY minisearch ./minisearch

# Run as a non-root user; /data holds the saved index
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser

EXPOSE 8000
CMD ["uvicorn", "minisearch.api:app", "--host", "0.0.0.0", "--port", "8000"]
