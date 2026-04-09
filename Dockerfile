FROM python:3.12-slim

WORKDIR /app

# Install supercronic and ffmpeg (needed by yt-dlp for merging streams)
ARG SUPERCRONIC_VERSION=0.2.33
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates ffmpeg \
    && ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-${ARCH}" \
       -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py config.py models.py ./
COPY utils/ ./utils/
COPY services/ ./services/
COPY crontab /app/crontab

# Ensure crontab has Unix line endings
RUN sed -i 's/\r$//' /app/crontab

# Create cache and temp directories
RUN mkdir -p /app/.cache /tmp/viewstats

CMD ["supercronic", "/app/crontab"]
