"""
Utils Package - Super TDI + Super Bollinger Bands Strategy
Version: 3.4.0 - FIXED: Import paths corrected
"""

# Data
from utils.binance_data_client import binance_client, BinanceDataClient
from utils.mongodb_client import mongodb_client, MongoDBClient

# Indicators - Import what exists
from utils.indicators import (
    Indicators,
    calculate_heikin_ashi,        # ✅ Standalone function exists
    calculate_bollinger_bands,    # ✅ Standalone function exists
    calculate_all_indicators,     # ✅ Standalone function exists
)

# Signal Manager
from utils.signal_manager import signal_manager, SignalManager, SignalData, TradeLifecycle

# Telegram
from utils.telegram_bot import telegram_bot, TelegramBot

# Logger
from utils.logger import get_logger, logger

__all__ = [
    # Data
    'binance_client',
    'BinanceDataClient',
    # MongoDB
    'mongodb_client',
    'MongoDBClient',
    # Indicators
    'Indicators',
    'calculate_heikin_ashi',
    'calculate_bollinger_bands',
    'calculate_all_indicators',
    # Signal Manager
    'signal_manager',
    'SignalManager',
    'SignalData',
    'TradeLifecycle',
    # Telegram
    'telegram_bot',
    'TelegramBot',
    # Logger
    'get_logger',
    'logger',
]
