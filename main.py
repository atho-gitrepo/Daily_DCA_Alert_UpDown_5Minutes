#!/usr/bin/env python3
"""
AI-Powered Trading Bot - Main Entry Point
HYBRID STRATEGY: Super TDI + Super Bollinger Bands + Multi-Timeframe
Version: 3.3.0 - UPDATED: Divergence, Candle Patterns, S/R, Session Filtering
"""

import os
import sys
import time
import logging
import signal
import asyncio
import threading
from typing import Dict, Optional, Tuple, Any, List
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import traceback

import pandas as pd
import numpy as np

# Local imports
from settings import config, Config
from data_fetcher import data_fetcher
from strategy.consolidated_trend import strategy
from utils.signal_manager import signal_manager, TradeLifecycle
from utils.telegram_bot import telegram_bot, send_telegram_message_sync
from utils.ai_analyzer import ai_analyzer
from utils.mongodb_client import mongodb_client as db_client
from utils.indicators import (
    Indicators,
    calculate_heikin_ashi,
    get_trading_session,
    get_session_multiplier,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.logging.level),
    format=config.logging.format,
    handlers=[
        logging.FileHandler(config.logging.file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
main_logger = logging.getLogger("main")

# Emoji indicators
EMOJI = {
    "START": "🚀", "STOP": "🛑", "SUCCESS": "✅", "ERROR": "❌",
    "WARNING": "⚠️", "INFO": "ℹ️", "SIGNAL": "📡", "HEALTH": "💚",
    "AI": "🤖", "DB": "💾", "TELEGRAM": "📨", "SYNC": "🔄",
    "RETRY": "↩️", "SNIPER": "🎯", "PROFIT": "💰", "LOSS": "💸",
    "REJECT": "🚫", "WAIT": "⏳", "CACHE": "💾", "RATE": "🚀",
    "LOCK": "🔒", "UNLOCK": "🔓", "MONITOR": "📊", "RESULT": "📈",
    "DELETE": "🗑️", "LTF": "⏱️", "CONFLICT": "⚠️", "RRR": "📈",
    "HTF": "📊", "HARD": "🔴", "SOFT": "🟡", "TDI": "📈",
    "BB": "📊", "ZONE": "🎯", "DEBUG": "🔍", "CANDLE": "🕯️",
    "CROSSOVER": "🔀", "REVERSAL": "↩️", "FEES": "💰",
    "SCORE": "🎯", "DECAY": "⏳", "LEVERAGE": "⚡", "LIMIT": "🚫",
    "APPROVED": "✅", "GRADE_A": "🏆", "GRADE_B": "🥈", "GRADE_C": "🥉",
    "MONGODB": "🍃", "PENDING": "⏳", "EXECUTED": "✅", "EXPIRED": "⏰",
    "CANCELLED": "❌", "ACTIVE": "🔥", "REJECTED": "🚫",
    "DIVERGENCE": "↩️", "PATTERN": "🕯️", "S_R": "📊", "SESSION": "🌍",
}


# Global state
running = True
bot_stats: Dict[str, Any] = {
    "status": "initializing",
    "start_time": datetime.now().isoformat(),
    "signals_generated": 0,
    "signals_processed": 0,
    "errors": 0,
    "last_signal": None,
    "symbols_processed": 0,
    "cycles_completed": 0,
    "sniper_signals": 0,
    "ai_tokens_used": 0,
    "ai_calls_skipped": 0,
    "duplicate_signals_prevented": 0,
    "signals_unlocked": 0,
    "active_deletions": 0,
    "ltf_confirmed": 0,
    "ltf_rejected": 0,
    "ai_conflicts": 0,
    "score_approved": 0,
    "score_rejected": 0,
    "data_stale_events": 0,
    "grade_a_signals": 0,
    "grade_b_signals": 0,
    "grade_c_rejected": 0,
    # NEW v3.3.0 stats
    "divergence_signals": 0,
    "pattern_signals": 0,
    "sr_signals": 0,
    "squeeze_signals": 0,
    "session_adjusted": 0,
    "signal_outcomes": {
        "profitable": 0, "losing": 0, "break_even": 0,
        "active": 0, "total_pnl": 0.0,
    },
    "rrr_stats": {"min": 0, "max": 0, "avg": 0, "values": []},
    "ai_decisions": {"approve": 0, "reject": 0, "wait": 0, "conflict": 0},
    "signal_strength": {"hard": 0, "soft": 0},
    "tdi_zones": {
        "oversold": 0, "soft_buy": 0, "buy_zone": 0,
        "no_trade": 0, "soft_sell": 0, "overbought": 0,
    },
    "rejection_reasons": {
        "ltf_not_confirmed": 0, "tdi_no_trade_zone": 0,
        "tdi_conditions_failed": 0, "volume_too_low": 0,
        "bb_position_bad": 0, "htf_conflict": 0,
        "score_too_low": 0, "data_stale": 0,
        "grade_c_rejected": 0, "insufficient_data": 0,
        "binance_connection_error": 0,
        "signal_manager_rejected": 0,
        "duplicate_signal": 0,
        # NEW v3.3.0
        "session_rejected": 0,
        "divergence_missing": 0,
        "pattern_missing": 0,
        "sr_missing": 0,
    },
}

# ========== MINIMUM DATA REQUIREMENTS ==========
MIN_DATA_BARS = 60
MIN_HTF_BARS = 30
MIN_LTF_BARS = 20

# ========== GRADE CONFIGURATION ==========
GRADE_A_THRESHOLD = 80
GRADE_B_THRESHOLD = 70
GRADE_C_THRESHOLD = 60
GRADE_D_THRESHOLD = 50

# ========== RRR CONFIGURATION ==========
DEFAULT_RRR = 2.0
MIN_RRR = 1.5
MAX_RRR = 4.0
RRR_TARGET = 2.5

# ========== TDI LEVELS (STANDARDIZED) ==========
HARD_BUY = 25.0
SOFT_BUY = 35.0
CENTER_LINE = 50.0
NO_TRADE_START = 50.0
NO_TRADE_END = 65.0
SOFT_SELL = 65.0
HARD_SELL = 75.0

# ========== AI RATE LIMIT CACHE ==========
ai_cache: Dict[str, Dict[str, Any]] = {}
ai_cache_timestamp: Dict[str, datetime] = {}
AI_CACHE_TTL = 600

# ========== SYMBOL COOLDOWN ==========
symbol_last_signal_time: Dict[str, datetime] = {}
SYMBOL_COOLDOWN_MINUTES = 30

# ========== AI TOKEN TRACKING ==========
ai_tokens_remaining = 100000
ai_token_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# ========== AI USAGE TRACKING ==========
ai_last_request_time: Dict[str, datetime] = {}
AI_MIN_INTERVAL_SECONDS = 120

# ========== GLOBAL SIGNAL DEDUPLICATION ==========
_processed_signals_this_cycle: Dict[str, Dict] = {}
_cycle_start_time: Optional[datetime] = None

# ========== TRADING FEES ==========
TRADING_FEE = 0.0011

# ========== TIMEFRAME CONFIGURATION ==========
LTF_TIMEFRAME = "5m"
HTF_TIMEFRAME = "1h"
LTF_MIN_CONFIRMATION = 0.50
HTF_ALIGNMENT_THRESHOLD = 0.70

# ========== SIGNAL FILTERING ==========
MIN_CONFIDENCE = 0.50
MIN_QUALITY_SCORE = 50
MAX_SIGNALS_PER_CYCLE = 3
MIN_SIGNAL_SCORE = 65

# ========== RETRY CONFIGURATION ==========
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


# ========== GRADE HELPER FUNCTIONS ==========
def get_grade(score: int) -> str:
    """Get grade based on score."""
    if score >= GRADE_A_THRESHOLD:
        return "A"
    elif score >= GRADE_B_THRESHOLD:
        return "B"
    elif score >= GRADE_C_THRESHOLD:
        return "C"
    elif score >= GRADE_D_THRESHOLD:
        return "D"
    else:
        return "F"


def is_grade_eligible_for_ai(score: int) -> Tuple[bool, str]:
    """
    Check if grade is eligible for AI analysis.
    Only Grade A and B get AI analysis to save tokens.
    """
    grade = get_grade(score)

    if grade == "A":
        return True, f"Grade A ({score}/100) - Eligible for AI analysis"
    elif grade == "B":
        return True, f"Grade B ({score}/100) - Eligible for AI analysis (conditional)"
    elif grade == "C":
        return False, f"Grade C ({score}/100) - REJECTED before AI (tokens saved!)"
    elif grade == "D":
        return False, f"Grade D ({score}/100) - REJECTED before AI (tokens saved!)"
    else:
        return False, f"Grade F ({score}/100) - REJECTED before AI (tokens saved!)"


def is_grade_approved_for_telegram(score: int, signal_data: Dict) -> Tuple[bool, str]:
    """
    Check if signal grade is approved for Telegram.
    Only Grade A and B with proper conditions.
    """
    grade = get_grade(score)

    if grade == "A":
        return True, f"Grade A ({score}/100) - Approved for Telegram"

    if grade == "B":
        ltf_confirmed = signal_data.get('ltf_confirmed', False)
        htf_aligned = signal_data.get('htf_aligned', False)
        ai_decision = signal_data.get('ai_decision', '')

        if not ltf_confirmed:
            return False, f"Grade B ({score}/100) - LTF not confirmed"
        if not htf_aligned:
            return False, f"Grade B ({score}/100) - HTF not aligned"
        if ai_decision != 'APPROVE':
            return False, f"Grade B ({score}/100) - AI not approved"

        return True, f"Grade B ({score}/100) - Approved for Telegram (LTF+HTF+AI)"

    return False, f"Grade {grade} ({score}/100) - Not approved for Telegram"


# ========== HELPER: TRACK REJECTION ==========
def track_rejection(reason: str):
    """Track rejection reasons for performance tuning."""
    reason_lower = reason.lower()
    if 'ltf' in reason_lower and ('rejected' in reason_lower or 'not confirmed' in reason_lower):
        bot_stats['rejection_reasons']['ltf_not_confirmed'] += 1
    elif 'no trade zone' in reason_lower:
        bot_stats['rejection_reasons']['tdi_no_trade_zone'] += 1
    elif 'conditions not met' in reason_lower:
        bot_stats['rejection_reasons']['tdi_conditions_failed'] += 1
    elif 'volume' in reason_lower:
        bot_stats['rejection_reasons']['volume_too_low'] += 1
    elif 'bb' in reason_lower:
        bot_stats['rejection_reasons']['bb_position_bad'] += 1
    elif 'htf' in reason_lower and 'conflict' in reason_lower:
        bot_stats['rejection_reasons']['htf_conflict'] += 1
    elif 'score' in reason_lower:
        bot_stats['rejection_reasons']['score_too_low'] += 1
    elif 'stale' in reason_lower or 'expired' in reason_lower:
        bot_stats['rejection_reasons']['data_stale'] += 1
    elif 'grade' in reason_lower and 'c' in reason_lower:
        bot_stats['rejection_reasons']['grade_c_rejected'] += 1
    elif 'insufficient' in reason_lower:
        bot_stats['rejection_reasons']['insufficient_data'] += 1
    elif 'signal_manager' in reason_lower or 'rejected' in reason_lower:
        bot_stats['rejection_reasons']['signal_manager_rejected'] += 1
    elif 'duplicate' in reason_lower:
        bot_stats['rejection_reasons']['duplicate_signal'] += 1
    # NEW v3.3.0
    elif 'session' in reason_lower:
        bot_stats['rejection_reasons']['session_rejected'] += 1
    elif 'divergence' in reason_lower:
        bot_stats['rejection_reasons']['divergence_missing'] += 1
    elif 'pattern' in reason_lower:
        bot_stats['rejection_reasons']['pattern_missing'] += 1
    elif 'sr' in reason_lower or 'support' in reason_lower or 'resistance' in reason_lower:
        bot_stats['rejection_reasons']['sr_missing'] += 1


# ========== DYNAMIC RRR CALCULATION ==========
def calculate_dynamic_rrr(signal_data: Dict[str, Any]) -> float:
    """Calculate dynamic RRR based on signal quality and market conditions."""
    try:
        base_rrr = signal_data.get('rrr', DEFAULT_RRR)
        confidence = signal_data.get('confidence', 0.5)
        tdi_level = signal_data.get('tdi_level', 50)
        htf_trend = signal_data.get('htf_trend', 'NEUTRAL')
        quality_score = signal_data.get('quality_score', 50)
        signal_strength = signal_data.get('signal_strength', 'SOFT')
        total_score = signal_data.get('total_score', 0)
        rrr = base_rrr
        if confidence > 0.8: rrr += 0.5
        elif confidence > 0.7: rrr += 0.3
        elif confidence < 0.5: rrr -= 0.3
        if tdi_level <= HARD_BUY or tdi_level >= HARD_SELL: rrr += 0.5
        elif tdi_level <= SOFT_BUY or tdi_level >= SOFT_SELL: rrr += 0.3
        if htf_trend in ['BULLISH', 'BEARISH']: rrr += 0.3
        if signal_strength == "HARD": rrr += 0.5
        if total_score >= 80: rrr += 0.5
        elif total_score >= 70: rrr += 0.3
        elif quality_score >= 80: rrr += 0.5
        elif quality_score >= 70: rrr += 0.3
        rrr = max(MIN_RRR, min(MAX_RRR, rrr))
        return round(rrr * 2) / 2
    except Exception as e:
        return DEFAULT_RRR


# ========== RRR SUGGESTION ==========
def get_rrr_suggestion(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate RRR suggestions for AI analysis."""
    try:
        current_rrr = signal_data.get('rrr', DEFAULT_RRR)
        suggested_rrr = calculate_dynamic_rrr(signal_data)
        quality_score = signal_data.get('quality_score', 50)
        total_score = signal_data.get('total_score', 0)
        confidence = signal_data.get('confidence', 0.5)
        rrr_options = {
            'conservative': max(MIN_RRR, suggested_rrr - 0.5),
            'moderate': suggested_rrr,
            'aggressive': min(MAX_RRR, suggested_rrr + 0.5)
        }
        for key in rrr_options: rrr_options[key] = round(rrr_options[key], 2)
        return {
            'current_rrr': current_rrr, 'suggested_rrr': suggested_rrr,
            'quality_score': quality_score, 'total_score': total_score,
            'rrr_options': rrr_options,
            'adjustment_reason': f"Confidence: {confidence:.2%}, Quality: {quality_score}/100, Score: {total_score}/100",
            'min_rrr': MIN_RRR, 'max_rrr': MAX_RRR, 'target_rrr': RRR_TARGET,
        }
    except Exception as e:
        return {'current_rrr': DEFAULT_RRR, 'suggested_rrr': DEFAULT_RRR, 'quality_score': 50,
                'total_score': 0, 'rrr_options': {'conservative': 1.5, 'moderate': 2.0, 'aggressive': 2.5},
                'adjustment_reason': 'Error', 'min_rrr': MIN_RRR, 'max_rrr': MAX_RRR, 'target_rrr': RRR_TARGET}


# ========== LTF (5min) CONFIRMATION ==========
def check_ltf_confirmation(symbol: str, direction: Optional[str], client) -> Tuple[bool, float, str, str, float]:
    """Check lower timeframe (5min) for entry confirmation."""
    main_logger.debug(f"{EMOJI['LTF']} Starting LTF check for {symbol}, direction={direction}")
    try:
        ltf_df = client.get_historical_klines(symbol, interval=LTF_TIMEFRAME, limit=100)
        if ltf_df.empty or len(ltf_df) < MIN_LTF_BARS:
            main_logger.debug(f"{EMOJI['WARNING']} Insufficient LTF data for {symbol}: {len(ltf_df)} bars")
            return False, 0, "Insufficient LTF data", "", 50

        ltf_df = Indicators.calculate_tdi(ltf_df)
        ltf_df = calculate_heikin_ashi(ltf_df)
        ltf_df = Indicators.calculate_bollinger_bands(ltf_df, period=34, dev=1.750)

        if 'tdi_slow_ma' not in ltf_df.columns or ltf_df['tdi_slow_ma'].isna().all():
            main_logger.warning(f"{EMOJI['WARNING']} TDI calculation failed for LTF {symbol}")
            return False, 0, "LTF TDI calculation failed", "", 50

        last = ltf_df.iloc[-1]
        prev = ltf_df.iloc[-2] if len(ltf_df) > 1 else last
        tdi_slow = last.get('tdi_slow_ma', 50)
        tdi_fast = last.get('tdi_fast_ma', 50)

        def get_tdi_zone(value: float) -> str:
            if value <= HARD_BUY: return "OVERSOLD"
            elif value <= SOFT_BUY: return "SOFT_BUY"
            elif value < CENTER_LINE: return "BUY_ZONE"
            elif value < SOFT_SELL: return "NO_TRADE"
            elif value < HARD_SELL: return "SOFT_SELL"
            else: return "OVERBOUGHT"

        tdi_zone = get_tdi_zone(tdi_slow)
        bb_lower = last.get('bb_lower', 0); bb_upper = last.get('bb_upper', 0)
        ha_color = last.get('ha_color', 0); ha_low = last.get('ha_low', last.get('low', 0))
        ha_high = last.get('ha_high', last.get('high', 0)); volume_ratio = last.get('volume_ratio', 1)

        if direction is None:
            detected_direction = ""
            if tdi_slow < CENTER_LINE:
                confidence = 0.5
                if tdi_slow <= HARD_BUY: confidence += 0.30
                elif tdi_slow <= SOFT_BUY: confidence += 0.20
                else: confidence += 0.10
                if tdi_fast > tdi_slow: confidence += 0.15
                if ha_color == 1: confidence += 0.10
                if ha_low <= bb_lower and bb_lower > 0: confidence += 0.10
                confidence = min(0.95, confidence)
                if confidence >= 0.50:
                    return True, confidence, f"LTF BUY zone (TDI: {tdi_slow:.1f})", "BUY", tdi_slow
            if tdi_slow > CENTER_LINE:
                confidence = 0.5
                if tdi_slow >= HARD_SELL: confidence += 0.30
                elif tdi_slow >= SOFT_SELL: confidence += 0.20
                else: confidence += 0.10
                if tdi_fast < tdi_slow: confidence += 0.15
                if ha_color == -1: confidence += 0.10
                if ha_high >= bb_upper and bb_upper > 0: confidence += 0.10
                confidence = min(0.95, confidence)
                if confidence >= 0.50:
                    return True, confidence, f"LTF SELL zone (TDI: {tdi_slow:.1f})", "SELL", tdi_slow
            return False, 0.3, f"LTF neutral (TDI: {tdi_slow:.1f})", "", tdi_slow

        confidence = 0.5; reasons = []
        if direction == "BUY":
            if tdi_slow <= HARD_BUY: confidence += 0.30; reasons.append("Hard Buy Zone")
            elif tdi_slow <= SOFT_BUY: confidence += 0.20; reasons.append("Soft Buy Zone")
            elif tdi_slow < 55: confidence += 0.15; reasons.append("Buy Zone")
            if tdi_fast > tdi_slow: confidence += 0.15; reasons.append("Bullish Crossover")
            if ha_low <= bb_lower and bb_lower > 0: confidence += 0.15; reasons.append("BB Lower Touch")
            if ha_color == 1: confidence += 0.10; reasons.append("HA Bullish")
            if volume_ratio > 1.5: confidence += 0.05; reasons.append("Volume Surge")
        else:
            if tdi_slow >= HARD_SELL: confidence += 0.30; reasons.append("Hard Sell Zone")
            elif tdi_slow >= SOFT_SELL: confidence += 0.20; reasons.append("Soft Sell Zone")
            elif tdi_slow > 45: confidence += 0.15; reasons.append("Sell Zone")
            if tdi_fast < tdi_slow: confidence += 0.15; reasons.append("Bearish Crossover")
            if ha_high >= bb_upper and bb_upper > 0: confidence += 0.15; reasons.append("BB Upper Touch")
            if ha_color == -1: confidence += 0.10; reasons.append("HA Bearish")
            if volume_ratio > 1.5: confidence += 0.05; reasons.append("Volume Surge")
        confidence = min(0.95, confidence)
        reason = ", ".join(reasons) if reasons else "No strong LTF signals"
        confirmed = confidence >= 0.50
        return confirmed, confidence, reason, direction, tdi_slow
    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} LTF check failed for {symbol}: {e}")
        return False, 0, f"Error: {str(e)}", "", 50


# ========== HTF TREND VALIDATION ==========
def validate_htf_trend(symbol: str, signal_type: str, htf_trend: str, client) -> Tuple[bool, float, str]:
    """Validate HTF trend alignment with signal direction."""
    try:
        htf_df = client.get_historical_klines(symbol, interval=HTF_TIMEFRAME, limit=50)
        if htf_df.empty or len(htf_df) < MIN_HTF_BARS:
            return True, 0.5, "Insufficient HTF data"
        htf_df = Indicators.calculate_all_indicators(htf_df)
        last = htf_df.iloc[-1]; bb_middle = last.get('bb_middle', 0)
        ha_close = last.get('ha_close', last.get('close', 0))
        if ha_close > bb_middle * 1.01 and bb_middle > 0: detected_trend, score, reason = "BULLISH", 0.8, "HTF BULLISH"
        elif ha_close < bb_middle * 0.99 and bb_middle > 0: detected_trend, score, reason = "BEARISH", 0.8, "HTF BEARISH"
        else: detected_trend, score, reason = "NEUTRAL", 0.5, "HTF NEUTRAL"
        if signal_type == "BUY" and detected_trend == "BULLISH": return True, 0.9, "HTF BULLISH aligns with BUY"
        elif signal_type == "SELL" and detected_trend == "BEARISH": return True, 0.9, "HTF BEARISH aligns with SELL"
        elif detected_trend == "NEUTRAL": return True, 0.6, "HTF NEUTRAL"
        else: return False, 0.3, f"HTF {detected_trend} conflicts with {signal_type}"
    except Exception as e: return True, 0.5, f"Error: {str(e)}"


# ------------------- Health Check Handler -------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health': self._handle_health()
        elif self.path == '/metrics': self._handle_metrics()
        elif self.path == '/signals': self._handle_signals()
        elif self.path == '/': self._handle_root()
        else: self.send_response(404); self.end_headers()

    def _handle_root(self):
        self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
        self.wfile.write(b"""
        <html>
        <body>
            <h1>🤖 AI Trading Bot v3.3.0</h1>
            <h2>✨ New Features: Divergence, Candle Patterns, S/R, Session Filtering</h2>
            <ul>
                <li><a href='/health'>Health Status</a></li>
                <li><a href='/metrics'>Metrics</a></li>
                <li><a href='/signals'>Signal Status</a></li>
            </ul>
        </body>
        </html>
        """)

    def _handle_health(self):
        status = get_bot_status(); is_healthy = status['status'] == 'healthy'
        self.send_response(200 if is_healthy else 503); self.send_header('Content-Type', 'application/json'); self.end_headers()
        self.wfile.write(json.dumps(status, indent=2).encode())

    def _handle_metrics(self):
        metrics = get_bot_metrics(); self.send_response(200); self.send_header('Content-Type', 'text/plain'); self.end_headers()
        self.wfile.write(metrics.encode())

    def _handle_signals(self):
        """Handle signal status endpoint."""
        try:
            active_signals = signal_manager.get_all_active_signals()

            status = {
                "timestamp": datetime.now().isoformat(),
                "version": "3.3.0",
                "active_count": len(active_signals),
                "active_signals": [
                    {
                        'symbol': s.get('symbol'),
                        'type': s.get('signal_type'),
                        'status': s.get('status'),
                        'entry_price': s.get('entry_price'),
                        'entry_time': s.get('entry_time'),
                        'direction': s.get('direction'),
                        'grade': s.get('grade'),
                        'total_score': s.get('total_score'),
                        'doc_id': s.get('doc_id'),
                        'age_minutes': s.get('age_minutes', 0),
                        'current_price': s.get('current_price'),
                        'pnl': s.get('pnl'),
                        'pnl_percent': s.get('pnl_percent'),
                        'rrr': s.get('rrr'),
                        'signal_strength': s.get('signal_strength'),
                        # NEW v3.3.0
                        'divergence_detected': s.get('divergence_detected', False),
                        'candle_pattern': s.get('candle_pattern', 'NONE'),
                        'sr_confirmed': s.get('sr_confirmed', False),
                        'bb_squeeze': s.get('bb_squeeze', False),
                        'session': s.get('session', 'UNKNOWN'),
                    }
                    for s in list(active_signals.values())[:20]
                ],
                "new_features": {
                    "divergence": "Bullish/Bearish divergence detection",
                    "candle_patterns": "Doji, Engulfing, Hammer, Star patterns",
                    "support_resistance": "Dynamic S/R levels",
                    "bb_squeeze": "Bollinger Band squeeze detection",
                    "session_filtering": "Asian/London/NY session awareness",
                }
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args): pass


def get_bot_status() -> Dict[str, Any]:
    ai_stats = ai_analyzer.get_stats() if ai_analyzer else {}
    active_count = len(signal_manager.active_signals) if signal_manager else 0
    return {
        "status": "healthy" if running else "stopped",
        "timestamp": datetime.now().isoformat(),
        "version": "3.3.0",
        "stats": bot_stats,
        "active_signals": active_count,
        "components": {
            "strategy": strategy is not None,
            "signal_manager": signal_manager is not None,
            "telegram_bot": telegram_bot.enabled if telegram_bot else False,
            "ai_analyzer": ai_analyzer.enabled if ai_analyzer else False,
            "mongodb": db_client.is_available() if db_client else False,
        },
        "score_approved": bot_stats.get('score_approved', 0),
        "score_rejected": bot_stats.get('score_rejected', 0),
        "grade_stats": {
            "grade_a": bot_stats.get('grade_a_signals', 0),
            "grade_b": bot_stats.get('grade_b_signals', 0),
            "grade_c_rejected": bot_stats.get('grade_c_rejected', 0),
        },
        # NEW v3.3.0
        "new_feature_stats": {
            "divergence_signals": bot_stats.get('divergence_signals', 0),
            "pattern_signals": bot_stats.get('pattern_signals', 0),
            "sr_signals": bot_stats.get('sr_signals', 0),
            "squeeze_signals": bot_stats.get('squeeze_signals', 0),
            "session_adjusted": bot_stats.get('session_adjusted', 0),
        },
        "rejection_report": _get_rejection_report(),
    }


def _get_rejection_report() -> Dict[str, Any]:
    rejection_reasons = bot_stats.get('rejection_reasons', {})
    total_rejections = sum(rejection_reasons.values())
    total_signals = bot_stats.get('signals_generated', 0)
    total_attempts = total_rejections + total_signals
    sorted_reasons = sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True)
    return {
        'total_attempts': total_attempts, 'total_signals': total_signals,
        'total_rejections': total_rejections,
        'acceptance_rate': round(total_signals / total_attempts * 100, 1) if total_attempts > 0 else 0,
        'rejection_breakdown': rejection_reasons,
        'top_reasons': [{'reason': reason, 'count': count} for reason, count in sorted_reasons[:5] if count > 0],
    }


def get_bot_metrics() -> str:
    active_count = len(signal_manager.active_signals) if signal_manager else 0
    metrics = [
        f"bot_status {1 if running else 0}",
        f"bot_signals_generated {bot_stats.get('signals_generated', 0)}",
        f"bot_active_signals {active_count}",
        f"bot_errors_total {bot_stats.get('errors', 0)}",
        f"bot_grade_a {bot_stats.get('grade_a_signals', 0)}",
        f"bot_grade_b {bot_stats.get('grade_b_signals', 0)}",
        f"bot_grade_c_rejected {bot_stats.get('grade_c_rejected', 0)}",
        # NEW v3.3.0
        f"bot_divergence_signals {bot_stats.get('divergence_signals', 0)}",
        f"bot_pattern_signals {bot_stats.get('pattern_signals', 0)}",
        f"bot_sr_signals {bot_stats.get('sr_signals', 0)}",
        f"bot_squeeze_signals {bot_stats.get('squeeze_signals', 0)}",
    ]
    return "\n".join(metrics)


# ==================== DUPLICATE DETECTION ====================
def check_duplicate_in_cycle(symbol: str, signal_type: str, entry_price: float) -> Tuple[bool, str]:
    global _processed_signals_this_cycle, _cycle_start_time
    if _cycle_start_time and (datetime.now() - _cycle_start_time).total_seconds() > 300:
        _processed_signals_this_cycle.clear(); _cycle_start_time = datetime.now()
    if not _cycle_start_time: _cycle_start_time = datetime.now()
    signal_key = f"{symbol}_{signal_type}_{round(entry_price, 6)}"
    if signal_key in _processed_signals_this_cycle:
        bot_stats['duplicate_signals_prevented'] += 1
        return True, "Duplicate in cycle"
    _processed_signals_this_cycle[signal_key] = {"time": datetime.now()}
    return False, "OK"


# ==================== LOAD ACTIVE SIGNALS ====================
def load_active_signals():
    """Load active signals from MongoDB with cleanup."""
    if not db_client.is_available():
        main_logger.warning(f"{EMOJI['WARNING']} MongoDB not available, skipping active signals load")
        return

    try:
        # ✅ NEW: Clean up orphaned active signals first
        if hasattr(db_client, 'cleanup_orphaned_active_signals'):
            cleaned = db_client.cleanup_orphaned_active_signals()
            if cleaned > 0:
                main_logger.info(f"{EMOJI['DELETE']} Cleaned up {cleaned} orphaned active signals")

        active_signals = db_client.get_active_signals()
        if not active_signals:
            main_logger.info(f"{EMOJI['INFO']} No active signals found in MongoDB")
            return

        loaded_count = 0
        for doc_id, signal_data in active_signals.items():
            if len(signal_manager.active_signals) >= 8:
                break

            symbol = signal_data.get('symbol')
            if not symbol or symbol in signal_manager.active_signals:
                continue

            signal_type = signal_data.get('signal_type')
            entry_price = signal_data.get('entry_price', 0)
            entry_time = signal_data.get('entry_time', datetime.now().isoformat())
            raw_data = {**signal_data, 'doc_id': doc_id, 'db_doc_id': doc_id}

            if signal_manager.restore_symbol(symbol, signal_type, entry_price, entry_time, raw_data):
                loaded_count += 1

        main_logger.info(f"{EMOJI['SUCCESS']} Loaded {loaded_count} active signals from MongoDB")

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} Load active signals error: {e}")


# ------------------- BinanceDataClient -------------------
class BinanceDataClient:
    """Client for fetching data from Binance with retry logic."""

    def __init__(self):
        self.api_key = config.binance.api_key
        self.api_secret = config.binance.api_secret
        self.is_testnet = config.binance.testnet
        base_url = "https://testnet.binancefuture.com" if self.is_testnet else "https://fapi.binance.com"
        self.futures_client = None
        self.spot_client = None
        self.client_type = "None"
        self._connected = False

        self._init_clients(base_url)
        self._test_connection()

        self.price_precisions: Dict[str, int] = {}
        for symbol in config.market.symbols:
            self.price_precisions[symbol] = 2

    def _init_clients(self, base_url: str):
        """Initialize Binance clients."""
        try:
            from binance.um_futures import UMFutures
            if self.api_key and self.api_secret:
                self.futures_client = UMFutures(key=self.api_key, secret=self.api_secret, base_url=base_url)
            else:
                self.futures_client = UMFutures(base_url=base_url)
            self.client_type = "Futures"
            main_logger.info(f"{EMOJI['SUCCESS']} Binance Futures client initialized (Testnet: {self.is_testnet})")
            return
        except ImportError:
            main_logger.warning(f"{EMOJI['WARNING']} Binance Futures SDK not available, trying Spot...")
        except Exception as e:
            main_logger.warning(f"{EMOJI['WARNING']} Failed to initialize Futures client: {e}")

        try:
            from binance.client import Client as BinanceSpotClient
            if self.api_key and self.api_secret:
                self.spot_client = BinanceSpotClient(api_key=self.api_key, api_secret=self.api_secret, testnet=self.is_testnet)
            else:
                self.spot_client = BinanceSpotClient()
            self.client_type = "Spot"
            main_logger.info(f"{EMOJI['SUCCESS']} Binance Spot client initialized")
            return
        except ImportError:
            main_logger.warning(f"{EMOJI['WARNING']} Binance Spot SDK not available")
        except Exception as e:
            main_logger.warning(f"{EMOJI['WARNING']} Failed to initialize Spot client: {e}")

        self.client_type = "DataFetcher"
        main_logger.info(f"{EMOJI['INFO']} Using DataFetcher fallback")

    def _test_connection(self):
        """Test Binance connection."""
        try:
            test_symbol = "BTCUSDT"
            price = self.get_current_price(test_symbol)
            if price:
                self._connected = True
                main_logger.info(f"{EMOJI['SUCCESS']} Binance connection OK. {test_symbol} price: {price:.2f}")
                return True

            if self.futures_client and hasattr(self.futures_client, 'time'):
                server_time = self.futures_client.time()
                self._connected = True
                main_logger.info(f"{EMOJI['SUCCESS']} Binance connection OK. Server time: {server_time}")
                return True

            main_logger.error(f"{EMOJI['ERROR']} Cannot connect to Binance")
            self._connected = False
            return False

        except Exception as e:
            main_logger.error(f"{EMOJI['ERROR']} Binance connection test failed: {e}")
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                if self.futures_client and hasattr(self.futures_client, 'ticker_price'):
                    ticker = self.futures_client.ticker_price(symbol=symbol)
                    return float(ticker['price'])

                if self.spot_client and hasattr(self.spot_client, 'get_symbol_ticker'):
                    ticker = self.spot_client.get_symbol_ticker(symbol=symbol)
                    return float(ticker['price'])

                df = data_fetcher.fetch_klines(symbol, config.market.timeframe, 1)
                if df is not None and not df.empty:
                    return float(df['close'].iloc[-1])

                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    main_logger.debug(f"{EMOJI['RETRY']} Price fetch retry {attempt+1}/{MAX_RETRIES} for {symbol}: {e}")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    main_logger.debug(f"{EMOJI['ERROR']} Price fetch failed for {symbol}: {e}")

        return None

    def get_historical_klines(self, symbol: str, interval: str = None, limit: int = 500) -> pd.DataFrame:
        """Get historical klines with retry logic."""
        interval = interval or config.market.timeframe

        for attempt in range(MAX_RETRIES):
            try:
                if self.futures_client and hasattr(self.futures_client, 'klines'):
                    klines = self.futures_client.klines(symbol=symbol, interval=interval, limit=limit)
                    if klines:
                        return self._convert_klines_to_dataframe(klines)

                if self.spot_client and hasattr(self.spot_client, 'get_klines'):
                    klines = self.spot_client.get_klines(symbol=symbol, interval=interval, limit=limit)
                    if klines:
                        return self._convert_klines_to_dataframe(klines)

                result = data_fetcher.fetch_klines(symbol, interval, limit)
                if result is not None and not result.empty:
                    return result

                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    main_logger.debug(f"{EMOJI['RETRY']} Klines fetch retry {attempt+1}/{MAX_RETRIES} for {symbol}: {e}")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    main_logger.debug(f"{EMOJI['ERROR']} Klines fetch failed for {symbol}: {e}")

        return pd.DataFrame()

    def _convert_klines_to_dataframe(self, raw_klines: List) -> pd.DataFrame:
        """Convert raw klines to DataFrame."""
        if not raw_klines:
            return pd.DataFrame()

        df = pd.DataFrame(raw_klines)
        if len(df.columns) >= 6:
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])

        keep_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        df = df[[col for col in keep_cols if col in df.columns]].copy()

        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'open_time' in df.columns:
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('open_time', inplace=True)

        df.sort_index(inplace=True)
        return df


# ==================== CHECK ACTIVE SIGNALS ====================
def check_active_signals(client):
    """Check active signals for resolution with Signal Manager."""
    try:
        active_signals = signal_manager.get_all_active_signals()
        if not active_signals:
            return

        main_logger.debug(f"{EMOJI['MONITOR']} Monitoring {len(active_signals)} active signals")

        for symbol, signal_data in active_signals.items():
            try:
                current_price = client.get_current_price(symbol)
                if current_price is None:
                    continue

                df = client.get_historical_klines(symbol, config.market.timeframe, 3)
                if df.empty:
                    continue

                last_candle = df.iloc[-1]

                # Check signal status using Signal Manager
                signal = signal_manager.get_signal(symbol)
                if signal:
                    status, price_diff, updated_signal = signal_manager.check_active_signal(
                        symbol, current_price, last_candle
                    )

                    status_str = status.value if hasattr(status, 'value') else str(status)

                    if status_str in ["PROFIT", "LOSS", "BREAK_EVEN", "CLOSED"] and updated_signal:
                        pnl = updated_signal.pnl if updated_signal else 0
                        pnl_percent = updated_signal.pnl_percent if updated_signal else 0

                        # Calculate fees
                        entry_fee = updated_signal.entry_price * TRADING_FEE
                        exit_fee = (updated_signal.exit_price or current_price) * TRADING_FEE
                        total_fee = entry_fee + exit_fee
                        adjusted_pnl = pnl - total_fee

                        entry_time = getattr(updated_signal, 'entry_time', None)
                        exit_time = getattr(updated_signal, 'exit_time', datetime.now().isoformat())
                        age_minutes = updated_signal.get_age_minutes() if hasattr(updated_signal, 'get_age_minutes') else 0

                        # Update stats
                        if 'PROFIT' in status_str.upper():
                            bot_stats["signal_outcomes"]["profitable"] += 1
                        elif 'LOSS' in status_str.upper():
                            bot_stats["signal_outcomes"]["losing"] += 1
                        elif 'BREAK' in status_str.upper():
                            bot_stats["signal_outcomes"]["break_even"] += 1
                        bot_stats["signal_outcomes"]["total_pnl"] += adjusted_pnl

                        doc_id = getattr(updated_signal, 'db_doc_id', None)

                        # Handle MongoDB resolution
                        if db_client.is_available():
                            try:
                                update_data = {
                                    'status': status_str,
                                    'exit_price': updated_signal.exit_price or current_price,
                                    'exit_time': str(exit_time) if exit_time else datetime.now().isoformat(),
                                    'pnl': adjusted_pnl,
                                    'pnl_percent': pnl_percent,
                                    'fees': total_fee,
                                    'bars_held': updated_signal.bar_count if hasattr(updated_signal, 'bar_count') else 0,
                                    'age_minutes': age_minutes,
                                    'updated_at': datetime.now().isoformat(),
                                }

                                if doc_id:
                                    db_success = db_client.update_signal_status(doc_id, status_str, update_data)
                                    if db_success:
                                        bot_stats["active_deletions"] = bot_stats.get("active_deletions", 0) + 1
                                        main_logger.info(f"{EMOJI['DELETE']} Signal {doc_id} moved to resolved ({status_str})")
                            except Exception as e:
                                main_logger.error(f"{EMOJI['ERROR']} MongoDB resolution error: {e}")

                        # Remove from Signal Manager
                        signal_manager.remove_signal(symbol)

                        # Send Telegram result
                        if telegram_bot and telegram_bot.enabled:
                            try:
                                telegram_bot.send_result(
                                    symbol=symbol,
                                    signal_type=updated_signal.signal_type,
                                    entry_price=updated_signal.entry_price,
                                    exit_price=updated_signal.exit_price or current_price,
                                    pnl=adjusted_pnl,
                                    pnl_percent=pnl_percent,
                                    status=status_str,
                                    bars_held=updated_signal.bar_count if hasattr(updated_signal, 'bar_count') else 0,
                                    confidence=getattr(updated_signal, 'confidence', 0),
                                    tdi_level=getattr(updated_signal, 'tdi_level', 0),
                                    rrr=getattr(updated_signal, 'rrr', 0),
                                    signal_strength=getattr(updated_signal, 'signal_strength', 'SOFT'),
                                    total_score=getattr(updated_signal, 'total_score', 0),
                                    entry_time=str(entry_time) if entry_time else None,
                                    exit_time=str(exit_time) if exit_time else None,
                                    fees=total_fee,
                                    # NEW v3.3.0
                                    divergence_detected=getattr(updated_signal, 'divergence_detected', False),
                                    candle_pattern=getattr(updated_signal, 'candle_pattern', 'NONE'),
                                    sr_confirmed=getattr(updated_signal, 'sr_confirmed', False),
                                    session=getattr(updated_signal, 'session', 'UNKNOWN'),
                                )
                            except Exception as e:
                                main_logger.warning(f"{EMOJI['WARNING']} Telegram error: {e}")

                        bot_stats["signals_unlocked"] = bot_stats.get("signals_unlocked", 0) + 1
                        main_logger.info(
                            f"{EMOJI['UNLOCK']} {symbol} UNLOCKED - {status_str} | "
                            f"PnL: ${adjusted_pnl:.2f} | "
                            f"Bars: {updated_signal.bar_count if hasattr(updated_signal, 'bar_count') else 0} | "
                            f"Age: {age_minutes:.1f}min"
                        )

            except Exception as e:
                main_logger.error(f"{EMOJI['ERROR']} Error processing {symbol}: {e}")
                continue

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} check_active_signals error: {e}")


# ==================== PROCESS SYMBOL ====================
def process_symbol(symbol: str, strategy_obj, client, state: Dict) -> Tuple[Optional[str], Optional[Dict], Optional[str]]:
    """Process a single symbol - GENERATE phase with data checks."""
    try:
        # Check data sufficiency first
        df = client.get_historical_klines(symbol, limit=200)
        if df.empty:
            main_logger.debug(f"{EMOJI['WARNING']} No data for {symbol}")
            return None, None, None

        if len(df) < MIN_DATA_BARS:
            main_logger.debug(
                f"{EMOJI['WARNING']} Insufficient data for {symbol}: {len(df)} bars (need {MIN_DATA_BARS}+)"
            )
            track_rejection(f"Insufficient data: {len(df)} bars")
            return None, None, None

        current_price = client.get_current_price(symbol)
        if current_price is None:
            main_logger.debug(f"{EMOJI['WARNING']} No current price for {symbol}")
            bot_stats['rejection_reasons']['binance_connection_error'] += 1
            return None, None, None

        # Check if symbol is locked
        if signal_manager.is_symbol_locked(symbol):
            return None, None, None

        if symbol in symbol_last_signal_time:
            time_since = (datetime.now() - symbol_last_signal_time[symbol]).total_seconds() / 60
            if time_since < SYMBOL_COOLDOWN_MINUTES:
                return None, None, None

        htf_df = client.get_historical_klines(symbol, interval=HTF_TIMEFRAME, limit=100)
        if htf_df.empty or len(htf_df) < MIN_HTF_BARS:
            main_logger.debug(
                f"{EMOJI['WARNING']} Insufficient HTF data for {symbol}: {len(htf_df)} bars (need {MIN_HTF_BARS}+)"
            )
            return None, None, None

        strategy_obj.set_htf_trend(htf_df)
        htf_trend = strategy_obj.htf_trend

        analyzed_data = strategy_obj.analyze_data(df)
        if analyzed_data.empty or 'bb_middle' not in analyzed_data.columns:
            main_logger.warning(f"{EMOJI['WARNING']} {symbol}: analyze_data returned empty or missing BB")
            track_rejection("Data analysis failed")
            return None, None, htf_trend

        strategy_obj.lock_current_data(analyzed_data)

        ltf_confirmation = None
        try:
            ltf_confirmed, ltf_confidence, ltf_reason, ltf_direction, ltf_tdi_value = check_ltf_confirmation(symbol, None, client)
            ltf_confirmation = {
                'confirmed': ltf_confirmed,
                'confidence': ltf_confidence,
                'reason': ltf_reason,
                'direction': ltf_direction,
                'tdi_value': ltf_tdi_value,
                'timestamp': time.time()
            }
            if ltf_confirmed:
                main_logger.info(f"{EMOJI['LTF']} {symbol}: LTF CONFIRMED ({ltf_confidence:.2%})")
        except Exception as e:
            main_logger.warning(f"{EMOJI['WARNING']} LTF error for {symbol}: {e}")

        signal_type, signal_data = strategy_obj.generate_signal(analyzed_data, ltf_confirmation)

        if signal_type == "NO_TRADE":
            track_rejection(signal_data.get('reason', 'Unknown'))
            if 'score' in signal_data.get('reason', '').lower():
                bot_stats['score_rejected'] += 1
        elif signal_data.get('total_score', 0) >= MIN_SIGNAL_SCORE:
            bot_stats['score_approved'] += 1

        is_new_signal = signal_type != "NO_TRADE"
        is_not_spamming = (signal_type != state.get("last_signal") or state.get("cooldown", 0) <= 0)

        if is_new_signal and is_not_spamming:
            state["last_signal"] = signal_type
            state["cooldown"] = 15
            signal_data['symbol'] = symbol
            signal_data['current_price'] = current_price
            signal_data['htf_trend'] = htf_trend
            signal_data['entry_price'] = current_price

            rrr_suggestion = get_rrr_suggestion(signal_data)
            signal_data.update({
                'current_rrr': rrr_suggestion['current_rrr'],
                'suggested_rrr': rrr_suggestion['suggested_rrr'],
                'rrr': rrr_suggestion['suggested_rrr'],
                'total_score': rrr_suggestion.get('total_score', 0)
            })
            return signal_type, signal_data, htf_trend

        if state.get("cooldown", 0) > 0:
            state["cooldown"] -= 1

        return None, None, htf_trend

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} {symbol}: {e}")
        return None, None, None


# ==================== SHOULD USE AI ====================
def should_use_ai(symbol: str) -> Tuple[bool, str]:
    if not ai_analyzer or not ai_analyzer.enabled:
        return False, "AI disabled"
    if symbol in ai_cache:
        cache_age = (datetime.now() - ai_cache_timestamp[symbol]).total_seconds()
        if cache_age < AI_CACHE_TTL:
            return False, f"Fresh cache ({cache_age/60:.1f}min)"
    if symbol in ai_last_request_time:
        time_since = (datetime.now() - ai_last_request_time[symbol]).total_seconds()
        if time_since < AI_MIN_INTERVAL_SECONDS:
            return False, f"Cooldown ({AI_MIN_INTERVAL_SECONDS - time_since:.0f}s)"
    ai_stats = ai_analyzer.get_stats() if ai_analyzer else {}
    if ai_stats.get('rate_limited_until'):
        return False, "Rate limited"
    if ai_stats.get('tokens_remaining', 0) < 2000:
        return False, "Low tokens"
    return True, "OK"


# ==================== HANDLE SIGNAL ====================
def handle_signal(symbol: str, signal_type: str, signal_data: Dict, current_price: float, htf_trend: str, client):
    """
    Handle a generated signal - GRADE CHECK → SIGNAL MANAGER → AI ANALYSIS → TELEGRAM.
    """
    global ai_cache, ai_cache_timestamp, bot_stats, ai_last_request_time

    # Add daily signal limit check
    try:
        if hasattr(ai_analyzer, 'signal_limiter'):
            if hasattr(ai_analyzer.signal_limiter, 'get_remaining_slots'):
                remaining = ai_analyzer.signal_limiter.get_remaining_slots()
                if remaining <= 0:
                    main_logger.info(f"{EMOJI.get('LIMIT', '🚫')} Daily signal limit reached, skipping {symbol}")
                    return
    except Exception as e:
        main_logger.warning(f"{EMOJI.get('WARNING', '⚠️')} Error checking signal limit: {e}")

    try:
        entry_price = signal_data.get('entry_price', current_price)

        # ========== STEP 1: BASIC VALIDATION ==========
        if check_duplicate_in_cycle(symbol, signal_type, entry_price)[0]:
            return

        quality_score = signal_data.get('quality_score', 50)
        total_score = signal_data.get('total_score', 0)

        if quality_score < MIN_QUALITY_SCORE:
            return

        # ========== STEP 2: LTF & HTF CONFIRMATION ==========
        ltf_confirmed = signal_data.get('ltf_confirmed', False)
        ltf_confidence = signal_data.get('ltf_confidence', 0)

        if not ltf_confirmed and not signal_data.get('ltf_confidence'):
            ltf_confirmed, ltf_confidence, ltf_reason, _, _ = check_ltf_confirmation(symbol, signal_type, client)
            signal_data['ltf_confirmed'] = ltf_confirmed
            signal_data['ltf_confidence'] = ltf_confidence
            signal_data['ltf_reason'] = ltf_reason

        if not ltf_confirmed:
            bot_stats["ltf_rejected"] += 1
            track_rejection("LTF not confirmed")
            return

        bot_stats["ltf_confirmed"] += 1

        htf_aligned, htf_score, htf_reason = validate_htf_trend(symbol, signal_type, htf_trend, client)
        signal_data['htf_aligned'] = htf_aligned
        signal_data['htf_score'] = htf_score
        signal_data['htf_reason'] = htf_reason

        # ========== STEP 3: GRADE CHECK BEFORE AI ==========
        grade = get_grade(total_score)
        eligible_for_ai, grade_reason = is_grade_eligible_for_ai(total_score)

        grade_emoji = {
            "A": "🏆",
            "B": "🥈",
            "C": "🥉",
            "D": "📉",
            "F": "❌"
        }.get(grade, "❌")

        # Grade C, D, F: REJECT BEFORE AI
        if not eligible_for_ai:
            main_logger.info(
                f"{EMOJI['REJECT']} {grade_emoji} {grade_reason} | "
                f"LTF: {'✅' if ltf_confirmed else '❌'} | HTF: {'✅' if htf_aligned else '❌'} | "
                f"{symbol} {signal_type} @ {current_price:.4f}"
            )
            bot_stats['score_rejected'] += 1
            bot_stats['grade_c_rejected'] = bot_stats.get('grade_c_rejected', 0) + 1
            track_rejection(f"Grade {grade} rejected before AI")
            return

        # Grade B: CONDITIONAL CHECKS
        if grade == "B":
            if not ltf_confirmed:
                main_logger.info(f"{EMOJI['REJECT']} 🥈 Grade B ({total_score}/100) - LTF not confirmed, rejecting before AI for {symbol}")
                bot_stats['score_rejected'] += 1
                track_rejection("Grade B - LTF not confirmed")
                return

            if not htf_aligned:
                main_logger.info(f"{EMOJI['REJECT']} 🥈 Grade B ({total_score}/100) - HTF not aligned, rejecting before AI for {symbol}")
                bot_stats['score_rejected'] += 1
                track_rejection("Grade B - HTF not aligned")
                return

            main_logger.info(f"{EMOJI['GRADE_B']} 🥈 Grade B ({total_score}/100) - Passed LTF+HTF checks, sending to AI for {symbol}")
            bot_stats['grade_b_signals'] = bot_stats.get('grade_b_signals', 0) + 1

        # Grade A: AUTO-PASS TO AI
        if grade == "A":
            main_logger.info(f"{EMOJI['GRADE_A']} 🏆 Grade A ({total_score}/100) - Sending to AI for {symbol}")
            bot_stats['grade_a_signals'] = bot_stats.get('grade_a_signals', 0) + 1

        # Update stats
        bot_stats["signals_generated"] += 1
        bot_stats["last_signal"] = {
            "symbol": symbol,
            "type": signal_type,
            "time": datetime.now().isoformat(),
            "price": current_price,
            "total_score": total_score,
            "grade": grade
        }

        signal_data.update({
            'signal_type': signal_type,
            'side': signal_type,
            'type': signal_type,
            'symbol': symbol,
            'current_price': current_price,
            'htf_trend': htf_trend,
            'entry_price': current_price,
            'timeframe': config.market.timeframe,
            'grade': grade
        })
        signal_data.setdefault('rrr', DEFAULT_RRR)
        signal_data.setdefault('quality_score', 50)
        signal_data.setdefault('total_score', total_score)

        # ========== STEP 4: AI ANALYSIS ==========
        # Check AI Cache first
        if symbol in ai_cache and (datetime.now() - ai_cache_timestamp[symbol]).total_seconds() < AI_CACHE_TTL:
            cached = ai_cache[symbol]
            if cached.get("decision") == 'APPROVE':
                main_logger.info(f"{EMOJI['CACHE']} Using cached AI decision for {symbol}")
                ai_decision = cached.get("decision")
                ai_confidence = cached.get("confidence", 0.7)
                ai_reasoning = cached.get("reasoning", "")
                ai_validated = cached.get("validated", True)
                ai_analysis = cached.get("analysis", {})

                if ai_decision == 'APPROVE':
                    telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
                    if telegram_approved:
                        _send_approved_signal(symbol, signal_type, signal_data, current_price, htf_trend,
                                            ai_analysis, ai_validated, ai_confidence, True, ai_reasoning)
                    else:
                        main_logger.info(f"{EMOJI['REJECT']} {telegram_reason} for {symbol}")
                        bot_stats['score_rejected'] += 1
                elif ai_decision == 'REJECT':
                    bot_stats['ai_decisions']['reject'] += 1
                    main_logger.info(f"{EMOJI['REJECT']} AI rejected {symbol} (cached)")
                return
            elif cached.get("decision") == 'REJECT':
                bot_stats['ai_decisions']['reject'] += 1
                return
            elif cached.get("decision") == 'WAIT':
                bot_stats['ai_decisions']['wait'] += 1
                return

        # Check if AI should be used
        should_use, ai_reason = should_use_ai(symbol)

        if not should_use:
            bot_stats["ai_calls_skipped"] += 1
            main_logger.info(f"{EMOJI['AI']} AI skipped: {ai_reason} for {symbol}")

            # Fallback: Only approve if Grade A AND strong LTF+HTF
            if grade == "A" and ltf_confirmed and htf_aligned:
                fallback_reasoning = f"Grade A signal ({total_score}/100) - AI skipped: {ai_reason}."
                fallback_analysis = {
                    "decision": "APPROVE",
                    "confidence": 0.7,
                    "reasoning": fallback_reasoning,
                    "risk_level": "MEDIUM",
                    "signal_quality": quality_score/100,
                    "market_alignment": htf_score,
                    "probability_success": 0.6,
                    "suggested_rrr": signal_data.get('rrr', DEFAULT_RRR),
                }

                telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
                if telegram_approved:
                    _send_approved_signal(symbol, signal_type, signal_data, current_price, htf_trend,
                                        fallback_analysis, True, 0.7, True, fallback_reasoning)
                else:
                    main_logger.info(f"{EMOJI['REJECT']} {telegram_reason} for {symbol}")
                    bot_stats['score_rejected'] += 1
            else:
                bot_stats['ai_decisions']['wait'] += 1
            return

        # ========== STEP 5: RUN AI ANALYSIS ==========
        main_logger.info(f"{EMOJI['AI']} 🤖 AI analyzing {symbol} (Grade {grade}, Score: {total_score}/100)...")
        ai_last_request_time[symbol] = datetime.now()
        signal_data.update({'min_rrr': MIN_RRR, 'max_rrr': MAX_RRR, 'target_rrr': RRR_TARGET})

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ai_result = loop.run_until_complete(
                asyncio.wait_for(ai_analyzer.analyze_signal(signal_data), timeout=30.0)
            )
            loop.close()

            if ai_result:
                ai_analysis = ai_result.to_dict()
                ai_decision = ai_result.decision
                ai_confidence = ai_result.confidence
                ai_reasoning = ai_result.reasoning
                ai_validated = ai_result.ai_validated
                has_conflict = ai_result.has_conflict

                if hasattr(ai_result, 'suggested_rrr') and ai_result.suggested_rrr:
                    if MIN_RRR <= ai_result.suggested_rrr <= MAX_RRR:
                        signal_data['rrr'] = ai_result.suggested_rrr
                        signal_data['ai_suggested_rrr'] = ai_result.suggested_rrr

                ai_cache[symbol] = {
                    "analysis": ai_analysis,
                    "decision": ai_decision,
                    "confidence": ai_confidence,
                    "reasoning": ai_reasoning,
                    "validated": ai_validated,
                    "has_conflict": has_conflict
                }
                ai_cache_timestamp[symbol] = datetime.now()

                if ai_decision == 'APPROVE':
                    bot_stats['ai_decisions']['approve'] += 1

                    telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
                    if telegram_approved:
                        main_logger.info(f"{EMOJI['APPROVED']} ✅ AI APPROVED {symbol} (Grade {grade}, Score: {total_score}/100) - {ai_reasoning}")
                        _send_approved_signal(symbol, signal_type, signal_data, current_price, htf_trend,
                                            ai_analysis, ai_validated, ai_confidence, False, ai_reasoning)
                    else:
                        main_logger.info(f"{EMOJI['REJECT']} {telegram_reason} for {symbol}")
                        bot_stats['score_rejected'] += 1

                elif ai_decision == 'REJECT':
                    bot_stats['ai_decisions']['reject'] += 1
                    main_logger.info(f"{EMOJI['REJECT']} ❌ AI REJECTED {symbol} (Grade {grade}, Score: {total_score}/100) - {ai_reasoning}")

                elif ai_decision == 'WAIT':
                    bot_stats['ai_decisions']['wait'] += 1
                    main_logger.info(f"{EMOJI['WAIT']} ⏳ AI WAITING on {symbol} - {ai_reasoning}")
            else:
                main_logger.warning(f"{EMOJI['AI']} AI returned None for {symbol}")
                if grade == "A" and ltf_confirmed and htf_aligned:
                    fallback_analysis = {"decision": "APPROVE", "confidence": 0.6,
                                        "reasoning": "AI unavailable - Grade A signal with LTF+HTF confirmed."}
                    telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
                    if telegram_approved:
                        _send_approved_signal(symbol, signal_type, signal_data, current_price, htf_trend,
                                            fallback_analysis, True, 0.6, True, fallback_analysis["reasoning"])
                    else:
                        main_logger.info(f"{EMOJI['REJECT']} {telegram_reason} for {symbol}")
                        bot_stats['score_rejected'] += 1
                else:
                    bot_stats['ai_decisions']['wait'] += 1

        except asyncio.TimeoutError:
            main_logger.error(f"{EMOJI['ERROR']} AI timeout for {symbol}")
            if grade == "A" and ltf_confirmed and htf_aligned:
                fallback_analysis = {"decision": "APPROVE", "confidence": 0.6,
                                    "reasoning": "AI timeout - Grade A signal with LTF+HTF confirmed."}
                telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
                if telegram_approved:
                    _send_approved_signal(symbol, signal_type, signal_data, current_price, htf_trend,
                                        fallback_analysis, True, 0.6, True, fallback_analysis["reasoning"])
                else:
                    main_logger.info(f"{EMOJI['REJECT']} {telegram_reason} for {symbol}")
                    bot_stats['score_rejected'] += 1
            else:
                bot_stats['ai_decisions']['wait'] += 1

        except Exception as e:
            main_logger.error(f"{EMOJI['ERROR']} AI error for {symbol}: {e}")
            if grade == "A" and ltf_confirmed and htf_aligned:
                fallback_analysis = {"decision": "APPROVE", "confidence": 0.5,
                                    "reasoning": f"AI error - Grade A signal with LTF+HTF confirmed."}
                telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
                if telegram_approved:
                    _send_approved_signal(symbol, signal_type, signal_data, current_price, htf_trend,
                                        fallback_analysis, True, 0.5, True, fallback_analysis["reasoning"])
                else:
                    main_logger.info(f"{EMOJI['REJECT']} {telegram_reason} for {symbol}")
                    bot_stats['score_rejected'] += 1
            else:
                bot_stats['ai_decisions']['wait'] += 1

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} handle_signal: {e}")


# ==================== SEND APPROVED SIGNAL ====================
def _send_approved_signal(symbol: str, signal_type: str, signal_data: Dict, current_price: float, htf_trend: str, ai_analysis: Optional[Dict], ai_validated: bool, ai_confidence: float, from_cache: bool, ai_reasoning: str = ""):
    """Send approved signal - LOCK phase using Signal Manager."""
    try:
        total_score = signal_data.get('total_score', 0)
        grade = get_grade(total_score)

        # Double-check grade before sending to Telegram
        telegram_approved, telegram_reason = is_grade_approved_for_telegram(total_score, signal_data)
        if not telegram_approved:
            main_logger.warning(f"{EMOJI['REJECT']} {telegram_reason} - Not sending to Telegram for {symbol}")
            return

        symbol_last_signal_time[symbol] = datetime.now()

        if ai_analysis:
            ai_suggested_rrr = ai_analysis.get('suggested_rrr')
            if ai_suggested_rrr and MIN_RRR <= ai_suggested_rrr <= MAX_RRR:
                signal_data['rrr'] = ai_suggested_rrr

        signal_data.update({
            'ai_validated': ai_validated,
            'ai_decision': 'APPROVE',
            'ai_confidence': ai_confidence,
            'ai_from_cache': from_cache,
            'ai_reasoning': ai_reasoning[:200],
            'entry_price': current_price,
            'entry_time': datetime.now().isoformat(),
            'grade': grade
        })
        signal_data.setdefault('rrr', DEFAULT_RRR)

        if 'stop_loss' not in signal_data or signal_data['stop_loss'] == 0:
            if signal_type == "BUY":
                signal_data['stop_loss'] = current_price * 0.994
                signal_data['take_profit'] = current_price * (1 + (0.006 * signal_data['rrr']))
            else:
                signal_data['stop_loss'] = current_price * 1.006
                signal_data['take_profit'] = current_price * (1 - (0.006 * signal_data['rrr']))

        bot_stats["sniper_signals"] += 1
        signal_strength = signal_data.get('signal_strength', 'SOFT')
        if signal_strength == "HARD":
            bot_stats['signal_strength']['hard'] += 1
        else:
            bot_stats['signal_strength']['soft'] += 1

        rrr = signal_data.get('rrr', DEFAULT_RRR)
        if rrr > 0:
            bot_stats['rrr_stats']['values'].append(rrr)
            values = bot_stats['rrr_stats']['values']
            bot_stats['rrr_stats'].update({
                'min': min(values),
                'max': max(values),
                'avg': sum(values)/len(values)
            })

        grade_emoji = "🏆" if grade == "A" else "🥈" if grade == "B" else "📊"

        # Build feature string for logging
        feature_parts = []
        if signal_data.get('divergence_detected'):
            feature_parts.append("DIV")
            bot_stats['divergence_signals'] = bot_stats.get('divergence_signals', 0) + 1
        if signal_data.get('candle_pattern') and signal_data.get('candle_pattern') != 'NONE':
            feature_parts.append(signal_data.get('candle_pattern')[:8])
            bot_stats['pattern_signals'] = bot_stats.get('pattern_signals', 0) + 1
        if signal_data.get('sr_confirmed'):
            feature_parts.append("S/R")
            bot_stats['sr_signals'] = bot_stats.get('sr_signals', 0) + 1
        if signal_data.get('bb_squeeze'):
            feature_parts.append("SQZ")
            bot_stats['squeeze_signals'] = bot_stats.get('squeeze_signals', 0) + 1
        if signal_data.get('session') and signal_data.get('session') != 'NY':
            bot_stats['session_adjusted'] = bot_stats.get('session_adjusted', 0) + 1

        feature_str = f" [{', '.join(feature_parts)}]" if feature_parts else ""

        main_logger.info(
            f"{EMOJI['PROFIT']} {grade_emoji} SIGNAL EXECUTED: {signal_type} {symbol} | "
            f"Price: {current_price:.4f} | RRR: {rrr:.1f} | Score: {total_score}/100 | Grade: {grade}{feature_str}"
        )

        # Store in MongoDB
        db_doc_id = None
        if db_client.is_available():
            try:
                signal_record = {
                    'symbol': symbol,
                    'signal_type': signal_type,
                    'entry_price': current_price,
                    'stop_loss': signal_data.get('stop_loss', 0),
                    'take_profit': signal_data.get('take_profit', 0),
                    'confidence': signal_data.get('confidence', 0.6),
                    'signal_strength': signal_strength,
                    'status': 'ACTIVE',
                    'timestamp': datetime.now().isoformat(),
                    'entry_time': datetime.now().isoformat(),
                    'htf_trend': htf_trend,
                    'rrr': rrr,
                    'quality_score': signal_data.get('quality_score', 50),
                    'total_score': total_score,
                    'grade': grade,
                    'tdi_level': signal_data.get('tdi_level', 0),
                    'tdi_zone': signal_data.get('tdi_zone', 'NEUTRAL'),
                    'ltf_confirmed': signal_data.get('ltf_confirmed', False),
                    'ltf_confidence': signal_data.get('ltf_confidence', 0),
                    'htf_aligned': signal_data.get('htf_aligned', False),
                    'ai_validated': ai_validated,
                    'ai_decision': 'APPROVE',
                    'ai_confidence': ai_confidence,
                    'ai_reasoning': ai_reasoning,
                    # NEW v3.3.0
                    'divergence_detected': signal_data.get('divergence_detected', False),
                    'divergence_strength': signal_data.get('divergence_strength', 0.0),
                    'candle_pattern': signal_data.get('candle_pattern', 'NONE'),
                    'candle_pattern_confidence': signal_data.get('candle_pattern_confidence', 0.0),
                    'sr_confirmed': signal_data.get('sr_confirmed', False),
                    'bb_squeeze': signal_data.get('bb_squeeze', False),
                    'session': signal_data.get('session', 'UNKNOWN'),
                    'session_multiplier': signal_data.get('session_multiplier', 1.0),
                    'strategy_version': 'v3.3.0-enhanced-super-tdi-15m'
                }
                db_doc_id = db_client.save_signal(signal_record)
                if db_doc_id:
                    signal_data['db_doc_id'] = db_doc_id
                    main_logger.info(f"{EMOJI['DB']} Signal saved with doc_id: {db_doc_id}")
            except Exception as e:
                main_logger.warning(f"{EMOJI['WARNING']} MongoDB save error: {e}")

        # ========== LOCK SYMBOL WITH SIGNAL MANAGER ==========
        try:
            signal_obj = signal_manager.lock_symbol(
                symbol=symbol,
                signal_type=signal_type,
                entry_price=current_price,
                raw_data=signal_data,
                stop_loss=signal_data.get('stop_loss', 0),
                take_profit=signal_data.get('take_profit', 0),
                confidence=signal_data.get('confidence', 0.6),
                rrr=rrr,
                grade=grade,
                total_score=total_score,
                signal_strength=signal_strength,
                tdi_level=signal_data.get('tdi_level', 0),
                tdi_zone=signal_data.get('tdi_zone', 'NEUTRAL'),
                htf_trend=htf_trend,
                ltf_confirmed=signal_data.get('ltf_confirmed', False),
                ltf_confidence=signal_data.get('ltf_confidence', 0),
                htf_aligned=signal_data.get('htf_aligned', False),
                db_doc_id=db_doc_id,
                ai_decision='APPROVE',
                ai_confidence=ai_confidence,
                ai_reasoning=ai_reasoning,
                ai_validated=ai_validated,
                # NEW v3.3.0
                divergence_detected=signal_data.get('divergence_detected', False),
                divergence_strength=signal_data.get('divergence_strength', 0.0),
                candle_pattern=signal_data.get('candle_pattern', 'NONE'),
                sr_confirmed=signal_data.get('sr_confirmed', False),
                bb_squeeze=signal_data.get('bb_squeeze', False),
                session=signal_data.get('session', 'UNKNOWN'),
                session_multiplier=signal_data.get('session_multiplier', 1.0),
            )

            if signal_obj:
                main_logger.info(
                    f"{EMOJI['LOCK']} {symbol} locked (RRR: {rrr:.1f}, Score: {total_score}/100, "
                    f"Grade: {grade}, DocID: {db_doc_id})"
                )
                bot_stats["signal_outcomes"]["active"] += 1
                bot_stats["signals_processed"] += 1
            else:
                main_logger.error(f"{EMOJI['ERROR']} Failed to lock {symbol}")

        except Exception as e:
            main_logger.error(f"{EMOJI['ERROR']} Lock error: {e}")

        # Send Telegram
        if telegram_bot and telegram_bot.enabled:
            try:
                telegram_bot.send_signal(
                    symbol=symbol,
                    signal_type=signal_type,
                    entry_price=current_price,
                    stop_loss=signal_data.get('stop_loss', 0),
                    take_profit=signal_data.get('take_profit', 0),
                    confidence=signal_data.get('confidence', 0.5),
                    ai_decision='APPROVE',
                    ai_confidence=ai_confidence,
                    rrr=rrr,
                    quality_score=signal_data.get('quality_score', 50),
                    signal_strength=signal_strength,
                    tdi_level=signal_data.get('tdi_level', 0),
                    tdi_zone=signal_data.get('tdi_zone', 'NEUTRAL'),
                    ltf_confirmed=signal_data.get('ltf_confirmed', False),
                    ltf_confidence=signal_data.get('ltf_confidence', 0),
                    htf_trend=htf_trend,
                    htf_aligned=signal_data.get('htf_aligned', False),
                    ai_reasoning=ai_reasoning,
                    total_score=total_score,
                    grade=grade,
                    component_scores=signal_data.get('component_scores', {}),
                    ai_suggested_rrr=signal_data.get('ai_suggested_rrr'),
                    leverage_recommendation=signal_data.get('leverage_recommendation'),
                    # NEW v3.3.0
                    divergence_detected=signal_data.get('divergence_detected', False),
                    divergence_strength=signal_data.get('divergence_strength', 0.0),
                    candle_pattern=signal_data.get('candle_pattern', 'NONE'),
                    sr_confirmed=signal_data.get('sr_confirmed', False),
                    bb_squeeze=signal_data.get('bb_squeeze', False),
                    session=signal_data.get('session', 'UNKNOWN'),
                    session_multiplier=signal_data.get('session_multiplier', 1.0),
                )
            except Exception as e:
                main_logger.warning(f"{EMOJI['WARNING']} Telegram error: {e}")

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} _send_approved_signal: {e}")


# ==================== MAIN PROCESSING LOOP ====================
def run_processing_loop():
    global running
    main_logger.info(f"{EMOJI['START']} Starting processing loop v3.3.0 with Signal Manager...")
    main_logger.info(f"{EMOJI['DIVERGENCE']} ✨ New: Divergence Detection")
    main_logger.info(f"{EMOJI['PATTERN']} ✨ New: Candle Pattern Recognition")
    main_logger.info(f"{EMOJI['S_R']} ✨ New: Support/Resistance Levels")
    main_logger.info(f"{EMOJI['BB']} ✨ New: BB Squeeze Detection")
    main_logger.info(f"{EMOJI['SESSION']} ✨ New: Session-Based Filtering")

    try:
        client = BinanceDataClient()

        if not client.is_connected():
            main_logger.error(f"{EMOJI['ERROR']} Binance connection failed. Please check your configuration.")
            main_logger.error(f"{EMOJI['INFO']} API Key: {'Set' if client.api_key else 'Not Set'}")
            main_logger.error(f"{EMOJI['INFO']} Testnet: {client.is_testnet}")
            return

        strategy_obj = strategy

        if db_client.is_available():
            main_logger.info(f"{EMOJI['SUCCESS']} MongoDB connected successfully")
        else:
            main_logger.warning(f"{EMOJI['WARNING']} MongoDB not available - running in memory-only mode")

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} Init error: {e}")
        return

    symbols = list(client.price_precisions.keys()) if client.price_precisions else config.market.symbols
    if not symbols:
        main_logger.error(f"{EMOJI['ERROR']} No symbols configured")
        return

    # Load active signals from MongoDB
    load_active_signals()

    symbol_state = {symbol: {"last_signal": None, "cooldown": 0} for symbol in symbols}
    main_logger.info(f"{EMOJI['SUCCESS']} Monitoring {len(symbols)} symbols")
    main_logger.info(f"{EMOJI['SIGNAL']} Signal Manager tracking {len(signal_manager.active_signals)} signals")

    while running:
        try:
            cycle_start = time.time()
            check_active_signals(client)
            signals_this_cycle = 0

            for symbol in symbols:
                if not running or signals_this_cycle >= MAX_SIGNALS_PER_CYCLE:
                    break
                try:
                    signal_type, signal_data, htf_trend = process_symbol(
                        symbol, strategy_obj, client, symbol_state[symbol]
                    )
                    if signal_type and signal_data:
                        current_price = client.get_current_price(symbol)
                        handle_signal(
                            symbol,
                            signal_type,
                            signal_data,
                            current_price or signal_data.get('entry_price', 0),
                            htf_trend or 'NEUTRAL',
                            client
                        )
                        signals_this_cycle += 1
                    bot_stats["symbols_processed"] += 1
                except Exception as e:
                    main_logger.error(f"{EMOJI['ERROR']} {symbol}: {e}")
                    bot_stats["errors"] += 1

            bot_stats["cycles_completed"] += 1
            cycle_time = time.time() - cycle_start
            active_count = len(signal_manager.active_signals) if signal_manager else 0

            if bot_stats["cycles_completed"] % 10 == 0:
                rejection_report = _get_rejection_report()
                main_logger.info(
                    f"{EMOJI['AI']} 🤖 Cycle {bot_stats['cycles_completed']} | "
                    f"Active: {active_count} | "
                    f"Score: A{bot_stats.get('score_approved', 0)}/R{bot_stats.get('score_rejected', 0)} | "
                    f"LTF: {bot_stats.get('ltf_confirmed', 0)}/{bot_stats.get('ltf_rejected', 0)} | "
                    f"Grades: A{bot_stats.get('grade_a_signals', 0)}/B{bot_stats.get('grade_b_signals', 0)}/C{bot_stats.get('grade_c_rejected', 0)} | "
                    f"Features: DIV{bot_stats.get('divergence_signals', 0)}/PAT{bot_stats.get('pattern_signals', 0)}/SR{bot_stats.get('sr_signals', 0)}"
                )
                if rejection_report['total_rejections'] > 0:
                    main_logger.info(f"{EMOJI['REJECT']} Rejection: {rejection_report['acceptance_rate']}% acceptance")

            main_logger.info(
                f"{EMOJI['SUCCESS']} ✅ Cycle {bot_stats['cycles_completed']} complete: "
                f"{signals_this_cycle} signals, {active_count} active, {cycle_time:.2f}s"
            )

            if running:
                sleep_time = max(0, config.market.polling_interval_seconds - cycle_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            running = False
            break
        except Exception as e:
            main_logger.error(f"{EMOJI['ERROR']} Loop error: {e}")
            time.sleep(10)

    main_logger.info(f"{EMOJI['STOP']} Processing loop stopped")


def run_health_server():
    try:
        server = HTTPServer(('0.0.0.0', config.deployment.port), HealthHandler)
        server.serve_forever()
    except Exception as e:
        main_logger.error(f"Health server error: {e}")


def signal_handler(sig, frame):
    global running
    main_logger.info(f"{EMOJI['STOP']} Shutdown signal ({sig})")
    running = False


def main():
    global running
    main_logger.info("=" * 70)
    main_logger.info(f"{EMOJI['START']} 🤖 AI TRADING BOT v3.3.0 - SUPER TDI STRATEGY with ENHANCED FEATURES")
    main_logger.info(f"{EMOJI['GRADE_A']} Grade A (80+): Auto-approve with AI → Signal Manager Lock")
    main_logger.info(f"{EMOJI['GRADE_B']} Grade B (70-79): Conditional with AI → Signal Manager Lock")
    main_logger.info(f"{EMOJI['GRADE_C']} Grade C (60-69): REJECTED before AI - Tokens saved!")
    main_logger.info(f"{EMOJI['DIVERGENCE']} 🔄 Divergence Detection: Bullish/Bearish TDI divergence")
    main_logger.info(f"{EMOJI['PATTERN']} 🕯️ Candle Patterns: Doji, Engulfing, Hammer, Star")
    main_logger.info(f"{EMOJI['S_R']} 📊 Support/Resistance: Dynamic levels for SL/TP")
    main_logger.info(f"{EMOJI['BB']} 📉 BB Squeeze: Low volatility breakout detection")
    main_logger.info(f"{EMOJI['SESSION']} 🌍 Session Filter: Asian/London/NY session awareness")
    main_logger.info(f"{EMOJI['SIGNAL']} Signal Manager: Active tracking, duplicate prevention, auto-resolution")
    main_logger.info(f"{EMOJI['DB']} Database: {'MongoDB' if config.mongodb.enabled else 'In-Memory'}")
    main_logger.info("=" * 70)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot_stats["status"] = "running"
    bot_stats["start_time"] = datetime.now().isoformat()

    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        run_processing_loop()
    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} Fatal: {e}")

    rejection_report = _get_rejection_report()
    main_logger.info(f"{EMOJI['REJECT']} Final Rejection: {json.dumps(rejection_report, indent=2)}")

    # Signal Manager final stats
    signal_stats = signal_manager.get_stats()
    main_logger.info(f"{EMOJI['SIGNAL']} Signal Manager Stats: {json.dumps(signal_stats, indent=2)}")

    main_logger.info(f"{EMOJI['STOP']} Shutting down...")
    try:
        data_fetcher.cleanup()
        if db_client:
            db_client.cleanup()
    except:
        pass
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        main_logger.error(f"Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)
