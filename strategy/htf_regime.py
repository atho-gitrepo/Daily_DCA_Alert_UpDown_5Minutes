# strategy/htf_regime.py
"""
HTF Regime System - v3.4.0
4H and 1H trend analysis for directional bias.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class Regime(Enum):
    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    MILD_BULL = "MILD_BULL"
    NEUTRAL = "NEUTRAL"
    MILD_BEAR = "MILD_BEAR"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"
    CONFLICT = "CONFLICT"


@dataclass
class RegimeData:
    """HTF regime analysis result."""
    regime: Regime
    trend_4h: str  # BULLISH, BEARISH, NEUTRAL
    trend_1h: str  # BULLISH, BEARISH, NEUTRAL
    strength_4h: float  # 0-1
    strength_1h: float  # 0-1
    adx_4h: float
    adx_1h: float
    is_bullish: bool
    is_bearish: bool
    is_conflict: bool


class HTFRegimeAnalyzer:
    """
    v3.4.0 HTF Regime System.
    Uses 4H and 1H timeframes for directional bias.
    """

    def __init__(self):
        self.current_regime: Regime = Regime.NEUTRAL
        self.last_analysis: Dict[str, Any] = {}

        # Thresholds
        self.ADX_TREND_THRESHOLD = 25
        self.ADX_STRONG_THRESHOLD = 40
        self.MA_ALIGNMENT_THRESHOLD = 0.01  # 1%

    def analyze(self, df_4h: pd.DataFrame, df_1h: pd.DataFrame) -> RegimeData:
        """
        Analyze both timeframes to determine regime.

        Args:
            df_4h: 4H timeframe data
            df_1h: 1H timeframe data

        Returns:
            RegimeData with regime classification
        """
        # Analyze each timeframe
        trend_4h, strength_4h, adx_4h = self._analyze_trend(df_4h)
        trend_1h, strength_1h, adx_1h = self._analyze_trend(df_1h)

        # Determine regime based on combination
        regime = self._determine_regime(trend_4h, trend_1h)

        is_bullish = regime in [Regime.STRONG_BULL, Regime.BULL, Regime.MILD_BULL]
        is_bearish = regime in [Regime.STRONG_BEAR, Regime.BEAR, Regime.MILD_BEAR]
        is_conflict = regime == Regime.CONFLICT

        result = RegimeData(
            regime=regime,
            trend_4h=trend_4h,
            trend_1h=trend_1h,
            strength_4h=strength_4h,
            strength_1h=strength_1h,
            adx_4h=adx_4h,
            adx_1h=adx_1h,
            is_bullish=is_bullish,
            is_bearish=is_bearish,
            is_conflict=is_conflict,
        )

        self.current_regime = regime
        self.last_analysis = {
            'regime': regime.value,
            'trend_4h': trend_4h,
            'trend_1h': trend_1h,
            'strength_4h': strength_4h,
            'strength_1h': strength_1h,
            'adx_4h': adx_4h,
            'adx_1h': adx_1h,
        }

        return result

    def get_directional_bias(self) -> str:
        """Get directional bias from current regime."""
        if self.current_regime in [Regime.STRONG_BULL, Regime.BULL, Regime.MILD_BULL]:
            return "BULLISH"
        elif self.current_regime in [Regime.STRONG_BEAR, Regime.BEAR, Regime.MILD_BEAR]:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def is_buy_favored(self) -> bool:
        """Check if BUY signals are favored."""
        return self.current_regime in [Regime.STRONG_BULL, Regime.BULL]

    def is_sell_favored(self) -> bool:
        """Check if SELL signals are favored."""
        return self.current_regime in [Regime.STRONG_BEAR, Regime.BEAR]

    def get_regime_weight(self) -> float:
        """Get regime weight for scoring (0-1)."""
        weights = {
            Regime.STRONG_BULL: 1.0,
            Regime.BULL: 0.8,
            Regime.MILD_BULL: 0.6,
            Regime.NEUTRAL: 0.5,
            Regime.MILD_BEAR: 0.4,
            Regime.BEAR: 0.2,
            Regime.STRONG_BEAR: 0.0,
            Regime.CONFLICT: 0.3,
        }
        return weights.get(self.current_regime, 0.5)

    def _analyze_trend(self, df: pd.DataFrame) -> Tuple[str, float, float]:
        """
        Analyze trend on a single timeframe.

        Returns:
            (trend, strength, adx)
        """
        if df is None or df.empty or len(df) < 30:
            return "NEUTRAL", 0.0, 0.0

        try:
            # Calculate EMAs
            df = df.copy()
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

            # Calculate ADX
            df = self._calculate_adx(df)

            last = df.iloc[-1]
            close = last.get('close', 0)
            ema20 = last.get('ema20', close)
            ema50 = last.get('ema50', close)
            ema200 = last.get('ema200', close)
            adx = last.get('adx', 0)

            # Determine trend based on EMA alignment
            if close > ema20 > ema50 > ema200:
                trend = "BULLISH"
                strength = min(1.0, adx / 50)
            elif close < ema20 < ema50 < ema200:
                trend = "BEARISH"
                strength = min(1.0, adx / 50)
            elif close > ema20 and close > ema50:
                trend = "BULLISH"
                strength = min(0.7, adx / 40)
            elif close < ema20 and close < ema50:
                trend = "BEARISH"
                strength = min(0.7, adx / 40)
            else:
                trend = "NEUTRAL"
                strength = 0.3

            return trend, strength, adx

        except Exception as e:
            return "NEUTRAL", 0.0, 0.0

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate ADX for trend strength."""
        try:
            high = df['high']
            low = df['low']
            close = df['close']

            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            df['up_move'] = high - high.shift(1)
            df['down_move'] = low.shift(1) - low

            df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
            df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)

            df['tr_smooth'] = df['tr'].ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            df['plus_dm_smooth'] = df['plus_dm'].ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            df['minus_dm_smooth'] = df['minus_dm'].ewm(alpha=1/period, min_periods=period, adjust=False).mean()

            df['plus_di'] = 100 * (df['plus_dm_smooth'] / df['tr_smooth'].replace(0, 1e-10))
            df['minus_di'] = 100 * (df['minus_dm_smooth'] / df['tr_smooth'].replace(0, 1e-10))

            di_sum = df['plus_di'] + df['minus_di'].replace(0, 1e-10)
            df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / di_sum)
            df['adx'] = df['dx'].ewm(alpha=1/period, min_periods=period, adjust=False).mean()

            return df

        except Exception as e:
            df['adx'] = 0
            return df

    def _determine_regime(self, trend_4h: str, trend_1h: str) -> Regime:
        """
        Determine regime based on 4H and 1H trends.

        | 4H       | 1H       | Regime        |
        |----------|----------|---------------|
        | BULLISH  | BULLISH  | STRONG_BULL   |
        | BULLISH  | NEUTRAL  | BULL          |
        | NEUTRAL  | BULLISH  | MILD_BULL     |
        | NEUTRAL  | NEUTRAL  | NEUTRAL       |
        | BEARISH  | BEARISH  | STRONG_BEAR   |
        | BEARISH  | NEUTRAL  | BEAR          |
        | NEUTRAL  | BEARISH  | MILD_BEAR     |
        | BULLISH  | BEARISH  | CONFLICT      |
        | BEARISH  | BULLISH  | CONFLICT      |
        """
        mapping = {
            ("BULLISH", "BULLISH"): Regime.STRONG_BULL,
            ("BULLISH", "NEUTRAL"): Regime.BULL,
            ("NEUTRAL", "BULLISH"): Regime.MILD_BULL,
            ("NEUTRAL", "NEUTRAL"): Regime.NEUTRAL,
            ("BEARISH", "BEARISH"): Regime.STRONG_BEAR,
            ("BEARISH", "NEUTRAL"): Regime.BEAR,
            ("NEUTRAL", "BEARISH"): Regime.MILD_BEAR,
            ("BULLISH", "BEARISH"): Regime.CONFLICT,
            ("BEARISH", "BULLISH"): Regime.CONFLICT,
        }

        return mapping.get((trend_4h, trend_1h), Regime.NEUTRAL)


# Singleton
htf_regime = HTFRegimeAnalyzer()
