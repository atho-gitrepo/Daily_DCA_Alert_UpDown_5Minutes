"""
Utils Package - Super TDI + Super Bollinger Bands Strategy
Version: 3.4.0
"""

# Data
from utils.binance_data_client import binance_client, BinanceDataClient
from utils.mongodb_client import mongodb_client, MongoDBClient

# Indicators - Only what's needed
from utils.indicators import (
    Indicators,              # ✅ Required - TDI, BB, RSI methods
    calculate_all_indicators, # ✅ Required - main indicator calculation
    calculate_heikin_ashi,    # ✅ Required - Heikin Ashi for BB
    calculate_bollinger_bands,# ✅ Required - Super BB
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
