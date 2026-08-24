"""
Super Bollinger Bands Detector - Super BB Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

import logging
logger = logging.getLogger(__name__)

class BBDetector:
    """
    Super Bollinger Bands Detector.

    Detects:
    - Price touching upper/lower bands
    - Reversal signals (price moving back inside bands)
    - Candles getting smaller (momentum loss)
    - Band squeezes (low volatility)
    """

    def __init__(self, period: int = 34, deviation: float = 1.750):
        self.period = period
        self.deviation = deviation

    def detect_bb_interaction(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect Bollinger Band interactions.

        Returns:
            {
                'touch_lower': bool,
                'touch_upper': bool,
                'position': float (0-1),
                'inside_band': bool,
                'candles_shrinking': bool,
                'reversal_buy': bool,
                'reversal_sell': bool,
                'bb_width': float,
                'bb_width_ratio': float,
                'squeeze': bool,
            }
        """
        if df is None or len(df) < 10:
            return self._default_result()

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        # Get BB values
        bb_lower = last.get('bb_lower', 0)
        bb_upper = last.get('bb_upper', 0)
        bb_middle = last.get('bb_middle', 0)
        bb_width = last.get('bb_width', 0)

        # Get price values
        close = last.get('close', 0)
        high = last.get('high', 0)
        low = last.get('low', 0)

        # Heikin Ashi values for better reversal detection
        ha_low = last.get('ha_low', low)
        ha_high = last.get('ha_high', high)
        ha_close = last.get('ha_close', close)
        ha_color = last.get('ha_color', 0)

        # Calculate position (0-1)
        if bb_upper > bb_lower:
            position = (close - bb_lower) / (bb_upper - bb_lower)
        else:
            position = 0.5
        position = max(0, min(1, position))

        # Detect touches
        touch_lower = ha_low <= bb_lower if bb_lower > 0 else False
        touch_upper = ha_high >= bb_upper if bb_upper > 0 else False

        # Inside band
        inside_band = bb_lower < close < bb_upper if bb_lower > 0 and bb_upper > 0 else True

        # Candles shrinking (momentum loss)
        last_body = abs(last.get('close', 0) - last.get('open', 0))
        prev_body = abs(prev.get('close', 0) - prev.get('open', 0))
        candles_shrinking = last_body < prev_body * 0.8 if prev_body > 0 else False

        # HA candle shrinking
        ha_last_body = abs(last.get('ha_close', 0) - last.get('ha_open', 0))
        ha_prev_body = abs(prev.get('ha_close', 0) - prev.get('ha_open', 0))
        ha_shrinking = ha_last_body < ha_prev_body * 0.8 if ha_prev_body > 0 else False

        # Reversal detection
        reversal_buy = False
        reversal_sell = False

        # BUY reversal: touch lower band + HA bullish + shrinking candles
        if touch_lower and ha_color == 1:
            reversal_buy = True
        elif touch_lower and close > bb_lower and ha_shrinking:
            reversal_buy = True

        # SELL reversal: touch upper band + HA bearish + shrinking candles
        if touch_upper and ha_color == -1:
            reversal_sell = True
        elif touch_upper and close < bb_upper and ha_shrinking:
            reversal_sell = True

        # Squeeze detection
        bb_width_avg = df['bb_width'].rolling(20).mean().iloc[-1] if len(df) >= 20 else bb_width
        bb_width_ratio = bb_width / bb_width_avg if bb_width_avg > 0 else 1.0
        squeeze = bb_width_ratio < 0.6 and bb_width_ratio > 0

        return {
            'touch_lower': touch_lower,
            'touch_upper': touch_upper,
            'position': position,
            'inside_band': inside_band,
            'candles_shrinking': candles_shrinking or ha_shrinking,
            'reversal_buy': reversal_buy,
            'reversal_sell': reversal_sell,
            'bb_width': bb_width,
            'bb_width_ratio': bb_width_ratio,
            'squeeze': squeeze,
            'ha_color': ha_color,
        }

    def _default_result(self) -> Dict[str, Any]:
        """Return default result."""
        return {
            'touch_lower': False,
            'touch_upper': False,
            'position': 0.5,
            'inside_band': True,
            'candles_shrinking': False,
            'reversal_buy': False,
            'reversal_sell': False,
            'bb_width': 0,
            'bb_width_ratio': 1.0,
            'squeeze': False,
            'ha_color': 0,
        }

    def check_buy_conditions(self, bb_data: Dict[str, Any], tdi_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if all BUY conditions are met."""
        conditions = []

        # 1. TDI in buyer zone
        if tdi_data.get('tdi_zone') in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE']:
            conditions.append("TDI in buyer zone")
        else:
            return False, "TDI not in buyer zone"

        # 2. Green above Red (bullish)
        if tdi_data.get('tdi_fast', 0) > tdi_data.get('tdi_slow', 0):
            conditions.append("Green above Red")
        else:
            return False, "Green not above Red"

        # 3. Touch lower band or near it
        if bb_data.get('touch_lower') or bb_data.get('position') < 0.30:
            conditions.append("Touch lower BB")
        else:
            return False, "Not touching lower BB"

        # 4. Candles shrinking (momentum loss)
        if bb_data.get('candles_shrinking'):
            conditions.append("Candles shrinking")
        else:
            # Accept if HA bullish
            if bb_data.get('ha_color') == 1:
                conditions.append("HA bullish")
            else:
                return False, "No momentum loss signal"

        # 5. Reversal confirmed
        if bb_data.get('reversal_buy'):
            conditions.append("Reversal confirmed")
        else:
            return False, "No reversal confirmed"

        return True, " ✅ ".join(conditions)

    def check_sell_conditions(self, bb_data: Dict[str, Any], tdi_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if all SELL conditions are met."""
        conditions = []

        # 1. TDI in seller zone
        if tdi_data.get('tdi_zone') in ['SOFT_SELL', 'OVERBOUGHT']:
            conditions.append("TDI in seller zone")
        else:
            return False, "TDI not in seller zone"

        # 2. Green below Red (bearish)
        if tdi_data.get('tdi_fast', 0) < tdi_data.get('tdi_slow', 0):
            conditions.append("Green below Red")
        else:
            return False, "Green not below Red"

        # 3. Touch upper band or near it
        if bb_data.get('touch_upper') or bb_data.get('position') > 0.70:
            conditions.append("Touch upper BB")
        else:
            return False, "Not touching upper BB"

        # 4. Candles shrinking (momentum loss)
        if bb_data.get('candles_shrinking'):
            conditions.append("Candles shrinking")
        else:
            # Accept if HA bearish
            if bb_data.get('ha_color') == -1:
                conditions.append("HA bearish")
            else:
                return False, "No momentum loss signal"

        # 5. Reversal confirmed
        if bb_data.get('reversal_sell'):
            conditions.append("Reversal confirmed")
        else:
            return False, "No reversal confirmed"

        return True, " ✅ ".join(conditions)
