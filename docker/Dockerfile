FROM python:3.14-slim

# Build arguments for versioning
ARG VERSION=dev
ARG BUILD_DATE
ARG VCS_REF

# OCI Image labels
LABEL org.opencontainers.image.title="Shelly Pro 3EM Emulator"
LABEL org.opencontainers.image.description="Shelly Pro 3EM Emulator for Marstek storage systems"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.source="https://github.com/bvweerd/shelly-emulator"
LABEL org.opencontainers.image.licenses="MIT"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create config directory (user mounts their config here)
RUN mkdir -p /app/config

# Expose ports
# Modbus TCP
EXPOSE 502
# UDP JSON-RPC (old and new firmware)
EXPOSE 1010/udp
EXPOSE 2220/udp
# HTTP API
EXPOSE 80

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/app/config/config.yaml
ENV VERSION=${VERSION}

# Health check - verifies at least one server is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -m src.health

# Run the emulator
CMD ["python", "-m", "src.main"]
