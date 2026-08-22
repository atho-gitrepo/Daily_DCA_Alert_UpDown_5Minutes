FROM python:3.11-slim

WORKDIR /app

# Minimal dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# ============================================================
# ✅ PINNED FIX: Install all pinned versions
# ============================================================
RUN pip install --no-cache-dir -r requirements.txt

# Force numpy to the correct version (in case any dependency tries to upgrade)
RUN pip install --force-reinstall --no-deps numpy==1.24.3

# Copy application code
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
