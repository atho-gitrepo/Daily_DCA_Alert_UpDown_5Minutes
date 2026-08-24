"""
Super TDI Detector - Super TDI Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple


class TDIDetector:
    """
    Super TDI Detector with standardized zone classification.

    Key Levels:
    - 25: OVERSOLD (Hard Buy Zone - 2x risk)
    - 35: SOFT_BUY (Soft Buy Zone - 1x risk)
    - 50: CENTER_LINE (No Trade Zone)
    - 65: SOFT_SELL (Soft Sell Zone - 1x risk)
    - 75: OVERBOUGHT (Hard Sell Zone - 2x risk)
    """

    def __init__(self):
        self.OVERSOLD = 25.0
        self.SOFT_BUY = 35.0
        self.CENTER_LINE = 50.0
        self.SOFT_SELL = 65.0
        self.OVERBOUGHT = 75.0

    def get_zone(self, tdi_value: float) -> str:
        """Standardized zone classification."""
        if tdi_value <= self.OVERSOLD:
            return "OVERSOLD"
        elif tdi_value <= self.SOFT_BUY:
            return "SOFT_BUY"
        elif tdi_value < self.CENTER_LINE:
            return "BUY_ZONE"
        elif tdi_value < self.SOFT_SELL:
            return "NO_TRADE"
        elif tdi_value < self.OVERBOUGHT:
            return "SOFT_SELL"
        else:
            return "OVERBOUGHT"

    def get_zone_description(self, tdi_value: float) -> str:
        """Get human-readable TDI zone description."""
        zone = self.get_zone(tdi_value)
        descriptions = {
            "OVERSOLD": f"HARD BUY (TDI {tdi_value:.1f} ≤ 25) - 2x risk",
            "SOFT_BUY": f"SOFT BUY (TDI {tdi_value:.1f} ≤ 35) - 1x risk",
            "BUY_ZONE": f"BUY ZONE (TDI {tdi_value:.1f} below 50)",
            "NO_TRADE": f"NO TRADE (TDI {tdi_value:.1f} around 50) - WAIT!",
            "SOFT_SELL": f"SOFT SELL (TDI {tdi_value:.1f} ≥ 65) - 1x risk",
            "OVERBOUGHT": f"HARD SELL (TDI {tdi_value:.1f} ≥ 75) - 2x risk",
        }
        return descriptions.get(zone, f"UNKNOWN (TDI {tdi_value:.1f})")

    def detect_crossovers(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect TDI crossover signals.

        Returns:
            {
                'bullish_cross': bool,   # Green crossed above Red
                'bearish_cross': bool,   # Green crossed below Red
                'green_above_red': bool, # Green currently above Red
                'green_below_red': bool, # Green currently below Red
                'tdi_fast': float,
                'tdi_slow': float,
            }
        """
        if df is None or len(df) < 2:
            return {
                'bullish_cross': False,
                'bearish_cross': False,
                'green_above_red': False,
                'green_below_red': False,
                'tdi_fast': 50.0,
                'tdi_slow': 50.0,
            }

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        fast = last.get('tdi_fast_ma', 50.0)
        slow = last.get('tdi_slow_ma', 50.0)
        fast_prev = prev.get('tdi_fast_ma', 50.0)
        slow_prev = prev.get('tdi_slow_ma', 50.0)

        return {
            'bullish_cross': fast > slow and fast_prev <= slow_prev,
            'bearish_cross': fast < slow and fast_prev >= slow_prev,
            'green_above_red': fast > slow,
            'green_below_red': fast < slow,
            'tdi_fast': fast,
            'tdi_slow': slow,
        }

    def detect_opportunity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect trading opportunities using Super TDI.

        Returns:
            {
                'opportunity': bool,
                'direction': 'BUY' or 'SELL' or 'NONE',
                'tdi_level': float,
                'tdi_zone': str,
                'tdi_zone_description': str,
                'bullish_cross': bool,
                'bearish_cross': bool,
                'confidence': float,
                'signal_strength': 'HARD' or 'SOFT',
                'risk_multiplier': float,
                'reason': str,
                'tdi_fast': float,
                'tdi_slow': float,
            }
        """
        if df is None or df.empty:
            return self._no_opportunity("No data")

        last = df.iloc[-1]

        # Get TDI values
        tdi_slow = last.get('tdi_slow_ma', 50)
        tdi_fast = last.get('tdi_fast_ma', 50)

        # Get zone
        zone = self.get_zone(tdi_slow)
        zone_desc = self.get_zone_description(tdi_slow)

        # Detect crossovers
        crossovers = self.detect_crossovers(df)
        bullish_cross = crossovers.get('bullish_cross', False)
        bearish_cross = crossovers.get('bearish_cross', False)

        # Check for opportunities
        buy_zones = ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE']
        sell_zones = ['SOFT_SELL', 'OVERBOUGHT']

        result = {
            'opportunity': False,
            'direction': 'NONE',
            'tdi_level': tdi_slow,
            'tdi_zone': zone,
            'tdi_zone_description': zone_desc,
            'bullish_cross': bullish_cross,
            'bearish_cross': bearish_cross,
            'tdi_fast': tdi_fast,
            'tdi_slow': tdi_slow,
        }

        # BUY opportunity
        if zone in buy_zones:
            if bullish_cross or tdi_fast > tdi_slow:
                result['opportunity'] = True
                result['direction'] = 'BUY'
                result['confidence'] = 0.7
                result['reason'] = f"BUY: {zone_desc}"

                if zone == 'OVERSOLD':
                    result['signal_strength'] = 'HARD'
                    result['risk_multiplier'] = 2.0
                    result['confidence'] = 0.85
                else:
                    result['signal_strength'] = 'SOFT'
                    result['risk_multiplier'] = 1.0

        # SELL opportunity
        elif zone in sell_zones:
            if bearish_cross or tdi_fast < tdi_slow:
                result['opportunity'] = True
                result['direction'] = 'SELL'
                result['confidence'] = 0.7
                result['reason'] = f"SELL: {zone_desc}"

                if zone == 'OVERBOUGHT':
                    result['signal_strength'] = 'HARD'
                    result['risk_multiplier'] = 2.0
                    result['confidence'] = 0.85
                else:
                    result['signal_strength'] = 'SOFT'
                    result['risk_multiplier'] = 1.0

        else:
            result['reason'] = f"NO TRADE: {zone_desc}"

        return result

    def _no_opportunity(self, reason: str) -> Dict[str, Any]:
        """Return no opportunity result."""
        return {
            'opportunity': False,
            'direction': 'NONE',
            'tdi_level': 50,
            'tdi_zone': 'NO_TRADE',
            'tdi_zone_description': 'No trade zone',
            'bullish_cross': False,
            'bearish_cross': False,
            'tdi_fast': 50,
            'tdi_slow': 50,
            'confidence': 0,
            'signal_strength': 'NONE',
            'risk_multiplier': 1.0,
            'reason': reason,
        }
