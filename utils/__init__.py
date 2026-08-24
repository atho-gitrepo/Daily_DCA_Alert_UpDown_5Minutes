"""
Utils Package - Super TDI + Super Bollinger Bands Strategy
Version: 3.4.0
"""

# Data
from utils.binance_data_client import binance_client
from utils.mongodb_client import mongodb_client

# Indicators - Only import what exists as standalone functions
from utils.indicators import (
    Indicators,              # ✅ Class exists
    calculate_heikin_ashi,   # ✅ Standalone exists
)

# Create aliases from the Indicators class for main.py compatibility
calculate_all_indicators = Indicators.calculate_all_indicators
calculate_bollinger_bands = Indicators.calculate_bollinger_bands

# Signal Manager
from utils.signal_manager import signal_manager

# Telegram
from utils.telegram_bot import telegram_bot

# Logger
from utils.logger import get_logger

__all__ = [
    'binance_client',
    'mongodb_client',
    'Indicators',
    'calculate_heikin_ashi',
    'calculate_bollinger_bands',
    'calculate_all_indicators',
    'signal_manager',
    'telegram_bot',
    'get_logger',
]
