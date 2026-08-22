FROM python:3.11-slim

WORKDIR /app

# ============================================================
# ✅ Install system dependencies for scipy and numpy
# ============================================================
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    python3-dev \
    libatlas-base-dev \
    libblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Copy requirements and install
# ============================================================
COPY requirements.txt .

# ✅ Install scipy first (it's the largest, install separately for cache)
RUN pip install --no-cache-dir numpy
RUN pip install --no-cache-dir scipy
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
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Run the bot
CMD ["python", "main.py"]
