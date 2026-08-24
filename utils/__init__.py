"""
Utils Package - Super TDI + Super Bollinger Bands Strategy
Version: 3.4.0 - FIXED
"""

from utils.binance_data_client import binance_client
from utils.mongodb_client import mongodb_client
from utils.indicators import Indicators, calculate_heikin_ashi, calculate_all_indicators
from utils.signal_manager import signal_manager
from utils.telegram_bot import telegram_bot
from utils.logger import get_logger

# Alias Indicators class methods for convenience
calculate_bollinger_bands = Indicators.calculate_bollinger_bands
calculate_tdi = Indicators.calculate_tdi
calculate_sma = Indicators.calculate_sma
calculate_ema = Indicators.calculate_ema

__all__ = [
    'binance_client',
    'mongodb_client',
    'Indicators',
    'calculate_heikin_ashi',
    'calculate_bollinger_bands',
    'calculate_tdi',
    'calculate_sma',
    'calculate_ema',
    'calculate_all_indicators',
    'signal_manager',
    'telegram_bot',
    'get_logger',
]
