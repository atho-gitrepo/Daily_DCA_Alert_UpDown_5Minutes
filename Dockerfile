FROM python:3.11-slim-bullseye

WORKDIR /app

# ============================================================
# ✅ Install system dependencies for scipy (Bullseye has all packages)
# ============================================================
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    python3-dev \
    libatlas-base-dev \
    libblas-dev \
    liblapack-dev \
    libopenblas-dev \
    libgfortran5 \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Copy requirements and install
# ============================================================
COPY requirements.txt .

# ✅ Install scipy with pre-built wheels when possible
RUN pip install --no-cache-dir numpy==1.24.3
RUN pip install --no-cache-dir scipy>=1.10.0
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================
# Copy application code
# ============================================================
COPY . .

# Create directories
RUN mkdir -p logs data backups models

# Expose ports
EXPOSE 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Run the bot
CMD ["python", "main.py"]
