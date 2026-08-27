"""
Utils package - Data fetching, indicators, signal management, and bot utilities
Version: 3.4.1
"""

from utils.binance_data_client import binance_client
from utils.mongodb_client import mongodb_client
from utils.indicators import indicators, Indicators
from utils.signal_manager import signal_manager
from utils.telegram_bot import telegram_bot
from utils.logger import get_logger

# ===== INDICATOR FUNCTIONS =====
# These are wrappers that match the old API for backward compatibility

def calculate_all_indicators(df):
    """Calculate all indicators - wrapper for Indicators.calculate_all_indicators()"""
    return Indicators.calculate_all_indicators(df)

def calculate_tdi(df):
    """Calculate TDI - wrapper"""
    return Indicators.calculate_tdi(df)

def calculate_macd(df):
    """Calculate MACD - wrapper"""
    return Indicators.calculate_macd(df)

def calculate_bollinger_bands(df):
    """Calculate Bollinger Bands - wrapper"""
    return Indicators.calculate_bollinger_bands(df)

def calculate_atr(df):
    """Calculate ATR - wrapper"""
    return Indicators.calculate_atr(df)

def calculate_heikin_ashi(df):
    """Calculate Heikin Ashi - wrapper"""
    from utils.indicators import calculate_heikin_ashi as ha_func
    return ha_func(df)

__all__ = [
    'binance_client',
    'mongodb_client',
    'indicators',
    'Indicators',
    'signal_manager',
    'telegram_bot',
    'get_logger',
    'calculate_all_indicators',
    'calculate_tdi',
    'calculate_macd',
    'calculate_bollinger_bands',
    'calculate_atr',
    'calculate_heikin_ashi',
]
