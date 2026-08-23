#!/usr/bin/env python3
"""
Strategy package - Trading strategies
Version: 3.4.0 - UPDATED: v3.4.0 signal engine
"""

import logging

__version__ = "3.4.0"

# ========== v3.4.0 Signal Engine ==========
from strategy.signal_engine_v34 import signal_engine, SignalEngineV34
from strategy.signal_state import SignalStateMachine, SignalState, SetupData, TriggerData
from strategy.htf_regime import HTFRegimeAnalyzer, Regime, RegimeData
from strategy.structure import MarketStructureAnalyzer, StructureData

# ========== Legacy Strategies (Keep for compatibility) ==========
try:
    from strategy.consolidated_trend import strategy, ConsolidatedTrendStrategy
    LEGACY_AVAILABLE = True
except ImportError:
    LEGACY_AVAILABLE = False
    strategy = None
    ConsolidatedTrendStrategy = None

try:
    from strategy.day_trading_strategy import DayTradingStrategy, TimeframeData
    DAY_TRADING_AVAILABLE = True
except ImportError:
    DAY_TRADING_AVAILABLE = False
    DayTradingStrategy = None
    TimeframeData = None

logger = logging.getLogger(__name__)

__all__ = [
    '__version__',
    # v3.4.0
    'signal_engine', 'SignalEngineV34',
    'SignalStateMachine', 'SignalState', 'SetupData', 'TriggerData',
    'HTFRegimeAnalyzer', 'Regime', 'RegimeData',
    'MarketStructureAnalyzer', 'StructureData',
    # Legacy
    'LEGACY_AVAILABLE', 'strategy', 'ConsolidatedTrendStrategy',
    'DAY_TRADING_AVAILABLE', 'DayTradingStrategy', 'TimeframeData',
]

logger.info(f"✅ Strategy package v{__version__} initialized")
