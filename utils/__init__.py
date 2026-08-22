#!/usr/bin/env python3
"""
Utils package - Trading bot utilities
Version: 3.3.0 - UPDATED: Added new indicator exports
"""

import logging
from typing import Optional

__version__ = "3.3.0"

# ========== LOGGER ==========
from .logger import (
    get_logger,
    logger,
    main_logger,
    strategy_logger,
    ai_logger,
    signal_logger,
    telegram_logger,
    firebase_logger,
    indicators_logger,
    data_logger,
)

# ========== INDICATORS ==========
from .indicators import (
    indicators,
    Indicators,
    calculate_heikin_ashi,
    validate_dataframe,
    get_missing_columns,
    REQUIRED_COLUMNS,
    EPSILON,
    # NEW v3.3.0
    detect_divergence,
    detect_candle_patterns,
    calculate_support_resistance,
    detect_bb_squeeze,
    calculate_vwap,
    get_trading_session,
    get_session_multiplier,
)

# ========== FIREBASE ==========
from .firebase_client import (
    firebase_client,
    FirebaseClient,
    FirebaseValidator,
    convert_to_serializable,
)

# ========== SIGNAL MANAGER ==========
from .signal_manager import (
    signal_manager,
    SignalManager,
    SignalData,
    SignalStats,
    TradeLifecycle,
)

# ========== AI ANALYZER ==========
from .ai_analyzer import (
    ai_analyzer,
    AIAnalyzer,
    AIAnalysisResult,
    LeverageCalculator,
)

# ========== TELEGRAM BOT ==========
from .telegram_bot import (
    telegram_bot,
    send_telegram_message_sync,
)

# ========== MONGODB CLIENT ==========
from .mongodb_client import (
    mongodb_client,
    MongoDBClient,
)

# ========== DATA FETCHER (Lazy Load) ==========
_data_fetcher = None
_data_fetcher_initialized = False


def get_data_fetcher():
    """Lazy load data_fetcher to avoid circular imports."""
    global _data_fetcher, _data_fetcher_initialized

    if _data_fetcher_initialized:
        return _data_fetcher

    try:
        import sys
        import os

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        from data_fetcher import data_fetcher as df
        _data_fetcher = df
        _data_fetcher_initialized = True
        return _data_fetcher

    except ImportError as e:
        logger.debug(f"data_fetcher not available: {e}")
        _data_fetcher = None
        _data_fetcher_initialized = True
        return None
    except Exception as e:
        logger.error(f"Error loading data_fetcher: {e}")
        _data_fetcher = None
        _data_fetcher_initialized = True
        return None


class _LazyDataFetcher:
    """Proxy for lazy-loaded data_fetcher."""

    def __getattr__(self, name):
        df = get_data_fetcher()
        if df is None:
            raise AttributeError(f"data_fetcher not available: {name}")
        return getattr(df, name)

    def __call__(self, *args, **kwargs):
        df = get_data_fetcher()
        if df is None:
            raise RuntimeError("data_fetcher not available")
        return df(*args, **kwargs)

    def __bool__(self):
        return get_data_fetcher() is not None


data_fetcher = _LazyDataFetcher()

# ========== CLEANUP ==========
def cleanup():
    """Cleanup all components."""
    logger.info("Cleaning up utils...")

    try:
        if firebase_client:
            firebase_client.clear_cache()
        if signal_manager:
            signal_manager.clear_expired()
        if ai_analyzer:
            ai_analyzer.clear_cache()

        df = get_data_fetcher()
        if df and hasattr(df, 'cleanup'):
            df.cleanup()

        logger.info("Cleanup complete")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

# ========== EXPORTS ==========
__all__ = [
    # Version
    '__version__',

    # Logger
    'get_logger',
    'logger',
    'main_logger',
    'strategy_logger',
    'ai_logger',
    'signal_logger',
    'telegram_logger',
    'firebase_logger',
    'indicators_logger',
    'data_logger',

    # Indicators
    'indicators',
    'Indicators',
    'calculate_heikin_ashi',
    'validate_dataframe',
    'get_missing_columns',
    'REQUIRED_COLUMNS',
    'EPSILON',
    # NEW v3.3.0
    'detect_divergence',
    'detect_candle_patterns',
    'calculate_support_resistance',
    'detect_bb_squeeze',
    'calculate_vwap',
    'get_trading_session',
    'get_session_multiplier',

    # Firebase
    'firebase_client',
    'FirebaseClient',
    'FirebaseValidator',
    'convert_to_serializable',

    # Signal Manager
    'signal_manager',
    'SignalManager',
    'SignalData',
    'SignalStats',
    'TradeLifecycle',

    # AI Analyzer
    'ai_analyzer',
    'AIAnalyzer',
    'AIAnalysisResult',
    'LeverageCalculator',

    # Telegram
    'telegram_bot',
    'send_telegram_message_sync',

    # MongoDB
    'mongodb_client',
    'MongoDBClient',

    # Data Fetcher
    'data_fetcher',
    'get_data_fetcher',

    # Utils
    'cleanup',
]

logger.info(f"✅ Utils package v{__version__} initialized (v3.3.0 - Divergence, Patterns, S/R, Session)")
