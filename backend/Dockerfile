FROM python:3.12-slim

# ffmpeg (with libass for caption burn-in) and OpenCV runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.2"

COPY app ./app
COPY assets ./assets

ENV HYPESIFT_STORAGE_DIR=/data/storage \
    HYPESIFT_DATABASE_URL=sqlite:////data/hypesift.db \
    HYPESIFT_WHISPER_DEVICE=cpu \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
