#!/bin/bash
set -e

echo "============================================================"
echo "🚀 AI TRADING BOT v3.4.0"
echo "📊 Super TDI + Super Bollinger Bands Strategy"
echo "============================================================"
echo "Environment: ${ENVIRONMENT:-development}"
echo "Run Mode: ${RUN_MODE:-DEMO}"
echo "============================================================"

# Create directories
mkdir -p /app/logs /app/data /app/backups

# Start the application
exec python -u main.py
