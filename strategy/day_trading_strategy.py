"""
Day Trading Strategy - Momentum Based
Version: 1.0.0 - Multi-Timeframe Day Trading
Designed for 1-hour holds
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple, Dict, Optional, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from utils.indicators import Indicators, calculate_heikin_ashi

logger = logging.getLogger(__name__)

EMOJI = {
    "BUY": "🟢",
    "SELL": "🔴",
    "HTF": "📊",
    "MTF": "📈",
    "LTF": "⏱️",
    "ULTRA": "⚡",
    "SIGNAL": "🎯",
    "VOLUME": "📊",
    "MOMENTUM": "🚀",
}


@dataclass
class TimeframeData:
    """Data from each timeframe."""
    symbol: str
    ultra_ltf_5m: pd.DataFrame  # 5m (entry timing)
    ltf_15m: pd.DataFrame       # 15m (entry confirmation)
    mtf_1h: pd.DataFrame        # 1h (trend direction)
    htf_4h: pd.DataFrame        # 4h (major trend)

    def is_valid(self) -> bool:
        return all([
            self.ultra_ltf_5m is not None and not self.ultra_ltf_5m.empty,
            self.ltf_15m is not None and not self.ltf_15m.empty,
            self.mtf_1h is not None and not self.mtf_1h.empty,
            self.htf_4h is not None and not self.htf_4h.empty,
        ])


class DayTradingStrategy:
    """
    Day Trading Strategy - 1-hour holds
    Multi-Timeframe Momentum Trading
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.last_signal = "NO_TRADE"
        self.last_signal_time = None

        # Timeframe settings
        self.TIMEFRAMES = {
            'ultra_ltf': '1m',
            'ltf': '5m',
            'mtf': '15m',
            'htf': '1h',
            'ultra_htf': '4h',
        }

        # Hold time settings
        self.MAX_HOLD_MINUTES = 60
        self.MIN_HOLD_MINUTES = 15

        # Momentum thresholds
        self.MOMENTUM_THRESHOLD = 1.0  # 1% momentum
        self.VOLUME_THRESHOLD = 1.5    # 1.5x volume
        self.MIN_SCORE = 70

    def analyze_timeframes(self, data: TimeframeData) -> Dict[str, Any]:
        """
        Analyze all timeframes and return signals.
        """
        result = {
            'signal': 'NO_TRADE',
            'direction': 'NONE',
            'confidence': 0,
            'score': 0,
            'reason': '',
            'timeframes': {},
        }

        try:
            # ===== HTF (4h) - Major Trend =====
            htf_4h = self._analyze_htf_4h(data.htf_4h)
            result['timeframes']['htf_4h'] = htf_4h

            # ===== HTF (1h) - Medium Trend =====
            htf_1h = self._analyze_htf_1h(data.mtf_1h)
            result['timeframes']['htf_1h'] = htf_1h

            # ===== MTF (15m) - Breakout Detection =====
            mtf_15m = self._analyze_mtf_15m(data.ltf_15m)
            result['timeframes']['mtf_15m'] = mtf_15m

            # ===== LTF (5m) - Entry Confirmation =====
            ltf_5m = self._analyze_ltf_5m(data.ultra_ltf_5m)
            result['timeframes']['ltf_5m'] = ltf_5m

            # ===== Generate Signal =====
            signal, direction, confidence, score, reason = self._generate_signal(
                htf_4h, htf_1h, mtf_15m, ltf_5m
            )

            result['signal'] = signal
            result['direction'] = direction
            result['confidence'] = confidence
            result['score'] = score
            result['reason'] = reason

        except Exception as e:
            self.logger.error(f"Error analyzing timeframes: {e}")

        return result

    def _analyze_htf_4h(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 4h timeframe - Major trend."""
        if df is None or df.empty:
            return {'trend': 'NEUTRAL', 'strength': 0}

        try:
            # Calculate EMA
            df = Indicators.calculate_ema(df, 'close', 50)  # 4h EMA = 200 periods on 15m
            df = Indicators.calculate_ema(df, 'close', 200)

            last = df.iloc[-1]
            close = last.get('close', 0)
            ema50 = last.get('close_ema_50', close)
            ema200 = last.get('close_ema_200', close)

            # Trend detection
            if close > ema50 and ema50 > ema200:
                trend = 'BULLISH'
                strength = 1.0
            elif close < ema50 and ema50 < ema200:
                trend = 'BEARISH'
                strength = 1.0
            elif close > ema50:
                trend = 'BULLISH'
                strength = 0.6
            elif close < ema50:
                trend = 'BEARISH'
                strength = 0.6
            else:
                trend = 'NEUTRAL'
                strength = 0

            # ADX for trend strength
            df = Indicators.calculate_adx(df)
            adx = last.get('adx', 20)

            if adx > 25:
                strength = min(1.0, strength + 0.2)

            return {
                'trend': trend,
                'strength': strength,
                'adx': adx,
                'ema50': ema50,
                'ema200': ema200,
            }

        except Exception as e:
            self.logger.error(f"Error in 4h analysis: {e}")
            return {'trend': 'NEUTRAL', 'strength': 0}

    def _analyze_htf_1h(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 1h timeframe - Medium trend."""
        if df is None or df.empty:
            return {'trend': 'NEUTRAL', 'strength': 0}

        try:
            df = Indicators.calculate_ema(df, 'close', 20)  # 1h EMA = 20 periods
            df = Indicators.calculate_ema(df, 'close', 50)
            df = Indicators.calculate_tdi(df)

            last = df.iloc[-1]
            close = last.get('close', 0)
            ema20 = last.get('close_ema_20', close)
            ema50 = last.get('close_ema_50', close)
            tdi = last.get('tdi_slow_ma', 50)

            # Trend
            if close > ema20 and ema20 > ema50:
                trend = 'BULLISH'
                strength = 0.8
            elif close < ema20 and ema20 < ema50:
                trend = 'BEARISH'
                strength = 0.8
            elif close > ema20:
                trend = 'BULLISH'
                strength = 0.5
            elif close < ema20:
                trend = 'BEARISH'
                strength = 0.5
            else:
                trend = 'NEUTRAL'
                strength = 0

            # TDI momentum
            if 25 <= tdi <= 35:
                strength += 0.1  # Oversold but trending up
            elif 65 <= tdi <= 75:
                strength += 0.1  # Overbought but trending down

            return {
                'trend': trend,
                'strength': min(1.0, strength),
                'tdi': tdi,
                'ema20': ema20,
                'ema50': ema50,
            }

        except Exception as e:
            self.logger.error(f"Error in 1h analysis: {e}")
            return {'trend': 'NEUTRAL', 'strength': 0}

    def _analyze_mtf_15m(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 15m timeframe - Breakout/Entry."""
        if df is None or df.empty:
            return {'breakout': False, 'direction': 'NONE'}

        try:
            # Calculate indicators
            df = calculate_heikin_ashi(df)
            df = Indicators.calculate_bollinger_bands(df)
            df = Indicators.calculate_tdi(df)

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            close = last.get('close', 0)
            ha_close = last.get('ha_close', close)
            ha_prev_close = prev.get('ha_close', close)
            bb_upper = last.get('bb_upper', 0)
            bb_lower = last.get('bb_lower', 0)
            bb_middle = last.get('bb_middle', 0)
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_slow = last.get('tdi_slow_ma', 50)
            volume_ratio = last.get('volume_ratio', 1)

            # Breakout detection
            above_bb_upper = ha_close > bb_upper * 1.001 if bb_upper > 0 else False
            below_bb_lower = ha_close < bb_lower * 0.999 if bb_lower > 0 else False

            # Momentum
            bullish_momentum = tdi_fast > tdi_slow and ha_close > ha_prev_close
            bearish_momentum = tdi_fast < tdi_slow and ha_close < ha_prev_close

            # Volume confirmation
            volume_confirmed = volume_ratio > self.VOLUME_THRESHOLD

            # Breakout
            bullish_breakout = above_bb_upper and bullish_momentum and volume_confirmed
            bearish_breakout = below_bb_lower and bearish_momentum and volume_confirmed

            return {
                'breakout': bullish_breakout or bearish_breakout,
                'direction': 'BUY' if bullish_breakout else 'SELL' if bearish_breakout else 'NONE',
                'bb_upper': bb_upper,
                'bb_lower': bb_lower,
                'bb_middle': bb_middle,
                'tdi_fast': tdi_fast,
                'tdi_slow': tdi_slow,
                'volume_ratio': volume_ratio,
                'ha_color': last.get('ha_color', 0),
            }

        except Exception as e:
            self.logger.error(f"Error in 15m analysis: {e}")
            return {'breakout': False, 'direction': 'NONE'}

    def _analyze_ltf_5m(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 5m timeframe - Entry timing."""
        if df is None or df.empty:
            return {'entry': False, 'direction': 'NONE'}

        try:
            df = calculate_heikin_ashi(df)
            df = Indicators.calculate_tdi(df, rsi_period=10, slow_ma_period=5)
            df = Indicators.calculate_bollinger_bands(df)

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            close = last.get('close', 0)
            ha_close = last.get('ha_close', close)
            ha_prev_close = prev.get('ha_close', close)
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_slow = last.get('tdi_slow_ma', 50)
            tdi_fast_prev = prev.get('tdi_fast_ma', 50)
            tdi_slow_prev = prev.get('tdi_slow_ma', 50)
            volume_ratio = last.get('volume_ratio', 1)

            # Crossover detection
            bullish_cross = tdi_fast > tdi_slow and tdi_fast_prev <= tdi_slow_prev
            bearish_cross = tdi_fast < tdi_slow and tdi_fast_prev >= tdi_slow_prev

            # HA momentum
            ha_bullish = ha_close > ha_prev_close and last.get('ha_color', 0) == 1
            ha_bearish = ha_close < ha_prev_close and last.get('ha_color', 0) == -1

            # Entry signal
            entry_buy = bullish_cross and ha_bullish and volume_ratio > 1.0
            entry_sell = bearish_cross and ha_bearish and volume_ratio > 1.0

            return {
                'entry': entry_buy or entry_sell,
                'direction': 'BUY' if entry_buy else 'SELL' if entry_sell else 'NONE',
                'bullish_cross': bullish_cross,
                'bearish_cross': bearish_cross,
                'tdi_fast': tdi_fast,
                'tdi_slow': tdi_slow,
                'volume_ratio': volume_ratio,
                'ha_color': last.get('ha_color', 0),
            }

        except Exception as e:
            self.logger.error(f"Error in 5m analysis: {e}")
            return {'entry': False, 'direction': 'NONE'}

    def _generate_signal(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict) -> Tuple[str, str, float, int, str]:
        """
        Generate final signal from all timeframes.
        """
        # ===== BUY SIGNAL =====
        if self._is_buy_signal(htf_4h, htf_1h, mtf_15m, ltf_5m):
            confidence = self._calculate_confidence(htf_4h, htf_1h, mtf_15m, ltf_5m)
            score = int(confidence * 100)
            reason = self._build_reason('BUY', htf_4h, htf_1h, mtf_15m, ltf_5m)

            if score >= self.MIN_SCORE:
                return 'SIGNAL', 'BUY', confidence, score, reason

        # ===== SELL SIGNAL =====
        if self._is_sell_signal(htf_4h, htf_1h, mtf_15m, ltf_5m):
            confidence = self._calculate_confidence(htf_4h, htf_1h, mtf_15m, ltf_5m)
            score = int(confidence * 100)
            reason = self._build_reason('SELL', htf_4h, htf_1h, mtf_15m, ltf_5m)

            if score >= self.MIN_SCORE:
                return 'SIGNAL', 'SELL', confidence, score, reason

        return 'NO_TRADE', 'NONE', 0, 0, "No signal conditions met"

    def _is_buy_signal(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict) -> bool:
        """Check BUY signal conditions."""
        # MUST have bullish 1h and 4h (higher timeframe alignment)
        if htf_4h.get('trend') != 'BULLISH':
            return False
        if htf_1h.get('trend') != 'BULLISH':
            return False

        # 15m breakout or 5m entry
        if mtf_15m.get('direction') == 'BUY':
            return True
        if ltf_5m.get('direction') == 'BUY':
            return True

        return False

    def _is_sell_signal(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict) -> bool:
        """Check SELL signal conditions."""
        # MUST have bearish 1h and 4h
        if htf_4h.get('trend') != 'BEARISH':
            return False
        if htf_1h.get('trend') != 'BEARISH':
            return False

        # 15m breakdown or 5m entry
        if mtf_15m.get('direction') == 'SELL':
            return True
        if ltf_5m.get('direction') == 'SELL':
            return True

        return False

    def _calculate_confidence(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict) -> float:
        """Calculate confidence score."""
        confidence = 0.5

        # HTF strength (40% weight)
        confidence += htf_4h.get('strength', 0) * 0.20
        confidence += htf_1h.get('strength', 0) * 0.20

        # MTF breakout (20% weight)
        if mtf_15m.get('breakout'):
            confidence += 0.20

        # LTF entry (20% weight)
        if ltf_5m.get('entry'):
            confidence += 0.20

        # Volume (bonus)
        volume_ratio = max(mtf_15m.get('volume_ratio', 1), ltf_5m.get('volume_ratio', 1))
        if volume_ratio > 2.0:
            confidence += 0.10
        elif volume_ratio > 1.5:
            confidence += 0.05

        return min(0.95, confidence)

    def _build_reason(self, direction: str, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict) -> str:
        """Build human-readable reason."""
        parts = [f"{direction}: Multiframe confirmed"]

        parts.append(f"4h {htf_4h.get('trend', 'NEUTRAL')} ({htf_4h.get('strength', 0):.0%})")
        parts.append(f"1h {htf_1h.get('trend', 'NEUTRAL')} ({htf_1h.get('strength', 0):.0%})")

        if mtf_15m.get('breakout'):
            parts.append(f"15m BREAKOUT")
        if ltf_5m.get('entry'):
            parts.append(f"5m ENTRY")

        return " | ".join(parts)

    def get_stop_loss(self, entry: float, direction: str, df: pd.DataFrame) -> Tuple[float, float]:
        """Calculate SL/TP for 1-hour hold."""
        # ATR for volatility-based SL
        atr_period = 14
        df = Indicators._calculate_atr(df, atr_period)
        atr = df['atr'].iloc[-1] if 'atr' in df.columns else entry * 0.01

        # SL = entry ± (1.5 * ATR)
        if direction == 'BUY':
            sl = entry - (1.5 * atr)
            tp = entry + (3.0 * atr)  # 2:1 RRR
        else:
            sl = entry + (1.5 * atr)
            tp = entry - (3.0 * atr)

        return sl, tp

    def get_exit_time(self, entry_time: datetime) -> datetime:
        """Calculate exit time for 1-hour hold."""
        return entry_time + timedelta(minutes=self.MAX_HOLD_MINUTES)
