# Backend image: bundles ffmpeg (for non-WAV decoding) + the uv-managed Python app.
FROM python:3.11-slim

# ffmpeg is the decoder for compressed audio (mp3/m4a/webm/...).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv: fast, reproducible Python package management.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies from the lockfile first (cached unless deps change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY README.md ./

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
