#!/bin/bash
# ============================================================
# ENTRYPOINT SCRIPT - Trading Bot Startup
# ============================================================

set -e

echo "============================================================"
echo "🚀 AI TRADING BOT v3.4.0 - Super TDI Strategy"
echo "============================================================"
echo "Environment: ${ENVIRONMENT:-development}"
echo "Run Mode: ${RUN_MODE:-DEMO}"
echo "Port: ${PORT:-8080}"
echo "============================================================"

# ============================================================
# 1. CREATE REQUIRED DIRECTORIES
# ============================================================

echo "📁 Creating directories..."
mkdir -p /app/logs /app/data /app/backups /app/models /app/reports

# ============================================================
# 2. VALIDATE ENVIRONMENT VARIABLES
# ============================================================

echo "🔍 Validating environment variables..."

# Check for required variables
missing_vars=()
if [ -z "${BINANCE_API_KEY}" ]; then
    missing_vars+=("BINANCE_API_KEY")
fi
if [ -z "${BINANCE_API_SECRET}" ]; then
    missing_vars+=("BINANCE_API_SECRET")
fi

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "⚠️ Missing required environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "   - ${var}"
    done

    # In production, fail hard. In development, continue with warnings.
    if [ "${ENVIRONMENT:-development}" = "production" ]; then
        echo "❌ Production environment requires all variables. Exiting."
        exit 1
    else
        echo "⚠️ Development mode - continuing with missing variables"
    fi
else
    echo "✅ All required environment variables present"
fi

# ============================================================
# 3. CHECK PYTHON DEPENDENCIES
# ============================================================

echo "🔍 Checking Python dependencies..."
python -c "
import sys
import importlib

required_modules = ['pandas', 'numpy', 'requests', 'binance', 'firebase_admin']
missing = []
for module in required_modules:
    try:
        importlib.import_module(module)
    except ImportError:
        missing.append(module)

if missing:
    print(f'❌ Missing modules: {missing}')
    sys.exit(1)
else:
    print('✅ All required modules available')
"

# ============================================================
# 4. START THE APPLICATION
# ============================================================

echo "============================================================"
echo "🚀 Starting Trading Bot..."
echo "============================================================"

# Run the main application
exec python -u main_v34.py
