"""
Technical Indicators Library - SUPER TDI + SUPER BOLLINGER BANDS STRATEGY
ALIGNED WITH: Super TDI + Super Bollinger Bands + 5-Step Checklist
Version: 3.4.0 - ALIGNED: Added Super TDI + Super BB strategy methods
"""

import pandas as pd
import numpy as np
import logging
import time
from typing import Tuple, Dict, Optional, List, Any
from functools import lru_cache
from scipy.signal import find_peaks
from datetime import datetime

# Local imports
from settings import config, Config

# Configure logging
logger = logging.getLogger(__name__)
indicator_logger = logging.getLogger("indicators")

EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DEBUG": "🔍",
    "CALC": "📊",
    "VALIDATE": "✔️",
    "HEIKIN": "🕯️",
    "TDI": "📈",
    "BB": "📉",
    "LTF": "⏱️",
    "FALLBACK": "🔄",
    "DIVERGENCE": "↩️",
    "PATTERN": "🕯️",
    "S_R": "📊",
    "SUPER_TDI": "📈",
    "SUPER_BB": "📊",
    "CHEAT": "📋",
}

EPSILON = 1e-10


def log_indicator_operation(operation: str, status: str, details: Optional[Dict] = None,
                           emoji: str = "", error: Optional[Exception] = None):
    """Log indicator operations."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {emoji} INDICATOR_{operation}: {status}"
    if details:
        safe_details = {}
        for k, v in details.items():
            if isinstance(v, float):
                safe_details[k] = round(v, 4)
            elif isinstance(v, str) and len(v) > 100:
                safe_details[k] = v[:100] + "..."
            else:
                safe_details[k] = v
        log_message += f" | Details: {safe_details}"
    if error:
        log_message += f" | Error: {str(error)}"
    if status == "FAILURE":
        indicator_logger.error(log_message)
    elif status == "WARNING":
        indicator_logger.warning(log_message)
    else:
        indicator_logger.debug(log_message)


# Updated required columns list for Super TDI + Super BB
REQUIRED_COLUMNS = [
    'open', 'high', 'low', 'close', 'volume',
    'tdi_slow_ma', 'tdi_fast_ma', 'tdi_zone', 'tdi_strength',
    'tdi_bull_cross', 'tdi_bear_cross',
    'bb_middle', 'bb_upper', 'bb_lower', 'bb_width_percent', 'bb_position',
    'ha_color', 'ha_low', 'ha_high', 'ha_close',
    'volume_sma', 'volume_ratio',
    'rsi',
]


def validate_dataframe(df: pd.DataFrame, required_columns: List[str] = None) -> bool:
    """Validate DataFrame structure with extended column checks."""
    if df is None or df.empty:
        return False

    if required_columns is None:
        required_columns = REQUIRED_COLUMNS

    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        critical_cols = ['open', 'high', 'low', 'close', 'tdi_slow_ma', 'tdi_fast_ma']
        critical_missing = [col for col in critical_cols if col in missing_cols]

        if critical_missing:
            indicator_logger.warning(
                f"{EMOJI['WARNING']} VALIDATE: Critical columns missing: {critical_missing}"
            )
            return False

        indicator_logger.debug(
            f"{EMOJI['DEBUG']} VALIDATE: Non-critical columns missing: {missing_cols[:5]}"
        )

    return True


def _add_default_tdi_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add default TDI columns to DataFrame when calculation fails."""
    if df is None:
        return pd.DataFrame()

    df = df.copy()
    default_cols = {
        'tdi_rsi': 50.0,
        'tdi_fast_ma': 50.0,
        'tdi_slow_ma': 50.0,
        'tdi_market_base': 50.0,
        'tdi_bull_count': 0,
        'tdi_bear_count': 0,
        'tdi_zone': 'NEUTRAL',
        'tdi_strength': 0.0,
        'tdi_bull_cross': False,
        'tdi_bear_cross': False,
        'tdi_bb_middle': 50.0,
        'tdi_bb_upper': 60.0,
        'tdi_bb_lower': 40.0,
        'tdi_bb_std': 5.0,
        'tdi_trend': 0.0,
        'tdi_trend_pct': 0.0,
    }

    for col, default_val in default_cols.items():
        if col not in df.columns:
            df[col] = default_val

    indicator_logger.debug(f"{EMOJI['FALLBACK']} Added default TDI columns")
    return df


def _add_default_bb_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add default Bollinger Band columns to DataFrame."""
    if df is None:
        return pd.DataFrame()

    df = df.copy()

    if 'close' in df.columns:
        close_series = df['close']
        df['bb_middle'] = close_series
        df['bb_upper'] = close_series * 1.02
        df['bb_lower'] = close_series * 0.98
        df['bb_width'] = df['bb_upper'] - df['bb_lower']
        df['bb_width_percent'] = 0.04
        df['bb_position'] = 0.5
    else:
        df['bb_middle'] = 1.0
        df['bb_upper'] = 1.02
        df['bb_lower'] = 0.98
        df['bb_width'] = 0.04
        df['bb_width_percent'] = 0.04
        df['bb_position'] = 0.5

    indicator_logger.debug(f"{EMOJI['FALLBACK']} Added default BB columns")
    return df


def _add_default_volume_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add default volume columns to DataFrame."""
    if df is None:
        return pd.DataFrame()

    df = df.copy()
    df['volume_sma'] = 0
    df['volume_ratio'] = 1.0
    df['volume_spike'] = 1.0

    return df


def _add_default_momentum_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add default momentum columns to DataFrame."""
    if df is None:
        return pd.DataFrame()

    df = df.copy()
    df['momentum_5'] = 0.0
    df['momentum_10'] = 0.0
    df['trend_strength'] = 0.0

    return df


# ==================== HEIKIN ASHI ====================

def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Heikin Ashi candles from standard OHLC."""
    if df is None or df.empty:
        return df

    df = df.copy()

    if len(df) < 2:
        df['ha_open'] = df['open']
        df['ha_high'] = df['high']
        df['ha_low'] = df['low']
        df['ha_close'] = df['close']
        df['ha_color'] = 1
        df['ha_body'] = 0.0
        df['ha_upper_wick'] = 0.0
        df['ha_lower_wick'] = 0.0
        df['ha_volume'] = df['volume'] if 'volume' in df.columns else 0
        return df

    # Heikin Ashi formulas
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2

    # Handle first row
    if len(df) > 0:
        df.loc[df.index[0], 'ha_open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2

    # Calculate high and low
    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)

    # Heikin Ashi body and wicks
    df['ha_body'] = abs(df['ha_close'] - df['ha_open'])
    df['ha_upper_wick'] = df['ha_high'] - df[['ha_open', 'ha_close']].max(axis=1)
    df['ha_lower_wick'] = df[['ha_open', 'ha_close']].min(axis=1) - df['ha_low']
    df['ha_color'] = np.where(df['ha_close'] > df['ha_open'], 1, -1)

    # Heikin Ashi volume (adjusted)
    if 'volume' in df.columns:
        close_safe = df['ha_close'].replace(0, EPSILON)
        df['ha_volume'] = df['volume'] * (1 + abs(df['ha_close'] - df['ha_open']) / close_safe)
    else:
        df['ha_volume'] = 0

    indicator_logger.debug(f"{EMOJI['HEIKIN']} INDICATOR_HA: Calculated Heikin Ashi for {len(df)} rows")
    return df


# ==================== NEW: SUPER TDI STRATEGY METHODS ====================

def get_tdi_zone(tdi_value: float) -> str:
    """
    Get standardized TDI zone for Super TDI strategy.

    Zones:
    - OVERSOLD: ≤ 25 (HARD BUY - 2x risk)
    - SOFT_BUY: 25-35 (SOFT BUY - 1x risk)
    - BUY_ZONE: 35-50 (Getting oversold)
    - NO_TRADE: 50-65 (Center line - WAIT!)
    - SOFT_SELL: 65-75 (SOFT SELL - 1x risk)
    - OVERBOUGHT: ≥ 75 (HARD SELL - 2x risk)
    """
    if tdi_value <= 25.0:
        return "OVERSOLD"
    elif tdi_value <= 35.0:
        return "SOFT_BUY"
    elif tdi_value < 50.0:
        return "BUY_ZONE"
    elif tdi_value < 65.0:
        return "NO_TRADE"
    elif tdi_value < 75.0:
        return "SOFT_SELL"
    else:
        return "OVERBOUGHT"


def get_tdi_zone_description(tdi_value: float) -> str:
    """Get human-readable TDI zone description."""
    zone = get_tdi_zone(tdi_value)
    descriptions = {
        "OVERSOLD": f"HARD BUY (TDI {tdi_value:.1f} ≤ 25) - 2x risk",
        "SOFT_BUY": f"SOFT BUY (TDI {tdi_value:.1f} ≤ 35) - 1x risk",
        "BUY_ZONE": f"BUY ZONE (TDI {tdi_value:.1f} below 50)",
        "NO_TRADE": f"NO TRADE (TDI {tdi_value:.1f} around 50) - WAIT!",
        "SOFT_SELL": f"SOFT SELL (TDI {tdi_value:.1f} ≥ 65) - 1x risk",
        "OVERBOUGHT": f"HARD SELL (TDI {tdi_value:.1f} ≥ 75) - 2x risk",
    }
    return descriptions.get(zone, f"UNKNOWN (TDI {tdi_value:.1f})")


def detect_tdi_crossovers(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detect TDI crossover signals for Super TDI strategy.

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


def check_super_tdi_buy_setup(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Check Super TDI BUY setup conditions.

    Returns:
        {
            'valid': bool,
            'tdi_level': float,
            'tdi_zone': str,
            'tdi_zone_description': str,
            'bullish_cross': bool,
            'green_above_red': bool,
            'signal_strength': 'HARD' or 'SOFT',
            'risk_multiplier': float,
            'reason': str,
        }
    """
    if df is None or df.empty:
        return {'valid': False, 'reason': 'No data'}

    last = df.iloc[-1]
    tdi_slow = last.get('tdi_slow_ma', 50.0)
    tdi_fast = last.get('tdi_fast_ma', 50.0)
    tdi_zone = get_tdi_zone(tdi_slow)

    crossovers = detect_tdi_crossovers(df)
    bullish_cross = crossovers.get('bullish_cross', False)
    green_above_red = crossovers.get('green_above_red', False)

    # BUY zones
    buy_zones = ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE']

    if tdi_zone not in buy_zones:
        return {
            'valid': False,
            'tdi_level': tdi_slow,
            'tdi_zone': tdi_zone,
            'tdi_zone_description': get_tdi_zone_description(tdi_slow),
            'bullish_cross': bullish_cross,
            'green_above_red': green_above_red,
            'reason': f'TDI {tdi_slow:.1f} not in buy zone ({tdi_zone})'
        }

    # Need Green above Red (bullish)
    if not green_above_red and not bullish_cross:
        return {
            'valid': False,
            'tdi_level': tdi_slow,
            'tdi_zone': tdi_zone,
            'tdi_zone_description': get_tdi_zone_description(tdi_slow),
            'bullish_cross': bullish_cross,
            'green_above_red': green_above_red,
            'reason': f'Green line not above Red (Fast: {tdi_fast:.1f}, Slow: {tdi_slow:.1f})'
        }

    # Determine signal strength
    if tdi_zone == 'OVERSOLD':
        signal_strength = 'HARD'
        risk_multiplier = 2.0
    else:
        signal_strength = 'SOFT'
        risk_multiplier = 1.0

    return {
        'valid': True,
        'tdi_level': tdi_slow,
        'tdi_zone': tdi_zone,
        'tdi_zone_description': get_tdi_zone_description(tdi_slow),
        'bullish_cross': bullish_cross,
        'green_above_red': green_above_red,
        'signal_strength': signal_strength,
        'risk_multiplier': risk_multiplier,
        'reason': f'BUY setup: {tdi_zone} ({tdi_slow:.1f})'
    }


def check_super_tdi_sell_setup(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Check Super TDI SELL setup conditions.

    Returns:
        {
            'valid': bool,
            'tdi_level': float,
            'tdi_zone': str,
            'tdi_zone_description': str,
            'bearish_cross': bool,
            'green_below_red': bool,
            'signal_strength': 'HARD' or 'SOFT',
            'risk_multiplier': float,
            'reason': str,
        }
    """
    if df is None or df.empty:
        return {'valid': False, 'reason': 'No data'}

    last = df.iloc[-1]
    tdi_slow = last.get('tdi_slow_ma', 50.0)
    tdi_fast = last.get('tdi_fast_ma', 50.0)
    tdi_zone = get_tdi_zone(tdi_slow)

    crossovers = detect_tdi_crossovers(df)
    bearish_cross = crossovers.get('bearish_cross', False)
    green_below_red = crossovers.get('green_below_red', False)

    # SELL zones
    sell_zones = ['SOFT_SELL', 'OVERBOUGHT']

    if tdi_zone not in sell_zones:
        return {
            'valid': False,
            'tdi_level': tdi_slow,
            'tdi_zone': tdi_zone,
            'tdi_zone_description': get_tdi_zone_description(tdi_slow),
            'bearish_cross': bearish_cross,
            'green_below_red': green_below_red,
            'reason': f'TDI {tdi_slow:.1f} not in sell zone ({tdi_zone})'
        }

    # Need Green below Red (bearish)
    if not green_below_red and not bearish_cross:
        return {
            'valid': False,
            'tdi_level': tdi_slow,
            'tdi_zone': tdi_zone,
            'tdi_zone_description': get_tdi_zone_description(tdi_slow),
            'bearish_cross': bearish_cross,
            'green_below_red': green_below_red,
            'reason': f'Green line not below Red (Fast: {tdi_fast:.1f}, Slow: {tdi_slow:.1f})'
        }

    # Determine signal strength
    if tdi_zone == 'OVERBOUGHT':
        signal_strength = 'HARD'
        risk_multiplier = 2.0
    else:
        signal_strength = 'SOFT'
        risk_multiplier = 1.0

    return {
        'valid': True,
        'tdi_level': tdi_slow,
        'tdi_zone': tdi_zone,
        'tdi_zone_description': get_tdi_zone_description(tdi_slow),
        'bearish_cross': bearish_cross,
        'green_below_red': green_below_red,
        'signal_strength': signal_strength,
        'risk_multiplier': risk_multiplier,
        'reason': f'SELL setup: {tdi_zone} ({tdi_slow:.1f})'
    }


# ==================== NEW: SUPER BOLLINGER BANDS STRATEGY METHODS ====================

def check_super_bb_buy_setup(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Check Super Bollinger Bands BUY setup conditions.

    Returns:
        {
            'valid': bool,
            'touch_lower': bool,
            'bb_position': float,
            'inside_band': bool,
            'candles_shrinking': bool,
            'ha_color': int,
            'reversal_buy': bool,
            'reason': str,
        }
    """
    if df is None or len(df) < 10:
        return {'valid': False, 'reason': 'No data'}

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # Get BB values
    bb_lower = last.get('bb_lower', 0)
    bb_upper = last.get('bb_upper', 0)

    # Get price values
    close = last.get('close', 0)

    # Get HA values
    ha_low = last.get('ha_low', 0)
    ha_high = last.get('ha_high', 0)
    ha_close = last.get('ha_close', close)
    ha_color = last.get('ha_color', 0)

    # Calculate position (0-1)
    if bb_upper > bb_lower:
        bb_position = (close - bb_lower) / (bb_upper - bb_lower)
    else:
        bb_position = 0.5
    bb_position = max(0, min(1, bb_position))

    # Touch lower band
    touch_lower = ha_low <= bb_lower if bb_lower > 0 else False

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

    # Reversal confirmation: touch lower + HA bullish + moving inside
    reversal_buy = False
    if touch_lower and ha_color == 1:
        reversal_buy = True
    elif touch_lower and close > bb_lower and (ha_shrinking or candles_shrinking):
        reversal_buy = True

    # Check if setup is valid
    conditions = []
    if touch_lower or bb_position < 0.30:
        conditions.append('Touch lower BB')
    else:
        return {'valid': False, 'reason': 'Not touching lower BB', 'touch_lower': touch_lower, 'bb_position': bb_position}

    if ha_color == 1:
        conditions.append('HA bullish')

    if candles_shrinking or ha_shrinking:
        conditions.append('Candles shrinking')

    if reversal_buy:
        conditions.append('Reversal confirmed')
    else:
        return {'valid': False, 'reason': 'No reversal confirmed', 'touch_lower': touch_lower, 'bb_position': bb_position}

    return {
        'valid': True,
        'touch_lower': touch_lower,
        'bb_position': bb_position,
        'inside_band': inside_band,
        'candles_shrinking': candles_shrinking or ha_shrinking,
        'ha_color': ha_color,
        'reversal_buy': reversal_buy,
        'reason': ' ✅ '.join(conditions)
    }


def check_super_bb_sell_setup(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Check Super Bollinger Bands SELL setup conditions.

    Returns:
        {
            'valid': bool,
            'touch_upper': bool,
            'bb_position': float,
            'inside_band': bool,
            'candles_shrinking': bool,
            'ha_color': int,
            'reversal_sell': bool,
            'reason': str,
        }
    """
    if df is None or len(df) < 10:
        return {'valid': False, 'reason': 'No data'}

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # Get BB values
    bb_lower = last.get('bb_lower', 0)
    bb_upper = last.get('bb_upper', 0)

    # Get price values
    close = last.get('close', 0)

    # Get HA values
    ha_low = last.get('ha_low', 0)
    ha_high = last.get('ha_high', 0)
    ha_close = last.get('ha_close', close)
    ha_color = last.get('ha_color', 0)

    # Calculate position (0-1)
    if bb_upper > bb_lower:
        bb_position = (close - bb_lower) / (bb_upper - bb_lower)
    else:
        bb_position = 0.5
    bb_position = max(0, min(1, bb_position))

    # Touch upper band
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

    # Reversal confirmation: touch upper + HA bearish + moving inside
    reversal_sell = False
    if touch_upper and ha_color == -1:
        reversal_sell = True
    elif touch_upper and close < bb_upper and (ha_shrinking or candles_shrinking):
        reversal_sell = True

    # Check if setup is valid
    conditions = []
    if touch_upper or bb_position > 0.70:
        conditions.append('Touch upper BB')
    else:
        return {'valid': False, 'reason': 'Not touching upper BB', 'touch_upper': touch_upper, 'bb_position': bb_position}

    if ha_color == -1:
        conditions.append('HA bearish')

    if candles_shrinking or ha_shrinking:
        conditions.append('Candles shrinking')

    if reversal_sell:
        conditions.append('Reversal confirmed')
    else:
        return {'valid': False, 'reason': 'No reversal confirmed', 'touch_upper': touch_upper, 'bb_position': bb_position}

    return {
        'valid': True,
        'touch_upper': touch_upper,
        'bb_position': bb_position,
        'inside_band': inside_band,
        'candles_shrinking': candles_shrinking or ha_shrinking,
        'ha_color': ha_color,
        'reversal_sell': reversal_sell,
        'reason': ' ✅ '.join(conditions)
    }


# ==================== NEW: COMPLETE STRATEGY CHECK ====================

def check_super_strategy_buy(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Complete Super TDI + Super BB BUY strategy check.

    Checks all 5 conditions:
    1. TDI in buyer zone
    2. Green above Red (bullish)
    3. Touch lower Bollinger Band
    4. Candles shrinking (momentum loss)
    5. Reversal confirmed

    Returns:
        {
            'valid': bool,
            'conditions': dict of each condition,
            'conditions_met': int,
            'conditions_total': 5,
            'signal_strength': 'HARD' or 'SOFT',
            'risk_multiplier': float,
            'reason': str,
            'cheat_sheet': str,
        }
    """
    if df is None or df.empty:
        return {'valid': False, 'reason': 'No data', 'conditions_met': 0, 'conditions_total': 5}

    # Get TDI setup
    tdi_buy = check_super_tdi_buy_setup(df)

    # Get BB setup
    bb_buy = check_super_bb_buy_setup(df)

    # Check each condition
    conditions = {
        'condition_1_tdi_zone': tdi_buy.get('valid', False) and tdi_buy.get('tdi_zone') in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE'],
        'condition_2_tdi_cross': tdi_buy.get('green_above_red', False) or tdi_buy.get('bullish_cross', False),
        'condition_3_bb_touch': bb_buy.get('touch_lower', False) or bb_buy.get('bb_position', 0.5) < 0.30,
        'condition_4_candles_shrinking': bb_buy.get('candles_shrinking', False),
        'condition_5_reversal_confirm': bb_buy.get('reversal_buy', False),
    }

    conditions_met = sum(1 for v in conditions.values() if v)
    conditions_total = 5

    # Determine if valid (need at least 4 conditions for strong signal, 3 for soft)
    valid = conditions_met >= 3

    # Determine signal strength
    if conditions_met >= 4 and tdi_buy.get('tdi_zone') == 'OVERSOLD':
        signal_strength = 'HARD'
        risk_multiplier = 2.0
    elif conditions_met >= 3:
        signal_strength = 'SOFT'
        risk_multiplier = 1.0
    else:
        signal_strength = 'WEAK'
        risk_multiplier = 0.5

    # Build reason
    reason_parts = []
    if conditions['condition_1_tdi_zone']:
        reason_parts.append(f"TDI in {tdi_buy.get('tdi_zone', 'UNKNOWN')} zone ({tdi_buy.get('tdi_level', 50):.1f})")
    if conditions['condition_2_tdi_cross']:
        reason_parts.append("Green above Red")
    if conditions['condition_3_bb_touch']:
        reason_parts.append("Touch lower BB")
    if conditions['condition_4_candles_shrinking']:
        reason_parts.append("Candles shrinking")
    if conditions['condition_5_reversal_confirm']:
        reason_parts.append("Reversal confirmed")

    reason = f"{conditions_met}/{conditions_total} conditions met: " + " | ".join(reason_parts)

    # Build cheat sheet
    cheat_sheet = f"""
✅ BUY SIGNAL - {df.get('symbol', 'UNKNOWN') if hasattr(df, 'get') else 'UNKNOWN'}
📋 Cheat Sheet:

1. TDI says: "{tdi_buy.get('tdi_zone_description', 'UNKNOWN')}" ✅
2. Green line is {'ABOVE' if conditions['condition_2_tdi_cross'] else 'NOT'} Red line ✅
3. Price {'touched' if conditions['condition_3_bb_touch'] else 'near'} the LOWER Bollinger Band ✅
4. Candles are {'getting SMALLER' if conditions['condition_4_candles_shrinking'] else 'showing reversal signs'} ✅
5. Price {'started moving BACK inside' if conditions['condition_5_reversal_confirm'] else 'showing reversal signs'} the band ✅

✅ ALL 5 HAPPEN = ENTER BUY TRADE
"""

    return {
        'valid': valid,
        'conditions': conditions,
        'conditions_met': conditions_met,
        'conditions_total': conditions_total,
        'signal_strength': signal_strength,
        'risk_multiplier': risk_multiplier,
        'tdi_level': tdi_buy.get('tdi_level', 50),
        'tdi_zone': tdi_buy.get('tdi_zone', 'UNKNOWN'),
        'bb_position': bb_buy.get('bb_position', 0.5),
        'touch_lower': bb_buy.get('touch_lower', False),
        'candles_shrinking': bb_buy.get('candles_shrinking', False),
        'reversal_confirm': bb_buy.get('reversal_buy', False),
        'reason': reason,
        'cheat_sheet': cheat_sheet,
    }


def check_super_strategy_sell(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Complete Super TDI + Super BB SELL strategy check.

    Checks all 5 conditions:
    1. TDI in seller zone
    2. Green below Red (bearish)
    3. Touch upper Bollinger Band
    4. Candles shrinking (momentum loss)
    5. Reversal confirmed

    Returns:
        {
            'valid': bool,
            'conditions': dict of each condition,
            'conditions_met': int,
            'conditions_total': 5,
            'signal_strength': 'HARD' or 'SOFT',
            'risk_multiplier': float,
            'reason': str,
            'cheat_sheet': str,
        }
    """
    if df is None or df.empty:
        return {'valid': False, 'reason': 'No data', 'conditions_met': 0, 'conditions_total': 5}

    # Get TDI setup
    tdi_sell = check_super_tdi_sell_setup(df)

    # Get BB setup
    bb_sell = check_super_bb_sell_setup(df)

    # Check each condition
    conditions = {
        'condition_1_tdi_zone': tdi_sell.get('valid', False) and tdi_sell.get('tdi_zone') in ['SOFT_SELL', 'OVERBOUGHT'],
        'condition_2_tdi_cross': tdi_sell.get('green_below_red', False) or tdi_sell.get('bearish_cross', False),
        'condition_3_bb_touch': bb_sell.get('touch_upper', False) or bb_sell.get('bb_position', 0.5) > 0.70,
        'condition_4_candles_shrinking': bb_sell.get('candles_shrinking', False),
        'condition_5_reversal_confirm': bb_sell.get('reversal_sell', False),
    }

    conditions_met = sum(1 for v in conditions.values() if v)
    conditions_total = 5

    # Determine if valid (need at least 4 conditions for strong signal, 3 for soft)
    valid = conditions_met >= 3

    # Determine signal strength
    if conditions_met >= 4 and tdi_sell.get('tdi_zone') == 'OVERBOUGHT':
        signal_strength = 'HARD'
        risk_multiplier = 2.0
    elif conditions_met >= 3:
        signal_strength = 'SOFT'
        risk_multiplier = 1.0
    else:
        signal_strength = 'WEAK'
        risk_multiplier = 0.5

    # Build reason
    reason_parts = []
    if conditions['condition_1_tdi_zone']:
        reason_parts.append(f"TDI in {tdi_sell.get('tdi_zone', 'UNKNOWN')} zone ({tdi_sell.get('tdi_level', 50):.1f})")
    if conditions['condition_2_tdi_cross']:
        reason_parts.append("Green below Red")
    if conditions['condition_3_bb_touch']:
        reason_parts.append("Touch upper BB")
    if conditions['condition_4_candles_shrinking']:
        reason_parts.append("Candles shrinking")
    if conditions['condition_5_reversal_confirm']:
        reason_parts.append("Reversal confirmed")

    reason = f"{conditions_met}/{conditions_total} conditions met: " + " | ".join(reason_parts)

    # Build cheat sheet
    cheat_sheet = f"""
🔴 SELL SIGNAL - {df.get('symbol', 'UNKNOWN') if hasattr(df, 'get') else 'UNKNOWN'}
📋 Cheat Sheet:

1. TDI says: "{tdi_sell.get('tdi_zone_description', 'UNKNOWN')}" ✅
2. Green line is {'BELOW' if conditions['condition_2_tdi_cross'] else 'NOT'} Red line ✅
3. Price {'touched' if conditions['condition_3_bb_touch'] else 'near'} the UPPER Bollinger Band ✅
4. Candles are {'getting SMALLER' if conditions['condition_4_candles_shrinking'] else 'showing reversal signs'} ✅
5. Price {'started moving BACK inside' if conditions['condition_5_reversal_confirm'] else 'showing reversal signs'} the band ✅

✅ ALL 5 HAPPEN = ENTER SELL TRADE
"""

    return {
        'valid': valid,
        'conditions': conditions,
        'conditions_met': conditions_met,
        'conditions_total': conditions_total,
        'signal_strength': signal_strength,
        'risk_multiplier': risk_multiplier,
        'tdi_level': tdi_sell.get('tdi_level', 50),
        'tdi_zone': tdi_sell.get('tdi_zone', 'UNKNOWN'),
        'bb_position': bb_sell.get('bb_position', 0.5),
        'touch_upper': bb_sell.get('touch_upper', False),
        'candles_shrinking': bb_sell.get('candles_shrinking', False),
        'reversal_confirm': bb_sell.get('reversal_sell', False),
        'reason': reason,
        'cheat_sheet': cheat_sheet,
    }


# ==================== NEW: DIVERGENCE DETECTION ====================

def detect_divergence(df: pd.DataFrame, lookback: int = 20,
                      price_col: str = 'close',
                      indicator_col: str = 'tdi_slow_ma') -> Dict[str, Any]:
    """
    Detect bullish and bearish divergence between price and TDI.

    Bullish Divergence: Price makes lower low, TDI makes higher low
    Bearish Divergence: Price makes higher high, TDI makes lower high

    Returns:
        {
            'bullish': bool,
            'bearish': bool,
            'strength': float (0-1),
            'bullish_strength': float,
            'bearish_strength': float,
            'price_swings': list,
            'indicator_swings': list
        }
    """
    if df is None or len(df) < lookback:
        return {
            'bullish': False,
            'bearish': False,
            'strength': 0.0,
            'bullish_strength': 0.0,
            'bearish_strength': 0.0,
            'price_swings': [],
            'indicator_swings': []
        }

    try:
        # Get recent data
        recent_df = df.iloc[-lookback:].copy()
        prices = recent_df[price_col].values
        indicator = recent_df[indicator_col].values

        # Find swing points using scipy.signal.find_peaks
        # Price peaks (highs)
        price_peaks_idx, _ = find_peaks(prices, distance=3, prominence=0.001)
        price_troughs_idx, _ = find_peaks(-prices, distance=3, prominence=0.001)

        # Indicator peaks (highs)
        indicator_peaks_idx, _ = find_peaks(indicator, distance=3, prominence=0.5)
        indicator_troughs_idx, _ = find_peaks(-indicator, distance=3, prominence=0.5)

        # Extract values
        price_peaks = [(idx, prices[idx]) for idx in price_peaks_idx]
        price_troughs = [(idx, prices[idx]) for idx in price_troughs_idx]
        indicator_peaks = [(idx, indicator[idx]) for idx in indicator_peaks_idx]
        indicator_troughs = [(idx, indicator[idx]) for idx in indicator_troughs_idx]

        bullish_divergence = False
        bearish_divergence = False
        bullish_strength = 0.0
        bearish_strength = 0.0

        # Check bullish divergence (price lower low, indicator higher low)
        if len(price_troughs) >= 2 and len(indicator_troughs) >= 2:
            # Get last two troughs
            p1_idx, p1_val = price_troughs[-2]
            p2_idx, p2_val = price_troughs[-1]

            # Find corresponding indicator troughs near these price troughs
            i1_val = None
            i2_val = None

            for i_idx, i_val in indicator_troughs:
                if abs(i_idx - p1_idx) <= 2:
                    i1_val = i_val
                if abs(i_idx - p2_idx) <= 2:
                    i2_val = i_val

            if i1_val is not None and i2_val is not None:
                # Price lower low, indicator higher low = bullish divergence
                if p2_val < p1_val and i2_val > i1_val:
                    bullish_divergence = True
                    # Calculate strength based on magnitude
                    price_diff_pct = abs((p2_val - p1_val) / p1_val) * 100 if p1_val != 0 else 0
                    indicator_diff_pct = abs((i2_val - i1_val) / i1_val) * 100 if i1_val != 0 else 0
                    bullish_strength = min(1.0, (price_diff_pct + indicator_diff_pct) / 20)

        # Check bearish divergence (price higher high, indicator lower high)
        if len(price_peaks) >= 2 and len(indicator_peaks) >= 2:
            # Get last two peaks
            p1_idx, p1_val = price_peaks[-2]
            p2_idx, p2_val = price_peaks[-1]

            # Find corresponding indicator peaks near these price peaks
            i1_val = None
            i2_val = None

            for i_idx, i_val in indicator_peaks:
                if abs(i_idx - p1_idx) <= 2:
                    i1_val = i_val
                if abs(i_idx - p2_idx) <= 2:
                    i2_val = i_val

            if i1_val is not None and i2_val is not None:
                # Price higher high, indicator lower high = bearish divergence
                if p2_val > p1_val and i2_val < i1_val:
                    bearish_divergence = True
                    # Calculate strength based on magnitude
                    price_diff_pct = abs((p2_val - p1_val) / p1_val) * 100 if p1_val != 0 else 0
                    indicator_diff_pct = abs((i2_val - i1_val) / i1_val) * 100 if i1_val != 0 else 0
                    bearish_strength = min(1.0, (price_diff_pct + indicator_diff_pct) / 20)

        # Overall strength
        strength = max(bullish_strength, bearish_strength)

        return {
            'bullish': bullish_divergence,
            'bearish': bearish_divergence,
            'strength': strength,
            'bullish_strength': bullish_strength,
            'bearish_strength': bearish_strength,
            'price_swings': {
                'peaks': price_peaks,
                'troughs': price_troughs
            },
            'indicator_swings': {
                'peaks': indicator_peaks,
                'troughs': indicator_troughs
            },
            'recent_price': prices[-1] if len(prices) > 0 else 0,
            'recent_indicator': indicator[-1] if len(indicator) > 0 else 50
        }

    except Exception as e:
        indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_DIVERGENCE: {e}")
        return {
            'bullish': False,
            'bearish': False,
            'strength': 0.0,
            'bullish_strength': 0.0,
            'bearish_strength': 0.0,
            'price_swings': [],
            'indicator_swings': []
        }


# ==================== NEW: CANDLE PATTERN DETECTION ====================

def detect_candle_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detect common candlestick patterns.

    Returns:
        {
            'doji': bool,
            'bullish_engulfing': bool,
            'bearish_engulfing': bool,
            'hammer': bool,
            'shooting_star': bool,
            'morning_star': bool,
            'evening_star': bool,
            'pattern_name': str,
            'pattern_direction': str (BUY/SELL/NONE),
            'confidence': float (0-1)
        }
    """
    if df is None or len(df) < 5:
        return {
            'doji': False,
            'bullish_engulfing': False,
            'bearish_engulfing': False,
            'hammer': False,
            'shooting_star': False,
            'morning_star': False,
            'evening_star': False,
            'pattern_name': 'NONE',
            'pattern_direction': 'NONE',
            'confidence': 0.0
        }

    try:
        # Get last 5 candles for pattern detection
        recent = df.iloc[-5:].copy()

        # Calculate candle properties
        recent['body'] = abs(recent['close'] - recent['open'])
        recent['upper_wick'] = recent['high'] - recent[['close', 'open']].max(axis=1)
        recent['lower_wick'] = recent[['close', 'open']].min(axis=1) - recent['low']
        recent['range'] = recent['high'] - recent['low']
        recent['body_pct'] = recent['body'] / recent['range'].replace(0, EPSILON)
        recent['color'] = np.where(recent['close'] > recent['open'], 1, -1)

        # Last candle
        last = recent.iloc[-1]
        prev = recent.iloc[-2]
        prev2 = recent.iloc[-3]

        results = {
            'doji': False,
            'bullish_engulfing': False,
            'bearish_engulfing': False,
            'hammer': False,
            'shooting_star': False,
            'morning_star': False,
            'evening_star': False,
            'pattern_name': 'NONE',
            'pattern_direction': 'NONE',
            'confidence': 0.0
        }

        # ===== DOJI =====
        # Body < 10% of range, long wicks
        if last['body_pct'] < 0.10 and last['upper_wick'] > last['body'] * 2 and last['lower_wick'] > last['body'] * 2:
            results['doji'] = True
            results['pattern_name'] = 'DOJI'
            results['pattern_direction'] = 'NONE'
            results['confidence'] = 0.6

        # ===== BULLISH ENGULFING =====
        # Previous candle is bearish, current candle is bullish and engulfs previous
        if (prev['color'] == -1 and last['color'] == 1 and
            last['close'] > prev['open'] and last['open'] < prev['close']):
            results['bullish_engulfing'] = True
            results['pattern_name'] = 'BULLISH_ENGULFING'
            results['pattern_direction'] = 'BUY'
            # Stronger if volume confirms
            vol_ratio = df['volume_ratio'].iloc[-1] if 'volume_ratio' in df.columns else 1.0
            results['confidence'] = min(0.85, 0.65 + (vol_ratio - 1.0) * 0.1)

        # ===== BEARISH ENGULFING =====
        # Previous candle is bullish, current candle is bearish and engulfs previous
        if (prev['color'] == 1 and last['color'] == -1 and
            last['close'] < prev['open'] and last['open'] > prev['close']):
            results['bearish_engulfing'] = True
            results['pattern_name'] = 'BEARISH_ENGULFING'
            results['pattern_direction'] = 'SELL'
            vol_ratio = df['volume_ratio'].iloc[-1] if 'volume_ratio' in df.columns else 1.0
            results['confidence'] = min(0.85, 0.65 + (vol_ratio - 1.0) * 0.1)

        # ===== HAMMER =====
        # Small body, long lower wick (>= 2x body), short/zero upper wick
        # Should appear after downtrend
        if (last['body_pct'] < 0.30 and
            last['lower_wick'] >= last['body'] * 2 and
            last['upper_wick'] < last['body'] * 0.5):
            results['hammer'] = True
            # Check if in downtrend (previous 3 candles bearish)
            recent_colors = recent['color'].tail(4).tolist()
            if sum(1 for c in recent_colors if c == -1) >= 2:
                results['pattern_name'] = 'HAMMER'
                results['pattern_direction'] = 'BUY'
                results['confidence'] = 0.7

        # ===== SHOOTING STAR =====
        # Small body, long upper wick (>= 2x body), short/zero lower wick
        # Should appear after uptrend
        if (last['body_pct'] < 0.30 and
            last['upper_wick'] >= last['body'] * 2 and
            last['lower_wick'] < last['body'] * 0.5):
            results['shooting_star'] = True
            recent_colors = recent['color'].tail(4).tolist()
            if sum(1 for c in recent_colors if c == 1) >= 2:
                results['pattern_name'] = 'SHOOTING_STAR'
                results['pattern_direction'] = 'SELL'
                results['confidence'] = 0.7

        # ===== MORNING STAR =====
        # Three candles: bearish (long), doji/small (indecision), bullish (long)
        if len(recent) >= 3:
            if (recent.iloc[-3]['color'] == -1 and  # First candle bearish
                recent.iloc[-2]['body_pct'] < 0.15 and  # Second candle small/doji
                recent.iloc[-1]['color'] == 1 and  # Third candle bullish
                recent.iloc[-1]['close'] > (recent.iloc[-3]['open'] + recent.iloc[-3]['close']) / 2):
                results['morning_star'] = True
                results['pattern_name'] = 'MORNING_STAR'
                results['pattern_direction'] = 'BUY'
                results['confidence'] = 0.75

        # ===== EVENING STAR =====
        # Three candles: bullish (long), doji/small (indecision), bearish (long)
        if len(recent) >= 3:
            if (recent.iloc[-3]['color'] == 1 and  # First candle bullish
                recent.iloc[-2]['body_pct'] < 0.15 and  # Second candle small/doji
                recent.iloc[-1]['color'] == -1 and  # Third candle bearish
                recent.iloc[-1]['close'] < (recent.iloc[-3]['open'] + recent.iloc[-3]['close']) / 2):
                results['evening_star'] = True
                results['pattern_name'] = 'EVENING_STAR'
                results['pattern_direction'] = 'SELL'
                results['confidence'] = 0.75

        return results

    except Exception as e:
        indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_PATTERNS: {e}")
        return {
            'doji': False,
            'bullish_engulfing': False,
            'bearish_engulfing': False,
            'hammer': False,
            'shooting_star': False,
            'morning_star': False,
            'evening_star': False,
            'pattern_name': 'NONE',
            'pattern_direction': 'NONE',
            'confidence': 0.0
        }


# ==================== SUPPORT/RESISTANCE ====================

def calculate_support_resistance(df: pd.DataFrame, lookback: int = 100,
                                 num_levels: int = 3) -> Dict[str, Any]:
    """
    Calculate key support and resistance levels using pivot points.
    """
    if df is None or df.empty:
        return {
            'support_levels': [],
            'resistance_levels': [],
            'nearest_support': 0,
            'nearest_resistance': 0,
            'current_price': 0,
            'position': 'UNKNOWN',
            'distance_to_support_pct': 0,
            'distance_to_resistance_pct': 0,
        }

    try:
        recent_df = df.iloc[-lookback:].copy()
        highs = recent_df['high'].values
        lows = recent_df['low'].values
        current_price = recent_df['close'].iloc[-1]

        # Find pivot highs (resistance)
        pivot_highs = []
        for i in range(2, len(highs) - 2):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                pivot_highs.append(highs[i])

        # Find pivot lows (support)
        pivot_lows = []
        for i in range(2, len(lows) - 2):
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                pivot_lows.append(lows[i])

        # If no pivots found, use MIN/MAX
        if not pivot_lows and not pivot_highs:
            support_levels = [recent_df['low'].min()]
            resistance_levels = [recent_df['high'].max()]
            nearest_support = recent_df['low'].min()
            nearest_resistance = recent_df['high'].max()

            if nearest_resistance > 0 and current_price > nearest_resistance:
                position = 'ABOVE_RESISTANCE'
            elif nearest_support > 0 and current_price < nearest_support:
                position = 'BELOW_SUPPORT'
            else:
                position = 'IN_RANGE'

            return {
                'support_levels': support_levels[:num_levels],
                'resistance_levels': resistance_levels[:num_levels],
                'nearest_support': nearest_support,
                'nearest_resistance': nearest_resistance,
                'current_price': current_price,
                'position': position,
                'distance_to_support_pct': ((current_price - nearest_support) / current_price * 100) if nearest_support > 0 and current_price > 0 else 0,
                'distance_to_resistance_pct': ((nearest_resistance - current_price) / current_price * 100) if nearest_resistance > 0 and current_price > 0 else 0,
            }

        # Cluster levels
        def cluster_levels(values, tolerance=0.002):
            if not values:
                return []
            values = sorted(values)
            clusters = []
            current_cluster = [values[0]]
            for val in values[1:]:
                if abs(val - current_cluster[-1]) / max(1, current_cluster[-1]) < tolerance:
                    current_cluster.append(val)
                else:
                    clusters.append(np.mean(current_cluster))
                    current_cluster = [val]
            if current_cluster:
                clusters.append(np.mean(current_cluster))
            return clusters

        support_levels = cluster_levels(pivot_lows)
        resistance_levels = cluster_levels(pivot_highs)

        support_levels = sorted(support_levels, reverse=True)
        resistance_levels = sorted(resistance_levels)

        nearest_support = 0
        nearest_resistance = 0

        for level in support_levels:
            if level < current_price:
                nearest_support = level
                break

        for level in resistance_levels:
            if level > current_price:
                nearest_resistance = level
                break

        # If still no levels, use MIN/MAX
        if nearest_support == 0:
            nearest_support = recent_df['low'].min()
        if nearest_resistance == 0:
            nearest_resistance = recent_df['high'].max()

        if nearest_resistance > 0 and current_price > nearest_resistance:
            position = 'ABOVE_RESISTANCE'
        elif nearest_support > 0 and current_price < nearest_support:
            position = 'BELOW_SUPPORT'
        else:
            position = 'IN_RANGE'

        return {
            'support_levels': support_levels[:num_levels],
            'resistance_levels': resistance_levels[:num_levels],
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'current_price': current_price,
            'position': position,
            'distance_to_support_pct': ((current_price - nearest_support) / current_price * 100) if nearest_support > 0 and current_price > 0 else 0,
            'distance_to_resistance_pct': ((nearest_resistance - current_price) / current_price * 100) if nearest_resistance > 0 and current_price > 0 else 0,
        }

    except Exception as e:
        indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_SR: {e}")
        if not df.empty:
            last_price = df['close'].iloc[-1]
            min_price = df['low'].min()
            max_price = df['high'].max()
            return {
                'support_levels': [min_price],
                'resistance_levels': [max_price],
                'nearest_support': min_price,
                'nearest_resistance': max_price,
                'current_price': last_price,
                'position': 'IN_RANGE',
                'distance_to_support_pct': ((last_price - min_price) / last_price * 100) if last_price > 0 else 0,
                'distance_to_resistance_pct': ((max_price - last_price) / last_price * 100) if last_price > 0 else 0,
            }
        return {
            'support_levels': [],
            'resistance_levels': [],
            'nearest_support': 0,
            'nearest_resistance': 0,
            'current_price': 0,
            'position': 'UNKNOWN',
            'distance_to_support_pct': 0,
            'distance_to_resistance_pct': 0,
        }


# ==================== BB SQUEEZE DETECTION ====================

def detect_bb_squeeze(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    """
    Detect Bollinger Band squeeze (low volatility = upcoming breakout).

    Returns:
        {
            'squeeze': bool,
            'squeeze_strength': float (0-1),
            'bb_width_ratio': float,
            'direction': str (BULLISH/BEARISH/NEUTRAL),
            'confidence': float
        }
    """
    if df is None or len(df) < period + 10:
        return {
            'squeeze': False,
            'squeeze_strength': 0.0,
            'bb_width_ratio': 0.0,
            'direction': 'NEUTRAL',
            'confidence': 0.0
        }

    try:
        # Get BB width
        if 'bb_width' not in df.columns:
            return {
                'squeeze': False,
                'squeeze_strength': 0.0,
                'bb_width_ratio': 0.0,
                'direction': 'NEUTRAL',
                'confidence': 0.0
            }

        recent_df = df.iloc[-period:].copy()
        bb_width = recent_df['bb_width'].values

        if len(bb_width) < period:
            return {
                'squeeze': False,
                'squeeze_strength': 0.0,
                'bb_width_ratio': 0.0,
                'direction': 'NEUTRAL',
                'confidence': 0.0
            }

        # Calculate rolling average of BB width
        width_avg = np.mean(bb_width[:period//2]) if len(bb_width) >= period//2 else np.mean(bb_width)
        current_width = bb_width[-1]

        # Ratio of current width to average
        width_ratio = current_width / width_avg if width_avg > 0 else 1.0

        # Squeeze detected if width is < 60% of average
        is_squeeze = width_ratio < 0.6
        squeeze_strength = min(1.0, (0.6 - width_ratio) / 0.4) if width_ratio < 0.6 else 0.0

        # Determine direction (price position within bands)
        last = df.iloc[-1]
        bb_middle = last.get('bb_middle', 0)
        bb_upper = last.get('bb_upper', 0)
        bb_lower = last.get('bb_lower', 0)
        close = last.get('close', 0)

        if bb_middle > 0:
            bb_position = (close - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
        else:
            bb_position = 0.5

        if is_squeeze:
            if bb_position > 0.7:
                direction = 'BULLISH'
                confidence = 0.6
            elif bb_position < 0.3:
                direction = 'BEARISH'
                confidence = 0.6
            else:
                direction = 'NEUTRAL'
                confidence = 0.4
        else:
            direction = 'NEUTRAL'
            confidence = 0.0

        return {
            'squeeze': is_squeeze,
            'squeeze_strength': squeeze_strength,
            'bb_width_ratio': width_ratio,
            'direction': direction,
            'confidence': confidence,
            'current_width': current_width,
            'average_width': width_avg,
        }

    except Exception as e:
        indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_SQUEEZE: {e}")
        return {
            'squeeze': False,
            'squeeze_strength': 0.0,
            'bb_width_ratio': 0.0,
            'direction': 'NEUTRAL',
            'confidence': 0.0
        }


# ==================== VWAP ====================

def calculate_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Volume Weighted Average Price.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    try:
        if 'volume' not in df.columns or 'close' not in df.columns:
            df['vwap'] = df['close'] if 'close' in df.columns else 0
            return df

        # Calculate VWAP
        df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum().replace(0, EPSILON)
        df['vwap'] = df['vwap'].ffill()

        # VWAP position (0-1 scale)
        close = df['close']
        vwap = df['vwap']
        df['vwap_position'] = (close - vwap) / close.replace(0, EPSILON)
        df['vwap_position'] = df['vwap_position'].clip(-1, 1)
        df['vwap_position_pct'] = df['vwap_position'] * 100

        return df

    except Exception as e:
        indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_VWAP: {e}")
        df['vwap'] = df['close'] if 'close' in df.columns else 0
        df['vwap_position'] = 0
        df['vwap_position_pct'] = 0
        return df


# ==================== SESSION UTILITIES ====================

def get_trading_session(dt: datetime = None) -> str:
    """Get current trading session based on UTC time."""
    if dt is None:
        dt = datetime.utcnow()

    hour = dt.hour

    if 0 <= hour < 8:
        return "ASIAN"
    elif 8 <= hour < 13:
        return "LONDON"
    elif 13 <= hour < 17:
        return "NY"
    else:
        return "LATE"


def get_session_multiplier(session: str) -> float:
    """Get confidence/position multiplier based on session."""
    multipliers = {
        "ASIAN": 0.7,      # Lower confidence in Asian session
        "LONDON": 1.0,     # Normal
        "NY": 1.2,         # Higher confidence during NY session
        "LATE": 0.8,       # Lower confidence late session
    }
    return multipliers.get(session, 1.0)


class Indicators:
    """Technical indicators library with vectorized calculations."""

    # ========== TDI METHODS ==========

    @staticmethod
    def calculate_tdi(df: pd.DataFrame,
                      rsi_period: int = 10,
                      bb_length: int = 20,
                      fast_ma_period: int = 1,
                      slow_ma_period: int = 5) -> pd.DataFrame:
        """Calculate TDI indicators with standardized zones."""
        log_indicator_operation("TDI_CALC", "START", {"rows": len(df) if df is not None else 0}, emoji=EMOJI['CALC'])

        if df is None or df.empty:
            indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_TDI: Empty DataFrame")
            return _add_default_tdi_columns(df) if df is not None else pd.DataFrame()

        try:
            df = df.copy()

            # Check if we have enough data
            min_period = max(rsi_period, bb_length, slow_ma_period)
            if len(df) < min_period:
                indicator_logger.warning(
                    f"{EMOJI['WARNING']} INDICATOR_TDI: Insufficient data "
                    f"(need {min_period}, got {len(df)})"
                )
                return _add_default_tdi_columns(df)

            # Calculate RSI
            df = Indicators.calculate_rsi(df, period=rsi_period)

            # Check if RSI was calculated successfully
            if 'rsi' not in df.columns or df['rsi'].isna().all():
                indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_TDI: RSI calculation failed")
                return _add_default_tdi_columns(df)

            # Calculate Bollinger Bands on RSI
            df['tdi_bb_middle'] = df['rsi'].rolling(bb_length).mean()
            df['tdi_bb_std'] = df['rsi'].rolling(bb_length).std()
            df['tdi_bb_upper'] = df['tdi_bb_middle'] + (2.0 * df['tdi_bb_std'])
            df['tdi_bb_lower'] = df['tdi_bb_middle'] - (2.0 * df['tdi_bb_std'])

            # Fast MA (Bulls) - Green line
            df['tdi_fast_ma'] = df['rsi'].rolling(fast_ma_period).mean()

            # Slow MA (Bears) - Red line
            df['tdi_slow_ma'] = df['rsi'].rolling(slow_ma_period).mean()

            # Check if slow_ma has valid data
            if df['tdi_slow_ma'].isna().all():
                indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_TDI: TDI calculation produced no valid data")
                return _add_default_tdi_columns(df)

            # Calculate TDI zone (standardized)
            df = Indicators._calculate_tdi_metrics(df)

            # Fill NaN values
            df = df.ffill().bfill()

            # Ensure no division by zero
            df = df.replace([np.inf, -np.inf], 0)

            # Final check: ensure tdi_slow_ma column exists
            if 'tdi_slow_ma' not in df.columns:
                df['tdi_slow_ma'] = 50.0
            if 'tdi_fast_ma' not in df.columns:
                df['tdi_fast_ma'] = 50.0
            if 'tdi_zone' not in df.columns:
                df['tdi_zone'] = 'NEUTRAL'

            log_indicator_operation("TDI_CALC", "SUCCESS",
                                   {"last_zone": df['tdi_zone'].iloc[-1] if not df.empty else 'NEUTRAL',
                                    "last_tdi": round(df['tdi_slow_ma'].iloc[-1], 2) if not df.empty else 0},
                                   emoji=EMOJI['SUCCESS'])

            return df

        except IndexError as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_TDI: Index error - {e}")
            return _add_default_tdi_columns(df)

        except Exception as e:
            log_indicator_operation("TDI_CALC", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_TDI: {e}")
            return _add_default_tdi_columns(df)

    @staticmethod
    def _calculate_tdi_metrics(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate TDI metrics with standardized zone names."""
        try:
            # Get TDI levels from config with fallbacks
            hard_buy = getattr(config.strategy, 'tdi_hard_buy_level', 25.0)
            soft_buy = getattr(config.strategy, 'tdi_soft_buy_level', 35.0)
            center_line = getattr(config.strategy, 'tdi_center_line', 50.0)
            soft_sell = getattr(config.strategy, 'tdi_soft_sell_level', 65.0)
            hard_sell = getattr(config.strategy, 'tdi_hard_sell_level', 75.0)
            no_trade_start = getattr(config.strategy, 'tdi_no_trade_start', 50.0)
            no_trade_end = getattr(config.strategy, 'tdi_no_trade_end', 65.0)

            # Initialize zone column
            df['tdi_zone'] = 'NEUTRAL'

            # Create masks for valid data
            valid_slow_ma = df['tdi_slow_ma'].notna() & (df['tdi_slow_ma'] != 0)

            # Standardized zone names
            df.loc[valid_slow_ma & (df['tdi_slow_ma'] <= hard_buy), 'tdi_zone'] = 'OVERSOLD'
            df.loc[valid_slow_ma & (df['tdi_slow_ma'] > hard_buy) & (df['tdi_slow_ma'] <= soft_buy), 'tdi_zone'] = 'SOFT_BUY'
            df.loc[valid_slow_ma & (df['tdi_slow_ma'] > soft_buy) & (df['tdi_slow_ma'] < center_line), 'tdi_zone'] = 'BUY_ZONE'
            df.loc[valid_slow_ma & (df['tdi_slow_ma'] >= no_trade_start) & (df['tdi_slow_ma'] < no_trade_end), 'tdi_zone'] = 'NO_TRADE'
            df.loc[valid_slow_ma & (df['tdi_slow_ma'] >= soft_sell) & (df['tdi_slow_ma'] < hard_sell), 'tdi_zone'] = 'SOFT_SELL'
            df.loc[valid_slow_ma & (df['tdi_slow_ma'] >= hard_sell), 'tdi_zone'] = 'OVERBOUGHT'

            # Calculate TDI strength (0-1 scale)
            df['tdi_strength'] = 0.0
            df.loc[valid_slow_ma, 'tdi_strength'] = abs(df.loc[valid_slow_ma, 'tdi_slow_ma'] - center_line) / center_line
            df['tdi_strength'] = df['tdi_strength'].clip(0, 1)

            # Calculate crossover signals
            if 'tdi_fast_ma' in df.columns and 'tdi_slow_ma' in df.columns:
                df['tdi_bull_cross'] = (df['tdi_fast_ma'] > df['tdi_slow_ma']) & (df['tdi_fast_ma'].shift(1) <= df['tdi_slow_ma'].shift(1))
                df['tdi_bear_cross'] = (df['tdi_fast_ma'] < df['tdi_slow_ma']) & (df['tdi_fast_ma'].shift(1) >= df['tdi_slow_ma'].shift(1))
            else:
                df['tdi_bull_cross'] = False
                df['tdi_bear_cross'] = False

            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_TDI_METRICS: {e}")
            if 'tdi_zone' not in df.columns:
                df['tdi_zone'] = 'NEUTRAL'
            if 'tdi_strength' not in df.columns:
                df['tdi_strength'] = 0.0
            if 'tdi_bull_cross' not in df.columns:
                df['tdi_bull_cross'] = False
            if 'tdi_bear_cross' not in df.columns:
                df['tdi_bear_cross'] = False
            return df

    # ========== RSI METHODS ==========

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = None) -> pd.DataFrame:
        """Calculate RSI."""
        if period is None:
            period = getattr(config.strategy, 'tdi_rsi_period', 10)

        try:
            df = df.copy()
            if 'close' not in df.columns:
                df['rsi'] = np.nan
                return df

            if len(df) < period:
                df['rsi'] = np.nan
                return df

            close = df['close'].ffill().replace(0, EPSILON)
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
            avg_loss = avg_loss.replace(0, EPSILON)
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            df['rsi'] = rsi
            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_RSI: {e}")
            df['rsi'] = np.nan
            return df

    # ========== MOVING AVERAGE METHODS ==========

    @staticmethod
    def calculate_sma(df: pd.DataFrame, column: str, period: int) -> pd.DataFrame:
        """Calculate SMA."""
        col_name = f'{column}_sma_{period}'

        try:
            df = df.copy()
            if len(df) < period:
                df[col_name] = np.nan
                return df

            df[col_name] = df[column].rolling(window=period, min_periods=period).mean()
            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_SMA: {e}")
            df[col_name] = np.nan
            return df

    @staticmethod
    def calculate_ema(df: pd.DataFrame, column: str, period: int) -> pd.DataFrame:
        """Calculate EMA."""
        col_name = f'{column}_ema_{period}'

        try:
            df = df.copy()
            if len(df) < period:
                df[col_name] = np.nan
                return df

            df[col_name] = df[column].ewm(span=period, adjust=False, min_periods=period).mean()
            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_EMA: {e}")
            df[col_name] = np.nan
            return df

    # ========== BOLLINGER BANDS METHODS ==========

    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 34, dev: float = 1.750) -> pd.DataFrame:
        """Calculate Bollinger Bands with position tracking."""
        log_indicator_operation("BB_CALC", "START", {"rows": len(df), "period": period, "dev": dev}, emoji=EMOJI['CALC'])

        try:
            df = df.copy()

            if len(df) < period:
                indicator_logger.warning(
                    f"{EMOJI['WARNING']} INDICATOR_BB: Insufficient data "
                    f"(need {period}, got {len(df)})"
                )
                return _add_default_bb_columns(df)

            # Calculate Bollinger Bands
            df['bb_middle'] = df['close'].rolling(window=period, min_periods=period).mean()
            df['bb_std'] = df['close'].rolling(window=period, min_periods=period).std()
            df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * dev)
            df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * dev)

            # Keep bb_width for dynamic volume threshold
            df['bb_width'] = df['bb_upper'] - df['bb_lower']

            # Calculate BB width percentage (for volatility assessment)
            df['bb_width_percent'] = df['bb_width'] / df['bb_middle'].replace(0, EPSILON)
            df['bb_width_percent'] = df['bb_width_percent'].fillna(0)

            # Calculate BB position (0-1 scale)
            bb_range = df['bb_upper'] - df['bb_lower']
            bb_range = bb_range.replace(0, EPSILON)
            df['bb_position'] = (df['close'] - df['bb_lower']) / bb_range
            df['bb_position'] = df['bb_position'].clip(0, 1)

            # Drop only std (keep width for VolumeNormalizer)
            df = df.drop(columns=['bb_std'], errors='ignore')

            # Fill NaN values
            df = df.ffill().bfill()

            log_indicator_operation("BB_CALC", "SUCCESS",
                                   {"width_pct": round(df['bb_width_percent'].iloc[-1] * 100, 2) if not df.empty else 0,
                                    "position": round(df['bb_position'].iloc[-1], 3) if not df.empty else 0},
                                   emoji=EMOJI['SUCCESS'])
            return df

        except Exception as e:
            log_indicator_operation("BB_CALC", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_BB: {e}", exc_info=True)
            return _add_default_bb_columns(df)

    @staticmethod
    def calculate_super_bollinger_bands(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Super Bollinger Bands."""
        return Indicators.calculate_bollinger_bands(df, period=34, dev=1.750)

    @staticmethod
    def _calculate_atr(df: pd.DataFrame, atr_period: int = 14) -> pd.DataFrame:
        """Calculate ATR."""
        try:
            if not all(col in df.columns for col in ['high', 'low', 'close']):
                df['atr'] = np.nan
                return df

            if len(df) < atr_period:
                df['atr'] = np.nan
                return df

            high = df['high']
            low = df['low']
            close = df['close']

            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))

            df['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(window=atr_period).mean()
            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_ATR: {e}")
            df['atr'] = np.nan
            return df

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate ADX."""
        try:
            df = df.copy()

            required_cols = ['high', 'low', 'close']
            if not all(col in df.columns for col in required_cols):
                df[['adx', 'plus_di', 'minus_di']] = np.nan
                return df

            if len(df) < period:
                df[['adx', 'plus_di', 'minus_di']] = np.nan
                return df

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

            df['plus_di'] = 100 * (df['plus_dm_smooth'] / df['tr_smooth'].replace(0, EPSILON))
            df['minus_di'] = 100 * (df['minus_dm_smooth'] / df['tr_smooth'].replace(0, EPSILON))

            di_sum = df['plus_di'] + df['minus_di']
            di_sum = di_sum.replace(0, EPSILON)
            df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / di_sum)
            df['adx'] = df['dx'].ewm(alpha=1/period, min_periods=period, adjust=False).mean()

            df = df.drop(columns=['tr', 'up_move', 'down_move', 'plus_dm', 'minus_dm',
                                  'tr_smooth', 'plus_dm_smooth', 'minus_dm_smooth', 'dx'], errors='ignore')
            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_ADX: {e}")
            df[['adx', 'plus_di', 'minus_di']] = np.nan
            return df

    # ========== MAIN INDICATOR CALCULATION ==========

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators with new features."""
        log_indicator_operation("ALL", "START", {"rows": len(df) if df is not None else 0}, emoji=EMOJI['CALC'])

        try:
            if not isinstance(df, pd.DataFrame):
                indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_ALL: Input is not a DataFrame")
                return pd.DataFrame()

            if df.empty:
                indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_ALL: Empty DataFrame")
                return df

            df = df.copy()
            df.columns = [col.lower() for col in df.columns]

            # Calculate Heikin Ashi first
            if getattr(config.strategy, 'use_heikin_ashi', True):
                try:
                    df = calculate_heikin_ashi(df)
                except Exception as e:
                    indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_ALL: Heikin Ashi failed: {e}")
                    # Add default HA columns if missing
                    if 'ha_color' not in df.columns:
                        df['ha_color'] = 1
                        df['ha_low'] = df['low'] if 'low' in df.columns else 0
                        df['ha_high'] = df['high'] if 'high' in df.columns else 0
                        df['ha_close'] = df['close'] if 'close' in df.columns else 0
                        df['ha_open'] = df['open'] if 'open' in df.columns else 0

            # Calculate TDI indicators
            try:
                df = Indicators.calculate_tdi(df)
            except Exception as e:
                indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_ALL: TDI calculation failed: {e}")
                df = _add_default_tdi_columns(df)

            # Calculate Bollinger Bands
            try:
                df = Indicators.calculate_bollinger_bands(df, period=34, dev=1.750)
            except Exception as e:
                indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_ALL: BB calculation failed: {e}")
                df = _add_default_bb_columns(df)

            # Calculate volume indicators
            try:
                if 'volume' in df.columns:
                    df['volume_sma'] = df['volume'].rolling(window=20, min_periods=1).mean()
                    df['volume_ratio'] = df['volume'] / df['volume_sma'].replace(0, EPSILON)
                    df['volume_ratio'] = df['volume_ratio'].replace([np.inf, -np.inf], 1).fillna(1)
                else:
                    df = _add_default_volume_columns(df)
            except Exception as e:
                indicator_logger.warning(f"{EMOJI['WARNING']} INDICATOR_ALL: Volume calculation failed: {e}")
                df = _add_default_volume_columns(df)

            # ===== Calculate Divergence =====
            try:
                divergence = detect_divergence(df)
                df['divergence_bullish'] = divergence.get('bullish', False)
                df['divergence_bearish'] = divergence.get('bearish', False)
                df['divergence_strength'] = divergence.get('strength', 0.0)
                df['divergence_bullish_strength'] = divergence.get('bullish_strength', 0.0)
                df['divergence_bearish_strength'] = divergence.get('bearish_strength', 0.0)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: Divergence calculation failed: {e}")
                df['divergence_bullish'] = False
                df['divergence_bearish'] = False
                df['divergence_strength'] = 0.0
                df['divergence_bullish_strength'] = 0.0
                df['divergence_bearish_strength'] = 0.0

            # ===== Calculate Candle Patterns =====
            try:
                patterns = detect_candle_patterns(df)
                df['candle_pattern'] = patterns.get('pattern_name', 'NONE')
                df['candle_pattern_direction'] = patterns.get('pattern_direction', 'NONE')
                df['candle_pattern_confidence'] = patterns.get('confidence', 0.0)
                df['candle_doji'] = patterns.get('doji', False)
                df['candle_engulfing_bullish'] = patterns.get('bullish_engulfing', False)
                df['candle_engulfing_bearish'] = patterns.get('bearish_engulfing', False)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: Pattern detection failed: {e}")
                df['candle_pattern'] = 'NONE'
                df['candle_pattern_direction'] = 'NONE'
                df['candle_pattern_confidence'] = 0.0
                df['candle_doji'] = False
                df['candle_engulfing_bullish'] = False
                df['candle_engulfing_bearish'] = False

            # ===== Calculate Support/Resistance =====
            try:
                sr = calculate_support_resistance(df)
                df['nearest_support'] = sr.get('nearest_support', 0)
                df['nearest_resistance'] = sr.get('nearest_resistance', 0)
                df['sr_position'] = sr.get('position', 'UNKNOWN')
                df['distance_to_support_pct'] = sr.get('distance_to_support_pct', 0)
                df['distance_to_resistance_pct'] = sr.get('distance_to_resistance_pct', 0)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: S/R calculation failed: {e}")
                df['nearest_support'] = 0
                df['nearest_resistance'] = 0
                df['sr_position'] = 'UNKNOWN'
                df['distance_to_support_pct'] = 0
                df['distance_to_resistance_pct'] = 0

            # ===== Calculate BB Squeeze =====
            try:
                squeeze = detect_bb_squeeze(df)
                df['bb_squeeze'] = squeeze.get('squeeze', False)
                df['bb_squeeze_strength'] = squeeze.get('squeeze_strength', 0.0)
                df['bb_squeeze_direction'] = squeeze.get('direction', 'NEUTRAL')
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: BB Squeeze calculation failed: {e}")
                df['bb_squeeze'] = False
                df['bb_squeeze_strength'] = 0.0
                df['bb_squeeze_direction'] = 'NEUTRAL'

            # ===== Calculate VWAP =====
            try:
                df = calculate_vwap(df)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: VWAP calculation failed: {e}")
                df['vwap'] = df['close'] if 'close' in df.columns else 0
                df['vwap_position'] = 0
                df['vwap_position_pct'] = 0

            # Calculate ADX
            try:
                df = Indicators.calculate_adx(df)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: ADX calculation failed: {e}")
                if 'adx' not in df.columns:
                    df['adx'] = np.nan
                if 'plus_di' not in df.columns:
                    df['plus_di'] = np.nan
                if 'minus_di' not in df.columns:
                    df['minus_di'] = np.nan

            # Calculate TDI trend
            try:
                if 'tdi_fast_ma' in df.columns and 'tdi_slow_ma' in df.columns:
                    df['tdi_trend'] = df['tdi_fast_ma'] - df['tdi_slow_ma']
                    df['tdi_trend_pct'] = (df['tdi_trend'] / df['tdi_slow_ma'].replace(0, EPSILON)) * 100
                    df['tdi_trend_pct'] = df['tdi_trend_pct'].replace([np.inf, -np.inf], 0).fillna(0)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: TDI trend calculation failed: {e}")

            # Calculate TDI strength
            try:
                if 'tdi_slow_ma' in df.columns:
                    valid_slow_ma = df['tdi_slow_ma'].replace(0, EPSILON)
                    df['tdi_strength'] = abs(df['tdi_trend']) / valid_slow_ma if 'tdi_trend' in df.columns else 0
                    df['tdi_strength'] = df['tdi_strength'].fillna(0).replace([np.inf, -np.inf], 0)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: TDI strength calculation failed: {e}")

            # Calculate trend strength from ADX
            try:
                if 'adx' in df.columns:
                    df['trend_strength'] = df['adx'] / 50
                    df['trend_strength'] = df['trend_strength'].clip(0, 1)
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: Trend strength calculation failed: {e}")

            # Add Heikin Ashi BB interaction
            try:
                if 'ha_low' in df.columns and 'bb_lower' in df.columns:
                    df['ha_bb_touch_buy'] = df['ha_low'] <= df['bb_lower']
                    df['ha_bb_touch_sell'] = df['ha_high'] >= df['bb_upper']
                    df['ha_bb_rejection_buy'] = (
                        df['ha_bb_touch_buy'] &
                        (df['ha_close'] > df['bb_lower']) &
                        (df['ha_color'] == 1)
                    )
                    df['ha_bb_rejection_sell'] = (
                        df['ha_bb_touch_sell'] &
                        (df['ha_close'] < df['bb_upper']) &
                        (df['ha_color'] == -1)
                    )
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: HA-BB interaction calculation failed: {e}")

            # Add momentum indicators
            try:
                if 'close' in df.columns:
                    df['momentum_5'] = df['close'].pct_change(periods=5) * 100
                    df['momentum_10'] = df['close'].pct_change(periods=10) * 100
                    if 'volume' in df.columns and 'volume_spike' not in df.columns:
                        df['volume_spike'] = df['volume_ratio'] if 'volume_ratio' in df.columns else 1.0
            except Exception as e:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: Momentum calculation failed: {e}")
                df = _add_default_momentum_columns(df)

            # Drop rows with NaN in essential columns
            essential_cols = ['tdi_slow_ma', 'tdi_fast_ma', 'bb_width_percent', 'bb_position']
            existing_cols = [col for col in essential_cols if col in df.columns]
            if existing_cols:
                df = df.dropna(subset=existing_cols, how='any')

            # Fill remaining NaN values
            df = df.ffill().bfill()

            # Log column summary
            available_cols = [c for c in REQUIRED_COLUMNS if c in df.columns]
            missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]

            if missing_cols:
                indicator_logger.debug(f"{EMOJI['DEBUG']} INDICATOR_ALL: Missing columns: {missing_cols[:5]}")

            log_indicator_operation("ALL", "SUCCESS",
                                   {"rows": len(df),
                                    "columns": len(df.columns),
                                    "available": len(available_cols),
                                    "missing": len(missing_cols)},
                                   emoji=EMOJI['SUCCESS'])

            return df

        except Exception as e:
            log_indicator_operation("ALL", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_ALL: {e}", exc_info=True)

            # Ensure required columns exist even on failure
            required_cols = ['tdi_slow_ma', 'tdi_fast_ma', 'tdi_zone', 'tdi_strength',
                           'bb_width_percent', 'bb_position', 'bb_rejection_buy', 'bb_rejection_sell',
                           'volume_sma', 'volume_ratio']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = np.nan
            df['tdi_zone'] = df.get('tdi_zone', 'NEUTRAL')
            return df

    @staticmethod
    def calculate_ltf_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators specifically for LTF (5m) confirmation."""
        if df is None or df.empty:
            return df

        try:
            df = df.copy()

            # Calculate Heikin Ashi for LTF
            df = calculate_heikin_ashi(df)

            # Calculate RSI
            df = Indicators.calculate_rsi(df, period=10)

            # Calculate TDI for LTF
            df = Indicators.calculate_tdi(df, rsi_period=10, bb_length=20, fast_ma_period=1, slow_ma_period=5)

            # Calculate Bollinger Bands for LTF
            df = Indicators.calculate_bollinger_bands(df, period=34, dev=1.750)

            # Calculate fast EMA for momentum
            df = Indicators.calculate_ema(df, 'close', 9)
            df = Indicators.calculate_ema(df, 'close', 21)
            df['ema_momentum'] = df['close_ema_9'] - df['close_ema_21']

            # Calculate volume indicators
            if 'volume' in df.columns:
                df['volume_sma'] = df['volume'].rolling(20).mean()
                df['volume_ratio'] = df['volume'] / df['volume_sma'].replace(0, EPSILON)
                df['volume_ratio'] = df['volume_ratio'].replace([np.inf, -np.inf], 1).fillna(1)

            # Calculate ATR for volatility
            df = Indicators._calculate_atr(df, atr_period=7)

            # Calculate price range
            df['price_range'] = (df['high'] - df['low']) / df['close'].replace(0, EPSILON)
            df['price_range'] = df['price_range'].replace([np.inf, -np.inf], 0).fillna(0)

            # Calculate momentum
            df['momentum'] = df['close'] - df['close'].shift(5)
            df['momentum_pct'] = df['momentum'] / df['close'].shift(5).replace(0, EPSILON) * 100
            df['momentum_pct'] = df['momentum_pct'].replace([np.inf, -np.inf], 0).fillna(0)

            # Clean up - drop rows with NaN in critical columns
            critical_cols = ['rsi', 'tdi_slow_ma', 'tdi_fast_ma', 'bb_position', 'close_ema_9', 'close_ema_21']
            existing_critical = [c for c in critical_cols if c in df.columns]
            if existing_critical:
                df = df.dropna(subset=existing_critical, how='any')

            # Fill remaining NaN values
            df = df.ffill().bfill()

            return df

        except Exception as e:
            indicator_logger.error(f"{EMOJI['ERROR']} INDICATOR_LTF: {e}")
            return df

    @staticmethod
    def get_alert_message_header(signal: str, strength: str, symbol: str) -> Tuple[str, str]:
        """Generate alert message header."""
        signal = signal.upper()
        strength = strength.upper()

        if signal == 'BUY':
            action = "LONG"
            if strength == 'HARD':
                header = f"🎯 **SNIPER BUY SIGNAL** | LONG *{symbol}* 🟢"
            elif strength == 'SOFT':
                header = f"🟢 Soft Buy Signal | LONG *{symbol}* 📊"
            elif strength == 'WEAK':
                header = f"💡 Weak Buy Signal | LONG *{symbol}* 📈"
            else:
                header = f"🟢 BUY Signal | LONG *{symbol}* 📈"

        elif signal == 'SELL':
            action = "SHORT"
            if strength == 'HARD':
                header = f"🎯 **SNIPER SELL SIGNAL** | SHORT *{symbol}* 🔴"
            elif strength == 'SOFT':
                header = f"🔴 Soft Sell Signal | SHORT *{symbol}* 📉"
            elif strength == 'WEAK':
                header = f"💡 Weak Sell Signal | SHORT *{symbol}* 📉"
            else:
                header = f"🔴 SELL Signal | SHORT *{symbol}* 📉"
        else:
            header = f"ℹ️ Market State: NO TRADE on *{symbol}*"
            action = "NO_TRADE"

        return header, action


# ==================== DATA VALIDATION HELPER ====================

def get_missing_columns(df: pd.DataFrame) -> List[str]:
    """Get list of required columns missing from DataFrame."""
    if df is None or df.empty:
        return REQUIRED_COLUMNS

    return [col for col in REQUIRED_COLUMNS if col not in df.columns]


# Create singleton instance
indicators = Indicators()

__all__ = [
    "indicators",
    "Indicators",
    "calculate_heikin_ashi",
    "validate_dataframe",
    "get_missing_columns",
    "REQUIRED_COLUMNS",
    "EPSILON",
    "_add_default_tdi_columns",
    "_add_default_bb_columns",
    "_add_default_volume_columns",
    "_add_default_momentum_columns",
    # Super TDI + Super BB Strategy Methods
    "get_tdi_zone",
    "get_tdi_zone_description",
    "detect_tdi_crossovers",
    "check_super_tdi_buy_setup",
    "check_super_tdi_sell_setup",
    "check_super_bb_buy_setup",
    "check_super_bb_sell_setup",
    "check_super_strategy_buy",
    "check_super_strategy_sell",
    # Existing methods
    "detect_divergence",
    "detect_candle_patterns",
    "calculate_support_resistance",
    "detect_bb_squeeze",
    "calculate_vwap",
    "get_trading_session",
    "get_session_multiplier",
]
