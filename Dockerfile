FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p logs data backups

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5)" || exit 1

# Expose port
EXPOSE 8080

# Run
ENTRYPOINT ["./entrypoint.sh"]
