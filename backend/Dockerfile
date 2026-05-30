# Backend image: bundles ffmpeg (for non-WAV decoding) + the Python pipeline.
FROM python:3.11-slim

# ffmpeg is the decoder for compressed audio (mp3/m4a/webm/...).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Recent-but-<81 build tools: new enough to build pretty_midi's legacy setup.py,
# old enough to retain pkg_resources (needed at runtime by resampy).
RUN pip install --no-cache-dir --upgrade pip wheel "setuptools<81"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
