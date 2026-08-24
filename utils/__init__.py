"""
Utils Package - Super TDI + Super Bollinger Bands Strategy
Version: 3.4.0 - FIXED: Import paths corrected
"""

# Data
from utils.binance_data_client import binance_client, BinanceDataClient
from utils.mongodb_client import mongodb_client, MongoDBClient

# Indicators - Import the class, not individual methods
from utils.indicators import Indicators

# Signal Manager
from utils.signal_manager import signal_manager, SignalManager, SignalData, TradeLifecycle

# Telegram
from utils.telegram_bot import telegram_bot, TelegramBot

# Logger
from utils.logger import get_logger, logger

# Alias for convenience (used in main.py)
calculate_all_indicators = Indicators.calculate_all_indicators
calculate_heikin_ashi = Indicators.calculate_heikin_ashi  # If this exists as standalone
calculate_bollinger_bands = Indicators.calculate_bollinger_bands

__all__ = [
    # Data
    'binance_client',
    'BinanceDataClient',
    # MongoDB
    'mongodb_client',
    'MongoDBClient',
    # Indicators
    'Indicators',
    'calculate_all_indicators',
    'calculate_heikin_ashi',
    'calculate_bollinger_bands',
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
