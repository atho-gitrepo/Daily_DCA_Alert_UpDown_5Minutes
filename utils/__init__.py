#!/usr/bin/env python3
"""
Utils package - Trading bot utilities
Version: 3.4.0 - UPDATED: v3.4.0 signal engine exports
"""

import logging
from typing import Optional

__version__ = "3.4.0"

# ========== LOGGER ==========
from .logger import get_logger, logger

# ========== INDICATORS ==========
from .indicators import (
    indicators,
    Indicators,
    calculate_heikin_ashi,
    validate_dataframe,
    get_missing_columns,
    REQUIRED_COLUMNS,
    EPSILON,
    detect_divergence,
    detect_candle_patterns,
    calculate_support_resistance,
    detect_bb_squeeze,
    calculate_vwap,
    get_trading_session,
    get_session_multiplier,
)

# ========== SIGNAL MANAGER ==========
from .signal_manager import (
    signal_manager,
    SignalManager,
    SignalData,
    TradeLifecycle,
)

# ========== v3.4.0 SIGNAL ENGINE ==========
try:
    from strategy.signal_engine_v34 import signal_engine, SignalEngineV34
    from strategy.signal_state import SignalStateMachine, SignalState, SetupData, TriggerData
    from strategy.htf_regime import HTFRegimeAnalyzer, Regime, RegimeData
    from strategy.structure import MarketStructureAnalyzer, StructureData
    V34_AVAILABLE = True
except ImportError:
    V34_AVAILABLE = False
    signal_engine = None
    SignalEngineV34 = None
    SignalStateMachine = None
    SignalState = None
    SetupData = None
    TriggerData = None
    HTFRegimeAnalyzer = None
    Regime = None
    RegimeData = None
    MarketStructureAnalyzer = None
    StructureData = None
    logging.warning("v3.4.0 signal engine not available")

# ========== AI ANALYZER ==========
from .ai_analyzer import ai_analyzer, AIAnalyzer, AIAnalysisResult

# ========== TELEGRAM BOT ==========
from .telegram_bot import telegram_bot, send_telegram_message_sync

# ========== MONGODB CLIENT ==========
from .mongodb_client import mongodb_client, MongoDBClient

# ========== DATA FETCHER ==========
from .data_fetcher import data_fetcher

# ========== EXPORTS ==========
__all__ = [
    # Version
    '__version__',

    # Logger
    'get_logger', 'logger',

    # Indicators
    'indicators', 'Indicators',
    'calculate_heikin_ashi',
    'validate_dataframe', 'get_missing_columns',
    'REQUIRED_COLUMNS', 'EPSILON',
    'detect_divergence', 'detect_candle_patterns',
    'calculate_support_resistance', 'detect_bb_squeeze',
    'calculate_vwap', 'get_trading_session', 'get_session_multiplier',

    # Signal Manager
    'signal_manager', 'SignalManager', 'SignalData', 'TradeLifecycle',

    # v3.4.0 Signal Engine
    'V34_AVAILABLE',
    'signal_engine', 'SignalEngineV34',
    'SignalStateMachine', 'SignalState', 'SetupData', 'TriggerData',
    'HTFRegimeAnalyzer', 'Regime', 'RegimeData',
    'MarketStructureAnalyzer', 'StructureData',

    # AI
    'ai_analyzer', 'AIAnalyzer', 'AIAnalysisResult',

    # Telegram
    'telegram_bot', 'send_telegram_message_sync',

    # MongoDB
    'mongodb_client', 'MongoDBClient',

    # Data
    'data_fetcher',
]

logger.info(f"✅ Utils package v{__version__} initialized")
if V34_AVAILABLE:
    logger.info("  ✅ v3.4.0 Signal Engine available")
