# Multi-stage build for efficient Docker image

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Copy requirements and application code
COPY pyproject.toml setup.py* ./
COPY src/ ./src/
RUN pip install --no-cache-dir --user --no-deps -e .

# Stage 2: Runtime
FROM python:3.11-slim

LABEL maintainer="Development Team"
LABEL description="Gmail-to-Sheets MT940 Pipeline"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    TIMEZONE=Europe/Lisbon

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser .env.example ./.env.example

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/credentials /app/data && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add local pip packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.gmail_to_sheets.config.settings import load_settings; load_settings()" || exit 1

# Run application
CMD ["python", "-m", "src.gmail_to_sheets"]
