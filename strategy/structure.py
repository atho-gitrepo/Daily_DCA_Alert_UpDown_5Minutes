# strategy/structure.py
"""
Market Structure Module - v3.4.0
BOS, CHoCH, liquidity sweep, reclaim logic.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
from scipy.signal import find_peaks


@dataclass
class StructureData:
    """Market structure analysis result."""
    swing_high: float = 0
    swing_low: float = 0
    higher_high: bool = False
    higher_low: bool = False
    lower_high: bool = False
    lower_low: bool = False
    bos: bool = False  # Break of Structure
    choch: bool = False  # Change of Character
    liquidity_sweep: bool = False
    support_reclaim: bool = False
    resistance_rejection: bool = False
    structure_direction: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL
    structure_strength: float = 0.0


class MarketStructureAnalyzer:
    """
    v3.4.0 Market Structure Module.
    Detects BOS, CHoCH, liquidity sweeps, and reclaims.
    """

    def __init__(self, lookback: int = 20, swing_distance: int = 3):
        self.lookback = lookback
        self.swing_distance = swing_distance
        self._swing_highs: List[float] = []
        self._swing_lows: List[float] = []
        self._last_structure: Optional[StructureData] = None

    def analyze(self, df: pd.DataFrame) -> StructureData:
        """
        Analyze market structure.

        Args:
            df: DataFrame with OHLC data

        Returns:
            StructureData with all structure signals
        """
        if df is None or df.empty or len(df) < self.lookback:
            return StructureData()

        try:
            # Get recent data
            recent = df.iloc[-self.lookback:].copy()
            highs = recent['high'].values
            lows = recent['low'].values
            close = recent['close'].values
            current_price = close[-1] if len(close) > 0 else 0

            # Find swing points
            swing_highs, swing_high_idx = self._find_swing_highs(highs)
            swing_lows, swing_low_idx = self._find_swing_lows(lows)

            # Store for reference
            self._swing_highs = swing_highs
            self._swing_lows = swing_lows

            # Analyze structure
            result = StructureData()

            if len(swing_highs) >= 2:
                result.higher_high = swing_highs[-1] > swing_highs[-2]
                result.lower_high = swing_highs[-1] < swing_highs[-2]

            if len(swing_lows) >= 2:
                result.higher_low = swing_lows[-1] > swing_lows[-2]
                result.lower_low = swing_lows[-1] < swing_lows[-2]

            # BOS - Break of Structure
            result.bos = self._detect_bos(swing_highs, swing_lows, current_price)

            # CHoCH - Change of Character
            result.choch = self._detect_choch(swing_highs, swing_lows)

            # Liquidity Sweep
            result.liquidity_sweep = self._detect_liquidity_sweep(highs, lows, swing_highs, swing_lows)

            # Support Reclaim
            result.support_reclaim = self._detect_support_reclaim(df, swing_lows)

            # Resistance Rejection
            result.resistance_rejection = self._detect_resistance_rejection(df, swing_highs)

            # Set swing levels
            if swing_highs:
                result.swing_high = swing_highs[-1]
            if swing_lows:
                result.swing_low = swing_lows[-1]

            # Determine structure direction
            if result.higher_high and result.higher_low:
                result.structure_direction = "BULLISH"
                result.structure_strength = 0.8
            elif result.lower_high and result.lower_low:
                result.structure_direction = "BEARISH"
                result.structure_strength = 0.8
            elif result.higher_high:
                result.structure_direction = "BULLISH"
                result.structure_strength = 0.5
            elif result.lower_low:
                result.structure_direction = "BEARISH"
                result.structure_strength = 0.5
            else:
                result.structure_direction = "NEUTRAL"
                result.structure_strength = 0.2

            self._last_structure = result
            return result

        except Exception as e:
            return StructureData()

    def _find_swing_highs(self, prices: np.ndarray) -> Tuple[List[float], List[int]]:
        """Find swing highs using peak detection."""
        peaks_idx, _ = find_peaks(prices, distance=self.swing_distance, prominence=0.001)
        peaks = [float(prices[i]) for i in peaks_idx]
        return peaks, peaks_idx.tolist()

    def _find_swing_lows(self, prices: np.ndarray) -> Tuple[List[float], List[int]]:
        """Find swing lows using trough detection."""
        troughs_idx, _ = find_peaks(-prices, distance=self.swing_distance, prominence=0.001)
        troughs = [float(prices[i]) for i in troughs_idx]
        return troughs, troughs_idx.tolist()

    def _detect_bos(self, swing_highs: List[float], swing_lows: List[float], current_price: float) -> bool:
        """Detect Break of Structure."""
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return False

        # Bullish BOS: Break above previous swing high
        if current_price > swing_highs[-2]:
            return True

        # Bearish BOS: Break below previous swing low
        if current_price < swing_lows[-2]:
            return True

        return False

    def _detect_choch(self, swing_highs: List[float], swing_lows: List[float]) -> bool:
        """Detect Change of Character."""
        if len(swing_highs) < 3 or len(swing_lows) < 3:
            return False

        # Bullish CHoCH: Lower low then higher low (trend change from bear to bull)
        if swing_lows[-2] < swing_lows[-3] and swing_lows[-1] > swing_lows[-2]:
            return True

        # Bearish CHoCH: Higher high then lower high (trend change from bull to bear)
        if swing_highs[-2] > swing_highs[-3] and swing_highs[-1] < swing_highs[-2]:
            return True

        return False

    def _detect_liquidity_sweep(self, highs: np.ndarray, lows: np.ndarray,
                                swing_highs: List[float], swing_lows: List[float]) -> bool:
        """Detect liquidity sweep (price sweeping previous highs/lows)."""
        if len(highs) < 3 or len(swing_highs) < 2 or len(swing_lows) < 2:
            return False

        current_high = highs[-1]
        current_low = lows[-1]
        prev_high = swing_highs[-2]
        prev_low = swing_lows[-2]

        # Sweeping previous high or low
        if current_high > prev_high or current_low < prev_low:
            return True

        return False

    def _detect_support_reclaim(self, df: pd.DataFrame, swing_lows: List[float]) -> bool:
        """Detect support reclaim after a sweep."""
        if len(swing_lows) < 2:
            return False

        close = df['close'].values
        current_price = close[-1] if len(close) > 0 else 0
        support = swing_lows[-1]

        # Price broke below support then reclaimed
        if len(close) > 2:
            min_price = min(close[-3:])
            if min_price < support and current_price > support:
                return True

        return False

    def _detect_resistance_rejection(self, df: pd.DataFrame, swing_highs: List[float]) -> bool:
        """Detect resistance rejection (price rejected at resistance)."""
        if len(swing_highs) < 2:
            return False

        close = df['close'].values
        high = df['high'].values
        current_price = close[-1] if len(close) > 0 else 0
        resistance = swing_highs[-1]

        # Price touched resistance and rejected
        if len(high) > 2:
            max_high = max(high[-3:])
            if max_high >= resistance and current_price < resistance * 0.995:
                return True

        return False

    def get_structure_summary(self) -> Dict[str, Any]:
        """Get summary of current structure."""
        if self._last_structure is None:
            return {'structure': 'NONE', 'strength': 0}

        return {
            'direction': self._last_structure.structure_direction,
            'strength': self._last_structure.structure_strength,
            'bos': self._last_structure.bos,
            'choch': self._last_structure.choch,
            'liquidity_sweep': self._last_structure.liquidity_sweep,
            'support_reclaim': self._last_structure.support_reclaim,
            'resistance_rejection': self._last_structure.resistance_rejection,
        }


# Singleton
structure_analyzer = MarketStructureAnalyzer()
