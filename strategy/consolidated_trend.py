"""
HYBRID STRATEGY: Super TDI + Super Bollinger Bands + Multi-Timeframe
VERSION: 3.3.0 - MAJOR UPDATE: Added Divergence, Candle Patterns, S/R, Session Filtering
"""

import pandas as pd
import numpy as np
import logging
import time
from typing import Tuple, Dict, Optional, Any, List
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
import threading

# Local imports
from utils.indicators import (
    Indicators,
    calculate_heikin_ashi,
    detect_divergence,
    detect_candle_patterns,
    calculate_support_resistance,
    detect_bb_squeeze,
    calculate_vwap,
    get_trading_session,
    get_session_multiplier,
)
from settings import config, Config

# Configure logging
logger = logging.getLogger(__name__)
strategy_logger = logging.getLogger("strategy")

EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DEBUG": "🔍",
    "SIGNAL": "📡",
    "BUY": "🟢",
    "SELL": "🔴",
    "HTF": "📊",
    "RISK": "🎯",
    "REGIME": "📈",
    "VALIDATE": "✔️",
    "DEBOUNCE": "🔄",
    "FEE": "💰",
    "LEVERAGE": "⚡",
    "SNIPER": "🎯",
    "STRUCTURE": "🏗️",
    "MSS": "🔄",
    "FVG": "📉",
    "LIQUIDITY": "💧",
    "LTF": "⏱️",
    "RRR": "📈",
    "CONFLICT": "⚔️",
    "HARD": "🔴",
    "SOFT": "🟡",
    "CROSSOVER": "🔀",
    "ZONE": "🎯",
    "REJECT": "🚫",
    "WAIT": "⏳",
    "TDI": "📈",
    "BB": "📉",
    "HEIKIN": "🕯️",
    "CANDLE": "🕯️",
    "REVERSAL": "↩️",
    "FEES": "💰",
    "PROFIT": "💰",
    "LOSS": "💸",
    "EXECUTE": "⚡",
    "OVERRIDE": "🔄",
    "REJECTED": "🚫",
    "APPROVED": "✅",
    "WAITING": "⏳",
    "CACHE": "💾",
    "RATE": "🚀",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "MONITOR": "📊",
    "RESULT": "📈",
    "DELETE": "🗑️",
    "EXPIRED": "⌛",
    "HEALTH": "💚",
    "AI": "🤖",
    "FIREBASE": "🔥",
    "TELEGRAM": "📨",
    "SYNC": "🔄",
    "RETRY": "↩️",
    "SCORE": "🎯",
    "DECAY": "⏳",
    "GRADE_A": "🏆",
    "GRADE_B": "🥈",
    "GRADE_C": "🥉",
    "DIVERGENCE": "↩️",
    "PATTERN": "🕯️",
    "S_R": "📊",
    "SESSION": "🌍",
}


# =============== FEE CONFIGURATION ===============

class FeeConfig:
    """Trading fee configuration for Binance Futures."""

    FUTURES_TAKER_FEE = 0.0004  # 0.04%
    FUTURES_MAKER_FEE = 0.0002  # 0.02%
    SLIPPAGE_BUFFER = 0.0003    # 0.03%
    MIN_PROFITABLE_SL = 0.005   # 0.50% minimum

    @classmethod
    def get_total_fee_impact(cls) -> float:
        return (cls.FUTURES_TAKER_FEE * 2) + cls.SLIPPAGE_BUFFER

    @classmethod
    def get_min_sl_percent(cls) -> float:
        total_fees = cls.get_total_fee_impact()
        return max(total_fees * 3, cls.MIN_PROFITABLE_SL)

    @classmethod
    def is_profitable(cls, sl_percent: float, tp_percent: float) -> bool:
        total_fees = cls.get_total_fee_impact()
        net_profit = tp_percent - sl_percent - total_fees
        return net_profit > 0.001


def log_strategy_operation(operation: str, status: str, details: Optional[Dict] = None,
                           emoji: str = "", error: Optional[Exception] = None):
    """Log strategy operations with structured format."""
    timestamp = datetime.now().isoformat()
    log_message = f"[{timestamp}] {emoji} STRATEGY_{operation}: {status}"

    if details:
        safe_details = {}
        for k, v in details.items():
            if isinstance(v, float):
                safe_details[k] = round(v, 4)
            else:
                safe_details[k] = v
        log_message += f" | Details: {safe_details}"

    if error:
        log_message += f" | Error: {str(error)}"

    if status == "FAILURE":
        strategy_logger.error(log_message)
    elif status == "WARNING":
        strategy_logger.warning(log_message)
    elif status == "START":
        strategy_logger.debug(log_message)
    else:
        strategy_logger.info(log_message)


# =============== DATA LOCK FOR TIME SYNCHRONIZATION ===============

class DataLock:
    """Time-based data lock to prevent staleness between LTF and signal generation."""
    def __init__(self, max_age_ms: int = 500):
        self.locked_data = None
        self.lock_time = None
        self.max_age_ms = max_age_ms
        self.candle_index = None

    def lock(self, df: pd.DataFrame, indicators: Dict[str, Any]):
        """Lock current data snapshot."""
        self.locked_data = {
            'df': df.copy(),
            'indicators': indicators.copy()
        }
        self.lock_time = time.time()
        self.candle_index = df.index[-1] if not df.empty else None
        strategy_logger.debug(f"{EMOJI['LOCK']} Data locked at index {self.candle_index}")

    def get_locked_data(self) -> Optional[Dict[str, Any]]:
        """Get locked data if still valid."""
        if self.locked_data is None or self.lock_time is None:
            return None

        age_ms = (time.time() - self.lock_time) * 1000
        if age_ms > self.max_age_ms:
            strategy_logger.warning(f"{EMOJI['DECAY']} Data expired: {age_ms:.0f}ms > {self.max_age_ms}ms")
            return None

        strategy_logger.debug(f"{EMOJI['LOCK']} Using locked data (age: {age_ms:.0f}ms)")
        return self.locked_data

    def is_same_candle(self, df: pd.DataFrame) -> bool:
        """Check if current DataFrame is on same candle as locked data."""
        if self.candle_index is None or df.empty:
            return False
        return df.index[-1] == self.candle_index

    def clear(self):
        """Clear locked data."""
        self.locked_data = None
        self.lock_time = None
        self.candle_index = None


# =============== SUPER TDI DETECTOR ===============

class SuperTDIDetector:
    """
    Super TDI (Advanced Traders Dynamic Index)

    Key Levels:
    - 25: OVERSOLD (Hard Buy Zone - 2x risk)
    - 35: SOFT_BUY (Soft Buy Zone - 1x risk)
    - 50: CENTER_LINE (Neutral)
    - 65: SOFT_SELL (Soft Sell Zone - 1x risk)
    - 75: OVERBOUGHT (Hard Sell Zone - 2x risk)

    NO_TRADE zone: 50-65 (only applies when LTF NOT confirmed)
    """

    # Standardized zone constants
    ZONE_OVERSOLD = "OVERSOLD"       # 0-25
    ZONE_SOFT_BUY = "SOFT_BUY"       # 25-35
    ZONE_BUY_ZONE = "BUY_ZONE"       # 35-50
    ZONE_NO_TRADE = "NO_TRADE"       # 50-65
    ZONE_SOFT_SELL = "SOFT_SELL"     # 65-75
    ZONE_OVERBOUGHT = "OVERBOUGHT"   # 75-100

    def __init__(self):
        # TDI Levels
        self.OVERSOLD = 25.0
        self.SOFT_BUY = 35.0
        self.CENTER_LINE = 50.0
        self.NO_TRADE_START = 50.0
        self.NO_TRADE_END = 65.0
        self.SOFT_SELL = 65.0
        self.OVERBOUGHT = 75.0

        # Confidence thresholds
        self.MIN_CONFIDENCE_HARD = 0.65
        self.MIN_CONFIDENCE_SOFT = 0.55

        # Risk multipliers
        self.RISK_MULTIPLIER_HARD = 2.0
        self.RISK_MULTIPLIER_SOFT = 1.0

    def get_zone(self, tdi_value: float) -> str:
        """Standardized zone classification."""
        if tdi_value <= self.OVERSOLD:
            return self.ZONE_OVERSOLD
        elif tdi_value <= self.SOFT_BUY:
            return self.ZONE_SOFT_BUY
        elif tdi_value < self.CENTER_LINE:
            return self.ZONE_BUY_ZONE
        elif tdi_value < self.SOFT_SELL:
            return self.ZONE_NO_TRADE
        elif tdi_value < self.OVERBOUGHT:
            return self.ZONE_SOFT_SELL
        else:
            return self.ZONE_OVERBOUGHT

    def get_trading_session(self) -> str:
        """Get current trading session."""
        from utils.indicators import get_trading_session
        return get_trading_session()

    def get_session_multiplier(self, session: str) -> float:
        """Get session multiplier for confidence adjustment."""
        from utils.indicators import get_session_multiplier
        return get_session_multiplier(session)

    def detect_opportunity(self, df: pd.DataFrame, ltf_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        ✅ UPDATED v3.3.0: Enhanced with divergence, candle patterns, S/R, session filtering.
        """
        if df is None or df.empty or len(df) < 20:
            return self._no_opportunity("Insufficient data")

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        # TDI Values
        tdi_slow = last.get('tdi_slow_ma', 50)
        tdi_fast = last.get('tdi_fast_ma', 50)
        tdi_slow_prev = prev.get('tdi_slow_ma', 50)
        tdi_fast_prev = prev.get('tdi_fast_ma', 50)

        # BB Values
        bb_lower = last.get('bb_lower', 0)
        bb_upper = last.get('bb_upper', 0)

        # HA Values
        ha_color = last.get('ha_color', 0)
        ha_prev_color = prev.get('ha_color', 0)
        ha_reversal = ha_color != ha_prev_color
        ha_close = last.get('ha_close', last.get('close', 0))
        ha_prev_close = prev.get('ha_close', prev.get('close', 0))
        ha_low = last.get('ha_low', last.get('low', 0))
        ha_high = last.get('ha_high', last.get('high', 0))

        # Candle Values
        candle_body = abs(last.get('close', 0) - last.get('open', 0))
        prev_candle_body = abs(prev.get('close', 0) - prev.get('open', 0))
        volume_ratio = last.get('volume_ratio', 1)

        # ===== NEW: Divergence Detection =====
        divergence_bullish = last.get('divergence_bullish', False)
        divergence_bearish = last.get('divergence_bearish', False)
        divergence_strength = last.get('divergence_strength', 0.0)

        # ===== NEW: Candle Patterns =====
        candle_pattern = last.get('candle_pattern', 'NONE')
        candle_pattern_direction = last.get('candle_pattern_direction', 'NONE')
        candle_pattern_confidence = last.get('candle_pattern_confidence', 0.0)

        # ===== NEW: Support/Resistance =====
        nearest_support = last.get('nearest_support', 0)
        nearest_resistance = last.get('nearest_resistance', 0)
        sr_position = last.get('sr_position', 'UNKNOWN')
        distance_to_support = last.get('distance_to_support_pct', 0)
        distance_to_resistance = last.get('distance_to_resistance_pct', 0)

        # ===== NEW: BB Squeeze =====
        bb_squeeze = last.get('bb_squeeze', False)
        bb_squeeze_direction = last.get('bb_squeeze_direction', 'NEUTRAL')

        # ===== NEW: VWAP =====
        vwap_position = last.get('vwap_position_pct', 0)

        # ===== NEW: Session =====
        session = get_trading_session()
        session_multiplier = get_session_multiplier(session)

        # Standardized zone
        tdi_zone = self.get_zone(tdi_slow)

        # LTF confirmation
        ltf_confirmed = ltf_data.get('confirmed', False) if ltf_data else False

        # Skip no-trade zone when LTF not confirmed
        if tdi_zone == self.ZONE_NO_TRADE and not ltf_confirmed:
            strategy_logger.info(f"{EMOJI['REJECT']} NO TRADE ZONE: TDI at {tdi_slow:.2f} (50-65) - LTF not confirmed")
            return self._no_opportunity(f"NO TRADE ZONE: TDI {tdi_slow:.2f}")
        elif tdi_zone == self.ZONE_NO_TRADE and ltf_confirmed:
            strategy_logger.info(f"{EMOJI['OVERRIDE']} NO TRADE ZONE OVERRIDDEN: TDI at {tdi_slow:.2f} - LTF confirmed")
            if ltf_data.get('direction', '') == 'BUY':
                tdi_zone = self.ZONE_BUY_ZONE
            elif ltf_data.get('direction', '') == 'SELL':
                tdi_zone = self.ZONE_SOFT_SELL

        # ========== CROSSOVER ==========
        is_bullish = tdi_fast > tdi_slow
        is_bearish = tdi_fast < tdi_slow
        bullish_cross = tdi_fast > tdi_slow and tdi_fast_prev <= tdi_slow_prev
        bearish_cross = tdi_fast < tdi_slow and tdi_fast_prev >= tdi_slow_prev

        # ========== BB INTERACTION ==========
        bb_buy = ha_low <= bb_lower if bb_lower > 0 else False
        bb_sell = ha_high >= bb_upper if bb_upper > 0 else False

        # ========== ENHANCED REVERSAL ==========
        # Simple reversal (existing)
        reversal_buy = (ha_close > ha_prev_close or ha_color == 1) and candle_body < prev_candle_body * 1.5
        reversal_sell = (ha_close < ha_prev_close or ha_color == -1) and candle_body < prev_candle_body * 1.5

        # ===== NEW: Enhanced reversal with patterns and divergence =====
        enhanced_reversal_buy = False
        enhanced_reversal_sell = False
        enhanced_reason = []

        # Check for bullish reversal signals
        if (divergence_bullish or
            candle_pattern_direction == 'BUY' or
            (bb_buy and ha_color == 1) or
            (bb_squeeze and bb_squeeze_direction == 'BULLISH')):
            enhanced_reversal_buy = True
            if divergence_bullish:
                enhanced_reason.append("Bullish divergence")
            if candle_pattern_direction == 'BUY':
                enhanced_reason.append(f"{candle_pattern}")
            if bb_buy and ha_color == 1:
                enhanced_reason.append("BB touch + HA bullish")

        # Check for bearish reversal signals
        if (divergence_bearish or
            candle_pattern_direction == 'SELL' or
            (bb_sell and ha_color == -1) or
            (bb_squeeze and bb_squeeze_direction == 'BEARISH')):
            enhanced_reversal_sell = True
            if divergence_bearish:
                enhanced_reason.append("Bearish divergence")
            if candle_pattern_direction == 'SELL':
                enhanced_reason.append(f"{candle_pattern}")
            if bb_sell and ha_color == -1:
                enhanced_reason.append("BB touch + HA bearish")

        # ===== NEW: Session confidence adjustment =====
        session_info = f"{session} session ({session_multiplier:.1f}x)"

        # ========== EVALUATE BUY ==========
        buy_zones = [self.ZONE_OVERSOLD, self.ZONE_SOFT_BUY, self.ZONE_BUY_ZONE]
        if tdi_zone in buy_zones:
            # Use enhanced reversal if available, else fallback to simple
            final_reversal_buy = enhanced_reversal_buy or reversal_buy

            # S/R confirmation: price near support
            sr_buy_confirmation = False
            if nearest_support > 0:
                # Price within 2% of support
                sr_buy_confirmation = distance_to_support < 2.0

            buy_conditions = is_bullish and bb_buy and final_reversal_buy

            # Extra confidence from S/R
            if sr_buy_confirmation:
                buy_conditions = buy_conditions or (is_bullish and bb_buy and sr_buy_confirmation)

            if tdi_zone == self.ZONE_OVERSOLD:
                buy_conditions = buy_conditions and tdi_slow <= self.OVERSOLD

            if buy_conditions:
                confidence = 0.55
                if tdi_zone == self.ZONE_OVERSOLD:
                    confidence += 0.25
                    signal_strength = "HARD"
                    risk_multiplier = 2.0
                    min_confidence = 0.65
                elif tdi_zone == self.ZONE_SOFT_BUY:
                    confidence += 0.15
                    signal_strength = "SOFT"
                    risk_multiplier = 1.0
                    min_confidence = 0.55
                else:
                    confidence += 0.10
                    signal_strength = "SOFT"
                    risk_multiplier = 1.0
                    min_confidence = 0.55

                # Divergence bonus
                if divergence_bullish:
                    confidence += 0.25
                    strategy_logger.info(f"{EMOJI['DIVERGENCE']} Bullish divergence detected! +0.25 confidence")

                # Candle pattern bonus
                if candle_pattern_direction == 'BUY':
                    confidence += candle_pattern_confidence * 0.15
                    strategy_logger.info(f"{EMOJI['PATTERN']} {candle_pattern} detected! +{candle_pattern_confidence*0.15:.2f} confidence")

                # S/R bonus
                if sr_buy_confirmation:
                    confidence += 0.10
                    strategy_logger.info(f"{EMOJI['S_R']} Near support (+0.10 confidence)")

                # BB Squeeze bonus
                if bb_squeeze and bb_squeeze_direction == 'BULLISH':
                    confidence += 0.10
                    strategy_logger.info(f"{EMOJI['BB']} BB Squeeze bullish breakout (+0.10 confidence)")

                # Session adjustment
                confidence *= session_multiplier
                if session != "NY":
                    strategy_logger.info(f"{EMOJI['SESSION']} {session_info} - confidence adjusted to {confidence:.2%}")

                # Crossover bonus
                if bullish_cross:
                    confidence += 0.10
                if ha_color == 1:
                    confidence += 0.05
                if volume_ratio > 1.5:
                    confidence += 0.05

                # LTF confirmation adds confidence
                if ltf_confirmed:
                    ltf_confidence = ltf_data.get('confidence', 0)
                    confidence += ltf_confidence * 0.15

                confidence = min(0.95, confidence)

                if confidence >= min_confidence:
                    quality_score = int(confidence * 100)
                    if signal_strength == "HARD":
                        quality_score += 10

                    # Build reason
                    reason_parts = [f'BUY: TDI {tdi_slow:.2f} ({tdi_zone})']
                    if divergence_bullish:
                        reason_parts.append("Bullish divergence")
                    if candle_pattern_direction == 'BUY':
                        reason_parts.append(candle_pattern)
                    if sr_buy_confirmation:
                        reason_parts.append(f"Near support {nearest_support:.4f}")
                    if bb_squeeze and bb_squeeze_direction == 'BULLISH':
                        reason_parts.append("BB squeeze breakout")
                    if session != "NY":
                        reason_parts.append(session_info)

                    rrr_suggested = self._suggest_rrr(quality_score, signal_strength, tdi_zone)

                    return {
                        'opportunity': True,
                        'direction': 'BUY',
                        'tdi_level': tdi_slow,
                        'tdi_zone': tdi_zone,
                        'tdi_crossover': is_bullish,
                        'bb_interaction': 'touch',
                        'ha_reversal': ha_reversal,
                        'candle_reversal': final_reversal_buy,
                        'confidence': confidence,
                        'signal_strength': signal_strength,
                        'risk_multiplier': risk_multiplier,
                        'quality_score': quality_score,
                        'rrr_suggested': rrr_suggested,
                        'reason': ' | '.join(reason_parts),
                        # New fields
                        'divergence_detected': divergence_bullish,
                        'divergence_strength': divergence_strength,
                        'candle_pattern': candle_pattern,
                        'candle_pattern_confidence': candle_pattern_confidence,
                        'sr_confirmed': sr_buy_confirmation,
                        'bb_squeeze': bb_squeeze,
                        'session': session,
                        'session_multiplier': session_multiplier,
                    }

        # ========== EVALUATE SELL ==========
        sell_zones = [self.ZONE_OVERBOUGHT, self.ZONE_SOFT_SELL]
        if tdi_zone in sell_zones:
            # Use enhanced reversal if available, else fallback to simple
            final_reversal_sell = enhanced_reversal_sell or reversal_sell

            # S/R confirmation: price near resistance
            sr_sell_confirmation = False
            if nearest_resistance > 0:
                # Price within 2% of resistance
                sr_sell_confirmation = distance_to_resistance < 2.0

            sell_conditions = is_bearish and bb_sell and final_reversal_sell

            # Extra confidence from S/R
            if sr_sell_confirmation:
                sell_conditions = sell_conditions or (is_bearish and bb_sell and sr_sell_confirmation)

            if tdi_zone == self.ZONE_OVERBOUGHT:
                sell_conditions = sell_conditions and tdi_slow >= self.OVERBOUGHT

            if sell_conditions:
                confidence = 0.55
                if tdi_zone == self.ZONE_OVERBOUGHT:
                    confidence += 0.25
                    signal_strength = "HARD"
                    risk_multiplier = 2.0
                    min_confidence = 0.65
                elif tdi_zone == self.ZONE_SOFT_SELL:
                    confidence += 0.15
                    signal_strength = "SOFT"
                    risk_multiplier = 1.0
                    min_confidence = 0.55
                else:
                    confidence += 0.10
                    signal_strength = "SOFT"
                    risk_multiplier = 1.0
                    min_confidence = 0.55

                # Divergence bonus
                if divergence_bearish:
                    confidence += 0.25
                    strategy_logger.info(f"{EMOJI['DIVERGENCE']} Bearish divergence detected! +0.25 confidence")

                # Candle pattern bonus
                if candle_pattern_direction == 'SELL':
                    confidence += candle_pattern_confidence * 0.15
                    strategy_logger.info(f"{EMOJI['PATTERN']} {candle_pattern} detected! +{candle_pattern_confidence*0.15:.2f} confidence")

                # S/R bonus
                if sr_sell_confirmation:
                    confidence += 0.10
                    strategy_logger.info(f"{EMOJI['S_R']} Near resistance (+0.10 confidence)")

                # BB Squeeze bonus
                if bb_squeeze and bb_squeeze_direction == 'BEARISH':
                    confidence += 0.10
                    strategy_logger.info(f"{EMOJI['BB']} BB Squeeze bearish breakout (+0.10 confidence)")

                # Session adjustment
                confidence *= session_multiplier
                if session != "NY":
                    strategy_logger.info(f"{EMOJI['SESSION']} {session_info} - confidence adjusted to {confidence:.2%}")

                if bearish_cross:
                    confidence += 0.10
                if ha_color == -1:
                    confidence += 0.05
                if volume_ratio > 1.5:
                    confidence += 0.05

                # LTF confirmation adds confidence
                if ltf_confirmed:
                    ltf_confidence = ltf_data.get('confidence', 0)
                    confidence += ltf_confidence * 0.15

                confidence = min(0.95, confidence)

                if confidence >= min_confidence:
                    quality_score = int(confidence * 100)
                    if signal_strength == "HARD":
                        quality_score += 10

                    # Build reason
                    reason_parts = [f'SELL: TDI {tdi_slow:.2f} ({tdi_zone})']
                    if divergence_bearish:
                        reason_parts.append("Bearish divergence")
                    if candle_pattern_direction == 'SELL':
                        reason_parts.append(candle_pattern)
                    if sr_sell_confirmation:
                        reason_parts.append(f"Near resistance {nearest_resistance:.4f}")
                    if bb_squeeze and bb_squeeze_direction == 'BEARISH':
                        reason_parts.append("BB squeeze breakdown")
                    if session != "NY":
                        reason_parts.append(session_info)

                    rrr_suggested = self._suggest_rrr(quality_score, signal_strength, tdi_zone)

                    return {
                        'opportunity': True,
                        'direction': 'SELL',
                        'tdi_level': tdi_slow,
                        'tdi_zone': tdi_zone,
                        'tdi_crossover': is_bearish,
                        'bb_interaction': 'touch',
                        'ha_reversal': ha_reversal,
                        'candle_reversal': final_reversal_sell,
                        'confidence': confidence,
                        'signal_strength': signal_strength,
                        'risk_multiplier': risk_multiplier,
                        'quality_score': quality_score,
                        'rrr_suggested': rrr_suggested,
                        'reason': ' | '.join(reason_parts),
                        # New fields
                        'divergence_detected': divergence_bearish,
                        'divergence_strength': divergence_strength,
                        'candle_pattern': candle_pattern,
                        'candle_pattern_confidence': candle_pattern_confidence,
                        'sr_confirmed': sr_sell_confirmation,
                        'bb_squeeze': bb_squeeze,
                        'session': session,
                        'session_multiplier': session_multiplier,
                    }

        # ========== REJECTION LOGGING ==========
        failed_conditions = []

        # Check what's missing
        if tdi_zone in buy_zones:
            if not is_bullish:
                failed_conditions.append("TDI not bullish (fast <= slow)")
            if not bb_buy:
                failed_conditions.append("No BB lower touch")
            if not (enhanced_reversal_buy or reversal_buy):
                failed_conditions.append("No reversal pattern")
        elif tdi_zone in sell_zones:
            if not is_bearish:
                failed_conditions.append("TDI not bearish (fast >= slow)")
            if not bb_sell:
                failed_conditions.append("No BB upper touch")
            if not (enhanced_reversal_sell or reversal_sell):
                failed_conditions.append("No reversal pattern")
        else:
            failed_conditions.append(f"Zone {tdi_zone} not actionable")

        reason = f"Conditions not met: TDI {tdi_slow:.2f} ({tdi_zone})"
        if failed_conditions:
            reason += f" | Failed: {', '.join(failed_conditions)}"

        return self._no_opportunity(reason)

    def _no_opportunity(self, reason: str) -> Dict[str, Any]:
        """Return no opportunity response."""
        return {
            'opportunity': False,
            'direction': 'NONE',
            'tdi_level': 50,
            'tdi_zone': 'NEUTRAL',
            'confidence': 0,
            'reason': reason,
            'signal_strength': 'NONE',
            'risk_multiplier': 1.0,
            'tdi_crossover': False,
            'bb_interaction': 'none',
            'ha_reversal': False,
            'candle_reversal': False,
            'quality_score': 0,
            'rrr_suggested': 2.0,
        }

    def _suggest_rrr(self, quality_score: int, signal_strength: str, tdi_zone: str) -> float:
        """Suggest RRR based on quality score and signal strength."""
        base_rrr = 2.0

        # Quality score bonus (up to +1.5)
        quality_bonus = (quality_score - 50) / 50 * 1.5
        quality_bonus = max(0, min(1.5, quality_bonus))

        # Signal strength bonus
        strength_bonus = 0.5 if signal_strength == "HARD" else 0.0

        # TDI zone bonus
        if tdi_zone in [self.ZONE_OVERSOLD, self.ZONE_OVERBOUGHT]:
            zone_bonus = 0.5
        elif tdi_zone in [self.ZONE_SOFT_BUY, self.ZONE_SOFT_SELL]:
            zone_bonus = 0.25
        else:
            zone_bonus = 0.0

        rrr = base_rrr + quality_bonus + strength_bonus + zone_bonus
        rrr = round(rrr * 2) / 2  # Round to nearest 0.5
        return max(1.5, min(4.0, rrr))

    def debug_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Debug current indicator values."""
        if df is None or df.empty:
            return {}

        last = df.iloc[-1]
        tdi_slow = last.get('tdi_slow_ma', 50)

        return {
            "tdi": tdi_slow,
            "tdi_zone": self.get_zone(tdi_slow),
            "tdi_fast": last.get('tdi_fast_ma', 50),
            "ha_color": last.get('ha_color', 0),
            "ha_close": last.get('ha_close', 0),
            "ha_low": last.get('ha_low', 0),
            "ha_high": last.get('ha_high', 0),
            "bb_lower": last.get('bb_lower', 0),
            "bb_upper": last.get('bb_upper', 0),
            "bb_middle": last.get('bb_middle', 0),
            "bb_width": last.get('bb_width', 0),
            "volume_ratio": last.get('volume_ratio', 1),
            "candle_body": abs(last.get('close', 0) - last.get('open', 0)),
            # New fields
            "divergence_bullish": last.get('divergence_bullish', False),
            "divergence_bearish": last.get('divergence_bearish', False),
            "candle_pattern": last.get('candle_pattern', 'NONE'),
            "nearest_support": last.get('nearest_support', 0),
            "nearest_resistance": last.get('nearest_resistance', 0),
            "bb_squeeze": last.get('bb_squeeze', False),
            "session": get_trading_session(),
        }


# =============== SIGNAL SCORING SYSTEM ===============

class SignalScorer:
    """Signal quality scoring with grade thresholds."""

    LTF_WEIGHT = 0.30
    TDI_WEIGHT = 0.25
    BB_WEIGHT = 0.15
    VOLUME_WEIGHT = 0.15
    REVERSAL_WEIGHT = 0.15

    GRADE_A_THRESHOLD = 80
    GRADE_B_THRESHOLD = 70
    GRADE_C_THRESHOLD = 60

    MIN_SIGNAL_SCORE = 70

    def calculate_score(self, ltf_data: Optional[Dict], tdi_data: Dict,
                        bb_data: Dict, volume_ratio: float,
                        ha_reversal: bool, candle_reversal: bool,
                        divergence_detected: bool = False,
                        candle_pattern_conf: float = 0.0,
                        sr_confirmed: bool = False,
                        session_multiplier: float = 1.0) -> Tuple[bool, int, Dict[str, float]]:
        """
        ✅ UPDATED v3.3.0: Enhanced scoring with new indicators.
        """
        component_scores = {}

        # 1. LTF Score (0-100)
        if ltf_data and ltf_data.get('confirmed', False):
            ltf_confidence = ltf_data.get('confidence', 0)
            component_scores['ltf'] = ltf_confidence * 100
        else:
            component_scores['ltf'] = 0

        # 2. TDI Score (0-100)
        tdi_zone = tdi_data.get('tdi_zone', 'NEUTRAL')
        tdi_zones_high_score = ['OVERSOLD', 'OVERBOUGHT']
        tdi_zones_medium_score = ['SOFT_BUY', 'SOFT_SELL', 'BUY_ZONE']

        if tdi_zone in tdi_zones_high_score:
            component_scores['tdi'] = 85
        elif tdi_zone in tdi_zones_medium_score:
            component_scores['tdi'] = 65
        elif tdi_zone == 'NO_TRADE':
            component_scores['tdi'] = 30
        else:
            component_scores['tdi'] = 10

        if tdi_data.get('tdi_crossover', False):
            component_scores['tdi'] = min(100, component_scores['tdi'] + 15)

        # 3. BB Score (0-100)
        bb_position = bb_data.get('position', 0.5)
        if bb_position <= 0.15 or bb_position >= 0.85:
            component_scores['bb'] = 85
        elif bb_position <= 0.30 or bb_position >= 0.70:
            component_scores['bb'] = 65
        elif bb_position <= 0.45 or bb_position >= 0.55:
            component_scores['bb'] = 40
        else:
            component_scores['bb'] = 20

        # 4. Volume Score (0-100) - Time-aware
        current_hour = datetime.now().hour
        if 0 <= current_hour <= 6:  # Asian session
            if volume_ratio > 1.0: component_scores['volume'] = 90
            elif volume_ratio > 0.7: component_scores['volume'] = 75
            elif volume_ratio > 0.4: component_scores['volume'] = 60
            elif volume_ratio > 0.2: component_scores['volume'] = 45
            else: component_scores['volume'] = 25
        elif 7 <= current_hour <= 12:  # London session
            if volume_ratio > 1.5: component_scores['volume'] = 90
            elif volume_ratio > 1.0: component_scores['volume'] = 75
            elif volume_ratio > 0.6: component_scores['volume'] = 60
            elif volume_ratio > 0.3: component_scores['volume'] = 45
            else: component_scores['volume'] = 25
        elif 13 <= current_hour <= 17:  # NY session
            if volume_ratio > 2.0: component_scores['volume'] = 90
            elif volume_ratio > 1.3: component_scores['volume'] = 75
            elif volume_ratio > 0.8: component_scores['volume'] = 60
            elif volume_ratio > 0.4: component_scores['volume'] = 45
            else: component_scores['volume'] = 20
        else:  # Late session
            if volume_ratio > 0.8: component_scores['volume'] = 90
            elif volume_ratio > 0.5: component_scores['volume'] = 75
            elif volume_ratio > 0.3: component_scores['volume'] = 60
            elif volume_ratio > 0.15: component_scores['volume'] = 45
            else: component_scores['volume'] = 25

        # 5. Reversal Score (0-100) - Enhanced with new indicators
        reversal_score = 0
        if ha_reversal:
            reversal_score += 25
        if candle_reversal:
            reversal_score += 25
        if ha_reversal and candle_reversal:
            reversal_score += 15  # Bonus for both
        if divergence_detected:
            reversal_score += 20  # Divergence is strong reversal signal
            strategy_logger.info(f"{EMOJI['DIVERGENCE']} Divergence adds +20 to reversal score")
        if candle_pattern_conf > 0.5:
            reversal_score += candle_pattern_conf * 15
            strategy_logger.info(f"{EMOJI['PATTERN']} Pattern confidence adds +{candle_pattern_conf*15:.0f} to reversal score")
        if sr_confirmed:
            reversal_score += 10
            strategy_logger.info(f"{EMOJI['S_R']} S/R confirmation adds +10 to reversal score")
        if volume_ratio > 1.5:
            reversal_score += 5
        component_scores['reversal'] = min(100, reversal_score)

        # Calculate weighted total
        total_score = (
            component_scores['ltf'] * self.LTF_WEIGHT +
            component_scores['tdi'] * self.TDI_WEIGHT +
            component_scores['bb'] * self.BB_WEIGHT +
            component_scores['volume'] * self.VOLUME_WEIGHT +
            component_scores['reversal'] * self.REVERSAL_WEIGHT
        )

        # Session multiplier
        total_score *= session_multiplier

        # Time bonuses
        if 0 <= current_hour <= 6:
            total_score += 5  # Asian session bonus
        elif 18 <= current_hour <= 23:
            total_score += 3  # Late session bonus

        total_score = round(total_score)
        is_valid = total_score >= self.MIN_SIGNAL_SCORE

        return is_valid, total_score, component_scores

    def get_grade(self, score: int) -> str:
        """Get grade aligned with main.py."""
        if score >= self.GRADE_A_THRESHOLD:
            return "A"
        elif score >= self.GRADE_B_THRESHOLD:
            return "B"
        elif score >= self.GRADE_C_THRESHOLD:
            return "C"
        else:
            return "D"


# =============== VOLUME NORMALIZER ===============

class VolumeNormalizer:
    """Dynamic volume threshold based on market conditions."""

    @staticmethod
    def get_threshold(df: pd.DataFrame) -> float:
        """Calculate dynamic volume threshold based on market conditions."""
        if df.empty or len(df) < 20:
            return 0.5

        base_threshold = 0.5

        # Check volatility (using BB width as proxy)
        last = df.iloc[-1]
        bb_width = last.get('bb_width', 0)
        bb_middle = last.get('bb_middle', 1)

        if bb_middle > 0:
            bb_width_percent = bb_width / bb_middle
            if bb_width_percent < 0.02:
                base_threshold = 0.3
            elif bb_width_percent > 0.05:
                base_threshold = 0.6

        # Check time of day
        current_hour = datetime.now().hour
        if current_hour in [0, 1, 2, 3, 4, 5, 6]:
            base_threshold = max(0.2, base_threshold - 0.15)
        elif current_hour in [14, 15, 16]:
            base_threshold = min(0.8, base_threshold + 0.1)

        return base_threshold


# =============== REJECTION TRACKER ===============

class RejectionTracker:
    """Track rejection reasons for performance tuning."""
    def __init__(self):
        self.stats = {
            'ltf_not_confirmed': 0,
            'tdi_no_trade_zone': 0,
            'tdi_conditions_failed': 0,
            'volume_too_low': 0,
            'bb_position_bad': 0,
            'htf_conflict': 0,
            'score_too_low': 0,
            'signal_generated': 0,
            'data_stale': 0,
            'grade_c_rejected': 0,
            # New
            'session_rejected': 0,
            'divergence_missing': 0,
            'pattern_missing': 0,
            'sr_missing': 0,
        }

    def record(self, reason: str):
        """Record a rejection reason."""
        reason_upper = reason.upper()
        if 'LTF' in reason_upper:
            self.stats['ltf_not_confirmed'] += 1
        elif 'NO TRADE ZONE' in reason_upper:
            self.stats['tdi_no_trade_zone'] += 1
        elif 'CONDITIONS NOT MET' in reason_upper:
            self.stats['tdi_conditions_failed'] += 1
        elif 'VOLUME' in reason_upper:
            self.stats['volume_too_low'] += 1
        elif 'BB' in reason_upper:
            self.stats['bb_position_bad'] += 1
        elif 'HTF' in reason_upper:
            self.stats['htf_conflict'] += 1
        elif 'SCORE' in reason_upper:
            self.stats['score_too_low'] += 1
        elif 'STALE' in reason_upper or 'EXPIRED' in reason_upper:
            self.stats['data_stale'] += 1
        elif 'GRADE' in reason_upper and 'C' in reason_upper:
            self.stats['grade_c_rejected'] += 1
        elif 'SESSION' in reason_upper:
            self.stats['session_rejected'] += 1
        elif 'DIVERGENCE' in reason_upper:
            self.stats['divergence_missing'] += 1
        elif 'PATTERN' in reason_upper:
            self.stats['pattern_missing'] += 1
        elif 'SR' in reason_upper or 'SUPPORT' in reason_upper or 'RESISTANCE' in reason_upper:
            self.stats['sr_missing'] += 1

    def record_signal(self):
        """Record a generated signal."""
        self.stats['signal_generated'] += 1

    def get_report(self) -> Dict[str, Any]:
        """Get rejection statistics report."""
        total_rejections = sum(v for k, v in self.stats.items() if k != 'signal_generated')
        total_attempts = total_rejections + self.stats['signal_generated']

        return {
            'stats': self.stats.copy(),
            'total_attempts': total_attempts,
            'total_rejections': total_rejections,
            'acceptance_rate': round(self.stats['signal_generated'] / total_attempts * 100, 1) if total_attempts > 0 else 0,
            'top_rejection_reasons': sorted(
                [(k, v) for k, v in self.stats.items() if k != 'signal_generated' and v > 0],
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }


# =============== CONFIDENCE DECAY ===============

class ConfidenceDecay:
    """Apply confidence decay for stale signals."""

    @staticmethod
    def apply(confidence: float, age_ms: float) -> float:
        """Apply time-based confidence decay."""
        if age_ms < 500:
            return confidence
        elif age_ms < 1000:
            return confidence * 0.95
        elif age_ms < 2000:
            return confidence * 0.90
        elif age_ms < 5000:
            return confidence * 0.80
        else:
            return confidence * 0.65


# =============== MAIN STRATEGY CLASS ===============

class ConsolidatedTrendStrategy:
    """
    HYBRID STRATEGY: Super TDI + Super Bollinger Bands + Multi-Timeframe
    Version 3.3.0 - Enhanced with Divergence, Patterns, S/R, Session
    """

    def __init__(self, config_override: Optional[Dict] = None):
        log_strategy_operation("INIT", "START", emoji=EMOJI['START'])

        # Components
        self.tdi_detector = SuperTDIDetector()
        self.signal_scorer = SignalScorer()
        self.volume_normalizer = VolumeNormalizer()
        self.rejection_tracker = RejectionTracker()
        self.data_lock = DataLock(max_age_ms=500)

        # State
        self.htf_trend = "NEUTRAL"
        self.last_signal = "NO_TRADE"
        self.last_signal_time = None
        self.consecutive_signals = 0
        self.signal_cooldown_active = False

        # Fee configuration
        self.fee_config = FeeConfig()
        self.total_fee_impact = self.fee_config.get_total_fee_impact()
        self.min_sl_percent = self.fee_config.get_min_sl_percent()

        # Risk parameters
        self.min_sl_percent = 0.005
        self.max_sl_percent = 0.015
        self.min_rrr = 1.5
        self.max_rrr = 4.0
        self.default_rrr = 2.0

        # Multi-timeframe thresholds
        self.ltf_confidence_threshold = 0.50
        self.htf_alignment_threshold = 0.70

        self.min_signal_score = 70

        # Grade thresholds
        self.GRADE_A_THRESHOLD = 80
        self.GRADE_B_THRESHOLD = 70
        self.GRADE_C_THRESHOLD = 60

        # Stats
        self.signal_stats = {
            "total_signals": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "sniper_signals": 0,
            "tdi_extreme_events": 0,
            "bb_touch_events": 0,
            "structure_events": 0,
            "mss_events": 0,
            "liquidity_sweep_events": 0,
            "fvg_events": 0,
            "ltf_confirmations": 0,
            "hard_signals": 0,
            "soft_signals": 0,
            "rrr_values": [],
            "htf_aligned": 0,
            "htf_conflicts": 0,
            "signals_approved": 0,
            "signals_rejected": 0,
            "score_approved": 0,
            "score_rejected": 0,
            "grade_a_signals": 0,
            "grade_b_signals": 0,
            "grade_c_rejected": 0,
            # New stats
            "divergence_signals": 0,
            "pattern_signals": 0,
            "sr_signals": 0,
            "squeeze_signals": 0,
            "session_adjusted": 0,
        }

        self.MIN_KLINES_REQUIRED = 50

        log_strategy_operation("INIT", "SUCCESS",
                              {
                                  "version": "3.3.0",
                                  "oversold": self.tdi_detector.OVERSOLD,
                                  "soft_buy": self.tdi_detector.SOFT_BUY,
                                  "center": self.tdi_detector.CENTER_LINE,
                                  "no_trade": f"{self.tdi_detector.NO_TRADE_START}-{self.tdi_detector.NO_TRADE_END}",
                                  "soft_sell": self.tdi_detector.SOFT_SELL,
                                  "overbought": self.tdi_detector.OVERBOUGHT,
                                  "min_signal_score": self.min_signal_score,
                                  "grade_a_threshold": self.GRADE_A_THRESHOLD,
                                  "grade_b_threshold": self.GRADE_B_THRESHOLD,
                                  "grade_c_threshold": self.GRADE_C_THRESHOLD,
                                  "new_features": [
                                      "Divergence Detection",
                                      "Candle Pattern Recognition",
                                      "Support/Resistance Levels",
                                      "BB Squeeze Detection",
                                      "VWAP Integration",
                                      "Session-Based Filtering",
                                      "Enhanced Reversal Scoring"
                                  ]
                              },
                              emoji=EMOJI['SUCCESS'])

    def _get_grade(self, score: int) -> str:
        """Get grade aligned with main.py."""
        if score >= self.GRADE_A_THRESHOLD:
            return "A"
        elif score >= self.GRADE_B_THRESHOLD:
            return "B"
        elif score >= self.GRADE_C_THRESHOLD:
            return "C"
        else:
            return "D"

    def set_htf_trend(self, htf_df: pd.DataFrame):
        """Set higher timeframe trend (1h)."""
        if htf_df.empty:
            self.htf_trend = "NEUTRAL"
            return

        try:
            htf_df = Indicators.calculate_all_indicators(htf_df)
            htf_df = calculate_heikin_ashi(htf_df)

            last = htf_df.iloc[-1]
            bb_middle = last.get('bb_middle', 0)
            ha_close = last.get('ha_close', last.get('close', 0))

            if ha_close > bb_middle * 1.01 and bb_middle > 0:
                self.htf_trend = "BULLISH"
            elif ha_close < bb_middle * 0.99 and bb_middle > 0:
                self.htf_trend = "BEARISH"
            else:
                self.htf_trend = "NEUTRAL"

        except Exception as e:
            strategy_logger.error(f"{EMOJI['ERROR']} STRATEGY_HTF: {e}")
            self.htf_trend = "NEUTRAL"

    def get_strategy_stats(self) -> Dict[str, Any]:
        avg_rrr = sum(self.signal_stats["rrr_values"]) / len(self.signal_stats["rrr_values"]) if self.signal_stats["rrr_values"] else 0

        return {
            "htf_trend": self.htf_trend,
            "last_signal": self.last_signal,
            "total_signals": self.signal_stats["total_signals"],
            "buy_signals": self.signal_stats["buy_signals"],
            "sell_signals": self.signal_stats["sell_signals"],
            "sniper_signals": self.signal_stats["sniper_signals"],
            "ltf_confirmations": self.signal_stats["ltf_confirmations"],
            "hard_signals": self.signal_stats["hard_signals"],
            "soft_signals": self.signal_stats["soft_signals"],
            "avg_rrr": round(avg_rrr, 2),
            "htf_aligned": self.signal_stats.get("htf_aligned", 0),
            "htf_conflicts": self.signal_stats.get("htf_conflicts", 0),
            "score_approved": self.signal_stats.get("score_approved", 0),
            "score_rejected": self.signal_stats.get("score_rejected", 0),
            "grade_a_signals": self.signal_stats.get("grade_a_signals", 0),
            "grade_b_signals": self.signal_stats.get("grade_b_signals", 0),
            "grade_c_rejected": self.signal_stats.get("grade_c_rejected", 0),
            # New stats
            "divergence_signals": self.signal_stats.get("divergence_signals", 0),
            "pattern_signals": self.signal_stats.get("pattern_signals", 0),
            "sr_signals": self.signal_stats.get("sr_signals", 0),
            "squeeze_signals": self.signal_stats.get("squeeze_signals", 0),
            "session_adjusted": self.signal_stats.get("session_adjusted", 0),
            "rejection_report": self.rejection_tracker.get_report(),
        }

    def analyze_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Analyze data with all indicators including new features."""
        if df.empty:
            return df

        try:
            df = df.copy()

            # Calculate Heikin Ashi
            df = calculate_heikin_ashi(df)

            # Calculate TDI indicators
            df = Indicators.calculate_tdi(df)

            # Calculate Bollinger Bands
            df = Indicators.calculate_bollinger_bands(df, period=34, dev=1.750)

            # Calculate additional indicators
            if 'volume' in df.columns:
                df['volume_sma'] = df['volume'].rolling(20).mean()
                df['volume_ratio'] = df['volume'] / df['volume_sma']

            df.dropna(inplace=True)
            return df

        except Exception as e:
            strategy_logger.error(f"{EMOJI['ERROR']} STRATEGY_ANALYZE: {e}")
            return df

    def lock_current_data(self, df: pd.DataFrame):
        """Lock current indicator snapshot for consistent signal generation."""
        if df.empty:
            return

        last = df.iloc[-1]
        indicators = {
            'tdi_slow': last.get('tdi_slow_ma', 50),
            'tdi_fast': last.get('tdi_fast_ma', 50),
            'tdi_zone': self.tdi_detector.get_zone(last.get('tdi_slow_ma', 50)),
            'ha_color': last.get('ha_color', 0),
            'ha_low': last.get('ha_low', 0),
            'ha_high': last.get('ha_high', 0),
            'bb_lower': last.get('bb_lower', 0),
            'bb_upper': last.get('bb_upper', 0),
            'bb_middle': last.get('bb_middle', 0),
            'bb_width': last.get('bb_width', 0),
            'bb_position': last.get('bb_position', 0.5),
            'close': last.get('close', 0),
            'volume_ratio': last.get('volume_ratio', 1),
            'ha_reversal': False,
            'candle_reversal': False,
            # New fields
            'divergence_bullish': last.get('divergence_bullish', False),
            'divergence_bearish': last.get('divergence_bearish', False),
            'candle_pattern': last.get('candle_pattern', 'NONE'),
            'nearest_support': last.get('nearest_support', 0),
            'nearest_resistance': last.get('nearest_resistance', 0),
            'bb_squeeze': last.get('bb_squeeze', False),
            'session': get_trading_session(),
            'timestamp': time.time(),
        }

        self.data_lock.lock(df, indicators)

    def _calculate_sl_tp_from_structure(self, entry: float, direction: str,
                                        df: pd.DataFrame, signal_strength: str,
                                        rrr_suggested: float) -> Tuple[float, float, float, float, float]:
        """Calculate SL/TP based on recent swing high/low with S/R awareness."""
        total_fees = self.total_fee_impact

        # Try to use nearest S/R levels first
        last = df.iloc[-1]
        nearest_support = last.get('nearest_support', 0)
        nearest_resistance = last.get('nearest_resistance', 0)

        lookback = 10
        if len(df) > lookback:
            recent_high = df['high'].iloc[-lookback:].max()
            recent_low = df['low'].iloc[-lookback:].min()
        else:
            recent_high = entry * 1.02
            recent_low = entry * 0.98

        if direction == "BUY":
            # Use nearest support if available and below entry
            if nearest_support > 0 and nearest_support < entry:
                sl_price = nearest_support * 0.998
            else:
                sl_price = recent_low * 0.998

            sl_percent = (entry - sl_price) / entry

            if sl_percent < self.min_sl_percent:
                sl_percent = self.min_sl_percent
                sl_price = entry * (1 - sl_percent)

            rrr = min(self.max_rrr, max(self.min_rrr, rrr_suggested))
            tp_percent = sl_percent * rrr

            min_tp_percent = sl_percent + total_fees + 0.001
            if tp_percent < min_tp_percent:
                tp_percent = min_tp_percent
                rrr = tp_percent / sl_percent if sl_percent > 0 else self.min_rrr

            tp_price = entry * (1 + tp_percent)

            # Use nearest resistance if available and above TP
            if nearest_resistance > 0 and nearest_resistance < tp_price:
                tp_price = nearest_resistance * 0.998
                tp_percent = (tp_price - entry) / entry
                rrr = tp_percent / sl_percent if sl_percent > 0 else self.min_rrr

        else:  # SELL
            # Use nearest resistance if available and above entry
            if nearest_resistance > 0 and nearest_resistance > entry:
                sl_price = nearest_resistance * 1.002
            else:
                sl_price = recent_high * 1.002

            sl_percent = (sl_price - entry) / entry

            if sl_percent < self.min_sl_percent:
                sl_percent = self.min_sl_percent
                sl_price = entry * (1 + sl_percent)

            rrr = min(self.max_rrr, max(self.min_rrr, rrr_suggested))
            tp_percent = sl_percent * rrr

            min_tp_percent = sl_percent + total_fees + 0.001
            if tp_percent < min_tp_percent:
                tp_percent = min_tp_percent
                rrr = tp_percent / sl_percent if sl_percent > 0 else self.min_rrr

            tp_price = entry * (1 - tp_percent)

            # Use nearest support if available and below TP
            if nearest_support > 0 and nearest_support > tp_price:
                tp_price = nearest_support * 1.002
                tp_percent = (entry - tp_price) / entry
                rrr = tp_percent / sl_percent if sl_percent > 0 else self.min_rrr

        rrr = max(self.min_rrr, min(self.max_rrr, rrr))

        strategy_logger.debug(
            f"{EMOJI['FEE']} SL/TP: Entry={entry:.4f}, SL={sl_price:.4f} ({sl_percent*100:.2f}%), "
            f"TP={tp_price:.4f} ({tp_percent*100:.2f}%), RRR={rrr:.1f}, Fees={total_fees*100:.2f}%"
        )

        return sl_price, tp_price, sl_percent, tp_percent, rrr

    def generate_signal(self, df: pd.DataFrame, ltf_confirmation: Optional[Dict] = None) -> Tuple[str, Dict[str, Any]]:
        """
        ✅ UPDATED v3.3.0: Enhanced signal generation with new features.
        """
        start_time = time.time()

        strategy_logger.info(f"{EMOJI['START']} generate_signal: Starting signal generation (v3.3.0)...")
        strategy_logger.info(f"{EMOJI['DEBUG']} DataFrame shape: {df.shape}, columns: {list(df.columns)}")

        if df.empty or len(df) < self.MIN_KLINES_REQUIRED:
            strategy_logger.warning(f"{EMOJI['WARNING']} Insufficient data: {len(df)} rows")
            self.rejection_tracker.record("Insufficient data")
            self._update_state("NO_TRADE")
            return "NO_TRADE", {"reason": f"Insufficient data"}

        try:
            # Check data lock validity
            locked_data = self.data_lock.get_locked_data()
            if locked_data and not self.data_lock.is_same_candle(df):
                strategy_logger.warning(f"{EMOJI['DECAY']} Candle changed! Data may be stale. Re-locking...")
                self.lock_current_data(df)
                locked_data = self.data_lock.get_locked_data()

            # ========== LOG CURRENT INDICATOR VALUES ==========
            last = df.iloc[-1]
            tdi_slow = last.get('tdi_slow_ma', 50)
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_zone = self.tdi_detector.get_zone(tdi_slow)
            ha_color = last.get('ha_color', 0)
            ha_low = last.get('ha_low', 0)
            ha_high = last.get('ha_high', 0)
            bb_lower = last.get('bb_lower', 0)
            bb_upper = last.get('bb_upper', 0)
            bb_middle = last.get('bb_middle', 0)
            close = last.get('close', 0)
            volume_ratio = last.get('volume_ratio', 1)
            candle_body = abs(last.get('close', 0) - last.get('open', 0))

            # New indicator values
            divergence_bullish = last.get('divergence_bullish', False)
            divergence_bearish = last.get('divergence_bearish', False)
            candle_pattern = last.get('candle_pattern', 'NONE')
            nearest_support = last.get('nearest_support', 0)
            nearest_resistance = last.get('nearest_resistance', 0)
            bb_squeeze = last.get('bb_squeeze', False)
            session = get_trading_session()

            strategy_logger.info(
                f"{EMOJI['DEBUG']} Current Indicators Summary:\n"
                f"  📈 TDI: Slow={tdi_slow:.2f}, Fast={tdi_fast:.2f}, Zone={tdi_zone}\n"
                f"  📊 BB: Lower={bb_lower:.6f}, Middle={bb_middle:.6f}, Upper={bb_upper:.6f}\n"
                f"  🕯️ HA: Color={ha_color}, Low={ha_low:.6f}, High={ha_high:.6f}\n"
                f"  💰 Price: Close={close:.6f}, Volume={volume_ratio:.2f}x, Body={candle_body:.6f}\n"
                f"  📊 HTF Trend: {self.htf_trend}\n"
                f"  🔄 Divergence: {'🟢 Bullish' if divergence_bullish else '🔴 Bearish' if divergence_bearish else '❌ None'}\n"
                f"  🕯️ Pattern: {candle_pattern}\n"
                f"  📊 S/R: Support={nearest_support:.6f}, Resistance={nearest_resistance:.6f}\n"
                f"  📉 BB Squeeze: {'✅' if bb_squeeze else '❌'}\n"
                f"  🌍 Session: {session}"
            )

            # ========== STEP 1: LTF ENTRY DETECTION ==========
            strategy_logger.info(f"{EMOJI['LTF']} STEP 1: Checking LTF confirmation...")

            ltf_confirmed = ltf_confirmation.get('confirmed', False) if ltf_confirmation else False
            ltf_confidence = ltf_confirmation.get('confidence', 0) if ltf_confirmation else 0
            ltf_reason = ltf_confirmation.get('reason', '') if ltf_confirmation else ''
            ltf_direction = ltf_confirmation.get('direction', '') if ltf_confirmation else ''
            ltf_tdi_value = ltf_confirmation.get('tdi_value', tdi_slow) if ltf_confirmation else tdi_slow

            if self.data_lock.lock_time:
                age_ms = (time.time() - self.data_lock.lock_time) * 1000
                ltf_confidence = ConfidenceDecay.apply(ltf_confidence, age_ms)
                if age_ms > 500:
                    strategy_logger.info(f"{EMOJI['DECAY']} Confidence decay applied: {ltf_confidence:.2%} (age: {age_ms:.0f}ms)")

            strategy_logger.info(
                f"{EMOJI['LTF']} LTF Status: Confirmed={ltf_confirmed}, Confidence={ltf_confidence:.2%}, "
                f"TDI={ltf_tdi_value:.1f}, Direction={ltf_direction}, Reason='{ltf_reason}'"
            )

            if config.strategy.require_ltf_confirmation and not ltf_confirmed:
                if ltf_confidence >= 0.70:
                    strategy_logger.info(f"{EMOJI['LTF']} LTF high confidence override: {ltf_confidence:.2%} >= 70%")
                    ltf_confirmed = True
                else:
                    reason = f"LTF rejected: {ltf_reason} (Confidence: {ltf_confidence:.2%})"
                    strategy_logger.warning(f"{EMOJI['REJECT']} {reason}")
                    self.rejection_tracker.record(reason)
                    self.signal_stats["signals_rejected"] += 1
                    self._update_state("NO_TRADE")
                    return "NO_TRADE", {
                        "reason": reason,
                        "ltf_confidence": ltf_confidence
                    }

            if ltf_confirmed:
                self.signal_stats["ltf_confirmations"] += 1
                strategy_logger.info(f"{EMOJI['SUCCESS']} LTF CONFIRMED ✅")

            # ========== STEP 2: MTF SIGNAL CONFIRMATION ==========
            strategy_logger.info(f"{EMOJI['TDI']} STEP 2: Checking TDI opportunity...")

            ltf_data_for_tdi = {
                'confirmed': ltf_confirmed,
                'confidence': ltf_confidence,
                'direction': ltf_direction
            }
            tdi_opportunity = self.tdi_detector.detect_opportunity(df, ltf_data_for_tdi)

            strategy_logger.info(
                f"{EMOJI['TDI']} TDI Opportunity: {tdi_opportunity.get('opportunity')}, "
                f"Direction: {tdi_opportunity.get('direction')}, "
                f"Reason: {tdi_opportunity.get('reason', 'N/A')}"
            )

            if not tdi_opportunity.get('opportunity', False):
                reason = tdi_opportunity.get('reason', 'No opportunity')
                self.rejection_tracker.record(reason)
                self.signal_stats["signals_rejected"] += 1
                self._update_state("NO_TRADE")
                return "NO_TRADE", {
                    "reason": reason,
                    "ltf_confidence": ltf_confidence
                }

            direction = tdi_opportunity.get('direction')
            signal_strength = tdi_opportunity.get('signal_strength', 'SOFT')
            risk_multiplier = tdi_opportunity.get('risk_multiplier', 1.0)
            confidence = tdi_opportunity.get('confidence', 0.5)
            quality_score = tdi_opportunity.get('quality_score', 50)
            rrr_suggested = tdi_opportunity.get('rrr_suggested', self.default_rrr)

            # Track new features
            if tdi_opportunity.get('divergence_detected', False):
                self.signal_stats["divergence_signals"] += 1
                strategy_logger.info(f"{EMOJI['DIVERGENCE']} Divergence detected in signal!")

            if tdi_opportunity.get('candle_pattern', 'NONE') != 'NONE':
                self.signal_stats["pattern_signals"] += 1
                strategy_logger.info(f"{EMOJI['PATTERN']} Pattern {tdi_opportunity.get('candle_pattern')} detected!")

            if tdi_opportunity.get('sr_confirmed', False):
                self.signal_stats["sr_signals"] += 1
                strategy_logger.info(f"{EMOJI['S_R']} S/R confirmed!")

            if tdi_opportunity.get('bb_squeeze', False):
                self.signal_stats["squeeze_signals"] += 1
                strategy_logger.info(f"{EMOJI['BB']} BB Squeeze detected!")

            if tdi_opportunity.get('session') != 'NY':
                self.signal_stats["session_adjusted"] += 1
                strategy_logger.info(f"{EMOJI['SESSION']} Session adjusted: {tdi_opportunity.get('session')}")

            # ========== STEP 2.5: SIGNAL QUALITY SCORING ==========
            strategy_logger.info(f"{EMOJI['SCORE']} STEP 2.5: Calculating signal quality score...")

            bb_data = {
                'position': last.get('bb_position', 0.5),
                'lower': bb_lower,
                'upper': bb_upper,
                'middle': bb_middle
            }

            is_valid_score, total_score, component_scores = self.signal_scorer.calculate_score(
                ltf_data=ltf_confirmation,
                tdi_data=tdi_opportunity,
                bb_data=bb_data,
                volume_ratio=volume_ratio,
                ha_reversal=tdi_opportunity.get('ha_reversal', False),
                candle_reversal=tdi_opportunity.get('candle_reversal', False),
                divergence_detected=tdi_opportunity.get('divergence_detected', False),
                candle_pattern_conf=tdi_opportunity.get('candle_pattern_confidence', 0.0),
                sr_confirmed=tdi_opportunity.get('sr_confirmed', False),
                session_multiplier=tdi_opportunity.get('session_multiplier', 1.0),
            )

            grade = self._get_grade(total_score)

            strategy_logger.info(
                f"{EMOJI['SCORE']} Signal Score: {total_score}/100 (Grade {grade}) "
                f"(LTF={component_scores['ltf']:.0f}, TDI={component_scores['tdi']:.0f}, "
                f"BB={component_scores['bb']:.0f}, Vol={component_scores['volume']:.0f}, "
                f"Reversal={component_scores['reversal']:.0f}) | "
                f"Threshold: {self.min_signal_score} | {'✅' if is_valid_score else '❌'}"
            )

            if grade == "C" or grade == "D":
                reason = f"Grade {grade} signal rejected: {total_score}/100 (need Grade A or B)"
                strategy_logger.warning(f"{EMOJI['REJECT']} {reason}")
                self.rejection_tracker.record(reason)
                self.signal_stats["score_rejected"] += 1
                self.signal_stats["signals_rejected"] += 1
                self.signal_stats["grade_c_rejected"] += 1
                self._update_state("NO_TRADE")
                return "NO_TRADE", {
                    "reason": reason,
                    "score": total_score,
                    "grade": grade,
                    "component_scores": component_scores,
                    "ltf_confidence": ltf_confidence
                }

            if not is_valid_score:
                reason = f"Signal score too low: {total_score}/100 < {self.min_signal_score}"
                strategy_logger.warning(f"{EMOJI['REJECT']} {reason}")
                self.rejection_tracker.record(reason)
                self.signal_stats["score_rejected"] += 1
                self.signal_stats["signals_rejected"] += 1
                self._update_state("NO_TRADE")
                return "NO_TRADE", {
                    "reason": reason,
                    "score": total_score,
                    "grade": grade,
                    "component_scores": component_scores,
                    "ltf_confidence": ltf_confidence
                }

            self.signal_stats["score_approved"] += 1
            if grade == "A":
                self.signal_stats["grade_a_signals"] += 1
            elif grade == "B":
                self.signal_stats["grade_b_signals"] += 1

            # ========== STEP 3: HTF TREND VALIDATION ==========
            strategy_logger.info(f"{EMOJI['HTF']} STEP 3: Validating HTF trend...")

            htf_aligned = False
            htf_conflict = False
            htf_conflict_reason = ""

            if direction == "BUY" and self.htf_trend == "BULLISH":
                htf_aligned = True
            elif direction == "SELL" and self.htf_trend == "BEARISH":
                htf_aligned = True
            elif direction == "BUY" and self.htf_trend == "BEARISH":
                htf_conflict = True
                htf_conflict_reason = "BUY with BEARISH HTF"
            elif direction == "SELL" and self.htf_trend == "BULLISH":
                htf_conflict = True
                htf_conflict_reason = "SELL with BULLISH HTF"
            elif self.htf_trend == "NEUTRAL":
                htf_aligned = True

            if htf_conflict:
                self.signal_stats["htf_conflicts"] += 1

                if grade in ["A", "B"] or quality_score >= 70 or ltf_confirmed or total_score >= 80:
                    strategy_logger.info(f"{EMOJI['OVERRIDE']} HTF conflict overridden (Grade {grade}, Score: {total_score})")
                    htf_aligned = True
                    htf_conflict = False
                else:
                    reason = f"HTF conflict: {htf_conflict_reason} (Grade {grade})"
                    strategy_logger.warning(f"{EMOJI['REJECT']} {reason}")
                    self.rejection_tracker.record(reason)
                    self.signal_stats["signals_rejected"] += 1
                    self._update_state("NO_TRADE")
                    return "NO_TRADE", {
                        "reason": reason,
                        "ltf_confidence": ltf_confidence,
                        "htf_trend": self.htf_trend,
                        "score": total_score,
                        "grade": grade
                    }

            if htf_aligned:
                self.signal_stats["htf_aligned"] += 1
                strategy_logger.info(f"{EMOJI['HTF']} HTF ALIGNED ✅")

            # ========== STEP 4: CALCULATE SL/TP ==========
            strategy_logger.info(f"{EMOJI['FEE']} STEP 4: Calculating SL/TP...")

            entry = close

            sl_price, tp_price, sl_percent, tp_percent, rrr = self._calculate_sl_tp_from_structure(
                entry, direction, df, signal_strength, rrr_suggested
            )

            # ========== STEP 5: BUILD SIGNAL DATA ==========
            strategy_logger.info(f"{EMOJI['SIGNAL']} STEP 5: Building signal data...")

            if signal_strength == "HARD":
                self.signal_stats["hard_signals"] += 1
            else:
                self.signal_stats["soft_signals"] += 1

            self.signal_stats["rrr_values"].append(rrr)
            self.signal_stats["total_signals"] += 1
            self.signal_stats[f"{direction.lower()}_signals"] += 1
            self.signal_stats["sniper_signals"] += 1
            self.signal_stats["signals_approved"] += 1
            self.rejection_tracker.record_signal()

            signal_data = {
                "signal_type": direction,
                "side": direction,
                "type": direction,
                "entry_price": entry,
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "sl_percent": sl_percent,
                "tp_percent": tp_percent,
                "rrr": rrr,
                "confidence": confidence,
                "signal_strength": signal_strength,
                "risk_multiplier": risk_multiplier,
                "quality_score": quality_score,
                "total_score": total_score,
                "grade": grade,
                "component_scores": component_scores,
                "tdi_level": tdi_opportunity.get('tdi_level', 50),
                "tdi_zone": tdi_opportunity.get('tdi_zone', 'NEUTRAL'),
                "tdi_crossover": tdi_opportunity.get('tdi_crossover', False),
                "bb_interaction": tdi_opportunity.get('bb_interaction', 'none'),
                "ha_reversal": tdi_opportunity.get('ha_reversal', False),
                "ltf_confirmed": ltf_confirmed,
                "ltf_confidence": ltf_confidence,
                "ltf_reason": ltf_reason,
                "htf_trend": self.htf_trend,
                "htf_aligned": htf_aligned,
                "htf_conflict": htf_conflict,
                "htf_conflict_reason": htf_conflict_reason,
                "rrr_suggested": rrr_suggested,
                "current_rrr": rrr,
                "fee_impact": f"{self.total_fee_impact*100:.2f}%",
                "has_conflict": htf_conflict,
                "conflict_reason": htf_conflict_reason if htf_conflict else "",
                # New fields
                "divergence_detected": tdi_opportunity.get('divergence_detected', False),
                "divergence_strength": tdi_opportunity.get('divergence_strength', 0.0),
                "candle_pattern": tdi_opportunity.get('candle_pattern', 'NONE'),
                "candle_pattern_confidence": tdi_opportunity.get('candle_pattern_confidence', 0.0),
                "sr_confirmed": tdi_opportunity.get('sr_confirmed', False),
                "bb_squeeze": tdi_opportunity.get('bb_squeeze', False),
                "session": tdi_opportunity.get('session', 'UNKNOWN'),
                "session_multiplier": tdi_opportunity.get('session_multiplier', 1.0),
                "timestamp": datetime.now().isoformat(),
                "strategy_version": "v3.3.0-enhanced-super-tdi-15m",
                "timeframe": "15m",
            }

            # Update state
            self._update_state(direction)

            elapsed = (time.time() - start_time) * 1000

            # ========== FINAL SIGNAL LOG ==========
            grade_emoji = "🏆" if grade == "A" else "🥈" if grade == "B" else "📊"

            # Build enhanced signal log
            feature_parts = []
            if signal_data.get('divergence_detected'):
                feature_parts.append("🔄 DIV")
            if signal_data.get('candle_pattern') != 'NONE':
                feature_parts.append(f"🕯️ {signal_data.get('candle_pattern')[:10]}")
            if signal_data.get('sr_confirmed'):
                feature_parts.append("📊 S/R")
            if signal_data.get('bb_squeeze'):
                feature_parts.append("📉 SQZ")
            feature_str = f" [{', '.join(feature_parts)}]" if feature_parts else ""

            strategy_logger.info(
                f"{EMOJI['SNIPER']} {grade_emoji} {'🟢' if direction == 'BUY' else '🔴'} "
                f"🎯 SIGNAL GENERATED: {direction} | Grade: {grade} | Score: {total_score}/100{feature_str} | "
                f"TDI: {tdi_opportunity.get('tdi_level', 50):.1f} ({tdi_opportunity.get('tdi_zone', 'NEUTRAL')}) | "
                f"Entry: {entry:.4f} | SL: {sl_price:.4f} ({sl_percent*100:.2f}%) | "
                f"TP: {tp_price:.4f} ({tp_percent*100:.2f}%) | "
                f"RRR: {rrr:.1f} | Confidence: {confidence:.2f} | "
                f"LTF: {'✅' if ltf_confirmed else '❌'} | HTF: {self.htf_trend} {'✅' if htf_aligned else '❌'} | "
                f"Strength: {signal_strength} | Session: {signal_data.get('session', 'UNKNOWN')} | "
                f"Elapsed: {elapsed:.0f}ms"
            )

            return direction, signal_data

        except Exception as e:
            strategy_logger.error(f"{EMOJI['ERROR']} STRATEGY_SIGNAL: {e}", exc_info=True)
            self.rejection_tracker.record(f"Error: {str(e)}")
            self._update_state("NO_TRADE")
            return "NO_TRADE", {"reason": f"Error: {str(e)}"}

    def _update_state(self, signal: str):
        if signal == self.last_signal and signal != "NO_TRADE":
            self.consecutive_signals += 1
        else:
            self.consecutive_signals = 1
            self.last_signal = signal

        if signal != "NO_TRADE":
            self.last_signal_time = datetime.now()
            self.signal_cooldown_active = True

            def cooldown_timer():
                time.sleep(config.strategy.signal_cooldown_minutes * 60)
                self.signal_cooldown_active = False

            threading.Thread(target=cooldown_timer, daemon=True).start()

    def reset_state(self):
        self.last_signal = "NO_TRADE"
        self.last_signal_time = None
        self.consecutive_signals = 0
        self.signal_cooldown_active = False
        self.data_lock.clear()
        self.signal_stats = {
            "total_signals": 0, "buy_signals": 0, "sell_signals": 0,
            "sniper_signals": 0, "tdi_extreme_events": 0, "bb_touch_events": 0,
            "structure_events": 0, "mss_events": 0, "liquidity_sweep_events": 0,
            "fvg_events": 0, "ltf_confirmations": 0, "hard_signals": 0,
            "soft_signals": 0, "rrr_values": [], "htf_aligned": 0,
            "htf_conflicts": 0, "signals_approved": 0, "signals_rejected": 0,
            "score_approved": 0, "score_rejected": 0,
            "grade_a_signals": 0, "grade_b_signals": 0, "grade_c_rejected": 0,
            "divergence_signals": 0, "pattern_signals": 0,
            "sr_signals": 0, "squeeze_signals": 0, "session_adjusted": 0,
        }


# Create singleton instance
strategy = ConsolidatedTrendStrategy()

# Export
__all__ = [
    "strategy",
    "ConsolidatedTrendStrategy",
    "SuperTDIDetector",
    "FeeConfig",
    "DataLock",
    "SignalScorer",
    "VolumeNormalizer",
    "RejectionTracker",
    "ConfidenceDecay",
]
