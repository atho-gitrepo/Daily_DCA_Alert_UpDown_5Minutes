"""
Day Trading Strategy - Momentum Based
Version: 1.0.1 - FIXED: TimeframeData field names
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
    """Data from each timeframe for day trading."""
    symbol: str
    ultra_ltf_1m: pd.DataFrame   # 1m (ultra entry timing)
    ltf_5m: pd.DataFrame         # 5m (entry timing)
    mtf_15m: pd.DataFrame        # 15m (entry confirmation)
    htf_1h: pd.DataFrame         # 1h (trend direction)
    ultra_htf_4h: pd.DataFrame   # 4h (major trend)

    def is_valid(self) -> bool:
        """Check if all timeframes have data."""
        return all([
            self.ultra_ltf_1m is not None and not self.ultra_ltf_1m.empty,
            self.ltf_5m is not None and not self.ltf_5m.empty,
            self.mtf_15m is not None and not self.mtf_15m.empty,
            self.htf_1h is not None and not self.htf_1h.empty,
            self.ultra_htf_4h is not None and not self.ultra_htf_4h.empty,
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
        self.MOMENTUM_THRESHOLD = 1.0
        self.VOLUME_THRESHOLD = 1.5
        self.MIN_SCORE = 70

    def analyze_timeframes(self, data: TimeframeData) -> Dict[str, Any]:
        """Analyze all timeframes and return signals."""
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
            htf_4h = self._analyze_ultra_htf_4h(data.ultra_htf_4h)
            result['timeframes']['ultra_htf_4h'] = htf_4h

            # ===== HTF (1h) - Medium Trend =====
            htf_1h = self._analyze_htf_1h(data.htf_1h)
            result['timeframes']['htf_1h'] = htf_1h

            # ===== MTF (15m) - Breakout Detection =====
            mtf_15m = self._analyze_mtf_15m(data.mtf_15m)
            result['timeframes']['mtf_15m'] = mtf_15m

            # ===== LTF (5m) - Entry Confirmation =====
            ltf_5m = self._analyze_ltf_5m(data.ltf_5m)
            result['timeframes']['ltf_5m'] = ltf_5m

            # ===== ULTRA LTF (1m) - Exact Entry =====
            ultra_1m = self._analyze_ultra_1m(data.ultra_ltf_1m)
            result['timeframes']['ultra_1m'] = ultra_1m

            # ===== Generate Signal =====
            signal, direction, confidence, score, reason = self._generate_signal(
                htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m
            )

            result['signal'] = signal
            result['direction'] = direction
            result['confidence'] = confidence
            result['score'] = score
            result['reason'] = reason

        except Exception as e:
            self.logger.error(f"Error analyzing timeframes: {e}")
            import traceback
            traceback.print_exc()

        return result

    def _analyze_ultra_htf_4h(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 4h timeframe - Major trend."""
        if df is None or df.empty:
            return {'trend': 'NEUTRAL', 'strength': 0}

        try:
            df = df.copy()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

            last = df.iloc[-1]
            close = last.get('close', 0)
            ema50 = last.get('ema50', close)
            ema200 = last.get('ema200', close)

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

            return {
                'trend': trend,
                'strength': strength,
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
            df = df.copy()
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df = Indicators.calculate_tdi(df)

            last = df.iloc[-1]
            close = last.get('close', 0)
            ema20 = last.get('ema20', close)
            ema50 = last.get('ema50', close)
            tdi = last.get('tdi_slow_ma', 50)

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
            df = df.copy()
            df = calculate_heikin_ashi(df)
            df = Indicators.calculate_bollinger_bands(df)
            df = Indicators.calculate_tdi(df)

            if 'volume' in df.columns:
                df['volume_sma'] = df['volume'].rolling(20).mean()
                df['volume_ratio'] = df['volume'] / df['volume_sma'].replace(0, 1)
            else:
                df['volume_ratio'] = 1.0

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            close = last.get('close', 0)
            ha_close = last.get('ha_close', close)
            ha_prev_close = prev.get('ha_close', close)
            bb_upper = last.get('bb_upper', 0)
            bb_lower = last.get('bb_lower', 0)
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_slow = last.get('tdi_slow_ma', 50)
            volume_ratio = last.get('volume_ratio', 1)

            above_bb_upper = ha_close > bb_upper * 1.001 if bb_upper > 0 else False
            below_bb_lower = ha_close < bb_lower * 0.999 if bb_lower > 0 else False

            bullish_momentum = tdi_fast > tdi_slow and ha_close > ha_prev_close
            bearish_momentum = tdi_fast < tdi_slow and ha_close < ha_prev_close

            volume_confirmed = volume_ratio > self.VOLUME_THRESHOLD

            bullish_breakout = above_bb_upper and bullish_momentum and volume_confirmed
            bearish_breakout = below_bb_lower and bearish_momentum and volume_confirmed

            return {
                'breakout': bullish_breakout or bearish_breakout,
                'direction': 'BUY' if bullish_breakout else 'SELL' if bearish_breakout else 'NONE',
                'bb_upper': bb_upper,
                'bb_lower': bb_lower,
                'tdi_fast': tdi_fast,
                'tdi_slow': tdi_slow,
                'volume_ratio': volume_ratio,
                'ha_color': last.get('ha_color', 0),
            }

        except Exception as e:
            self.logger.error(f"Error in 15m analysis: {e}")
            return {'breakout': False, 'direction': 'NONE'}

    def _analyze_ltf_5m(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 5m timeframe - Entry confirmation."""
        if df is None or df.empty:
            return {'entry': False, 'direction': 'NONE'}

        try:
            df = df.copy()
            df = calculate_heikin_ashi(df)
            df = Indicators.calculate_tdi(df, rsi_period=10, slow_ma_period=5)
            df = Indicators.calculate_bollinger_bands(df)

            if 'volume' in df.columns:
                df['volume_sma'] = df['volume'].rolling(20).mean()
                df['volume_ratio'] = df['volume'] / df['volume_sma'].replace(0, 1)
            else:
                df['volume_ratio'] = 1.0

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

            bullish_cross = tdi_fast > tdi_slow and tdi_fast_prev <= tdi_slow_prev
            bearish_cross = tdi_fast < tdi_slow and tdi_fast_prev >= tdi_slow_prev

            ha_bullish = ha_close > ha_prev_close and last.get('ha_color', 0) == 1
            ha_bearish = ha_close < ha_prev_close and last.get('ha_color', 0) == -1

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

    def _analyze_ultra_1m(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze 1m timeframe - Exact entry timing."""
        if df is None or df.empty:
            return {'bullish_cross': False, 'bearish_cross': False}

        try:
            df = df.copy()
            df = calculate_heikin_ashi(df)
            df = Indicators.calculate_tdi(df, rsi_period=5, slow_ma_period=3)

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_slow = last.get('tdi_slow_ma', 50)
            tdi_fast_prev = prev.get('tdi_fast_ma', 50)
            tdi_slow_prev = prev.get('tdi_slow_ma', 50)

            bullish_cross = tdi_fast > tdi_slow and tdi_fast_prev <= tdi_slow_prev
            bearish_cross = tdi_fast < tdi_slow and tdi_fast_prev >= tdi_slow_prev

            return {
                'bullish_cross': bullish_cross,
                'bearish_cross': bearish_cross,
                'tdi_fast': tdi_fast,
                'tdi_slow': tdi_slow,
            }

        except Exception as e:
            self.logger.error(f"Error in 1m analysis: {e}")
            return {'bullish_cross': False, 'bearish_cross': False}

    def _generate_signal(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict, ultra_1m: Dict) -> Tuple[str, str, float, int, str]:
        """Generate final signal from all timeframes."""
        # ===== BUY SIGNAL =====
        if self._is_buy_signal(htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m):
            confidence = self._calculate_confidence(htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m)
            score = int(confidence * 100)
            reason = self._build_reason('BUY', htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m)

            if score >= self.MIN_SCORE:
                return 'SIGNAL', 'BUY', confidence, score, reason

        # ===== SELL SIGNAL =====
        if self._is_sell_signal(htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m):
            confidence = self._calculate_confidence(htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m)
            score = int(confidence * 100)
            reason = self._build_reason('SELL', htf_4h, htf_1h, mtf_15m, ltf_5m, ultra_1m)

            if score >= self.MIN_SCORE:
                return 'SIGNAL', 'SELL', confidence, score, reason

        return 'NO_TRADE', 'NONE', 0, 0, "No signal conditions met"

    def _is_buy_signal(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict, ultra_1m: Dict) -> bool:
        """Check BUY signal conditions."""
        if htf_4h.get('trend') != 'BULLISH':
            return False
        if htf_1h.get('trend') != 'BULLISH':
            return False

        if mtf_15m.get('direction') == 'BUY':
            return True
        if ltf_5m.get('direction') == 'BUY':
            return True

        return False

    def _is_sell_signal(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict, ultra_1m: Dict) -> bool:
        """Check SELL signal conditions."""
        if htf_4h.get('trend') != 'BEARISH':
            return False
        if htf_1h.get('trend') != 'BEARISH':
            return False

        if mtf_15m.get('direction') == 'SELL':
            return True
        if ltf_5m.get('direction') == 'SELL':
            return True

        return False

    def _calculate_confidence(self, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict, ultra_1m: Dict) -> float:
        """Calculate confidence score."""
        confidence = 0.5

        confidence += htf_4h.get('strength', 0) * 0.20
        confidence += htf_1h.get('strength', 0) * 0.20

        if mtf_15m.get('breakout'):
            confidence += 0.20

        if ltf_5m.get('entry'):
            confidence += 0.20

        volume_ratio = max(mtf_15m.get('volume_ratio', 1), ltf_5m.get('volume_ratio', 1))
        if volume_ratio > 2.0:
            confidence += 0.10
        elif volume_ratio > 1.5:
            confidence += 0.05

        return min(0.95, confidence)

    def _build_reason(self, direction: str, htf_4h: Dict, htf_1h: Dict, mtf_15m: Dict, ltf_5m: Dict, ultra_1m: Dict) -> str:
        """Build human-readable reason."""
        parts = [f"{direction}: Multi-frame confirmed"]

        parts.append(f"4h {htf_4h.get('trend', 'NEUTRAL')} ({htf_4h.get('strength', 0):.0%})")
        parts.append(f"1h {htf_1h.get('trend', 'NEUTRAL')} ({htf_1h.get('strength', 0):.0%})")

        if mtf_15m.get('breakout'):
            parts.append(f"15m BREAKOUT")
        if ltf_5m.get('entry'):
            parts.append(f"5m ENTRY")
        if ultra_1m.get('bullish_cross') or ultra_1m.get('bearish_cross'):
            parts.append(f"1m CROSSOVER")

        return " | ".join(parts)

    def get_stop_loss(self, entry: float, direction: str, df: pd.DataFrame) -> Tuple[float, float]:
        """Calculate SL/TP for 1-hour hold using ATR."""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            tr1 = high - low
            tr2 = np.abs(high - np.roll(close, 1))
            tr3 = np.abs(low - np.roll(close, 1))
            tr = np.maximum(tr1, np.maximum(tr2, tr3))
            atr = np.mean(tr[-14:]) if len(tr) >= 14 else entry * 0.01

            if direction == 'BUY':
                sl = entry - (1.5 * atr)
                tp = entry + (3.0 * atr)
            else:
                sl = entry + (1.5 * atr)
                tp = entry - (3.0 * atr)

            return sl, tp

        except Exception as e:
            self.logger.error(f"Error calculating SL/TP: {e}")
            if direction == 'BUY':
                return entry * 0.985, entry * 1.03
            else:
                return entry * 1.015, entry * 0.97

    def get_exit_time(self, entry_time: datetime) -> datetime:
        """Calculate exit time for 1-hour hold."""
        return entry_time + timedelta(minutes=self.MAX_HOLD_MINUTES)
