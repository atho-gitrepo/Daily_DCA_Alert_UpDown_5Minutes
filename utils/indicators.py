"""
Technical Indicators Library - SUPER TDI + MACD + SUPER BOLLINGER BANDS
MINIMAL VERSION - Only what the strategy needs
Version: 3.4.1
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Any

from settings import config

logger = logging.getLogger(__name__)
indicator_logger = logging.getLogger("indicators")

EPSILON = 1e-10


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
        return df

    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df.loc[df.index[0], 'ha_open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2

    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)
    df['ha_color'] = np.where(df['ha_close'] > df['ha_open'], 1, -1)

    return df


# ==================== RSI ====================

def calculate_rsi(df: pd.DataFrame, period: int = 10) -> pd.DataFrame:
    """Calculate RSI."""
    if df is None or df.empty or len(df) < period:
        df['rsi'] = 50.0
        return df

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean().replace(0, EPSILON)
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['rsi'] = df['rsi'].fillna(50)
    return df


# ==================== TDI (Your Primary Indicator) ====================

def calculate_tdi(df: pd.DataFrame, rsi_period: int = 10,
                  fast_ma_period: int = 1, slow_ma_period: int = 5) -> pd.DataFrame:
    """
    Calculate TDI (RSI with fast and slow MAs).
    This is your PRIMARY indicator - replaces RSI.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Calculate RSI first
    df = calculate_rsi(df, rsi_period)

    if 'rsi' not in df.columns:
        df['rsi'] = 50.0

    # TDI lines
    df['tdi_fast_ma'] = df['rsi'].rolling(fast_ma_period).mean()  # Green line
    df['tdi_slow_ma'] = df['rsi'].rolling(slow_ma_period).mean()  # Red line

    # TDI Zones
    tdi_values = df['tdi_slow_ma'].fillna(50)
    df['tdi_zone'] = tdi_values.apply(get_tdi_zone)
    df['tdi_zone_description'] = tdi_values.apply(get_tdi_zone_description)

    # Crossovers
    df['tdi_bullish_cross'] = (df['tdi_fast_ma'] > df['tdi_slow_ma']) & (df['tdi_fast_ma'].shift(1) <= df['tdi_slow_ma'].shift(1))
    df['tdi_bearish_cross'] = (df['tdi_fast_ma'] < df['tdi_slow_ma']) & (df['tdi_fast_ma'].shift(1) >= df['tdi_slow_ma'].shift(1))

    # Fill NaN
    df = df.ffill().bfill()

    return df


def get_tdi_zone(tdi_value: float) -> str:
    """Get standardized TDI zone."""
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


# ==================== MACD (Your Secondary Confirmation) ====================

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calculate MACD - Your SECONDARY indicator for confirmation.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    try:
        if len(df) < slow:
            return _add_default_macd_columns(df)

        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()

        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # MACD signals
        df['macd_bullish'] = (df['macd'] > df['macd_signal']) & (df['macd_histogram'] > df['macd_histogram'].shift(1))
        df['macd_bearish'] = (df['macd'] < df['macd_signal']) & (df['macd_histogram'] < df['macd_histogram'].shift(1))

        df = df.ffill().bfill()

    except Exception as e:
        indicator_logger.warning(f"MACD calculation failed: {e}")
        df = _add_default_macd_columns(df)

    return df


def _add_default_macd_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add default MACD columns."""
    if df is None:
        return df
    for col in ['macd', 'macd_signal', 'macd_histogram']:
        df[col] = 0.0
    for col in ['macd_bullish', 'macd_bearish']:
        df[col] = False
    return df


# ==================== BOLLINGER BANDS (Your Entry Tool) ====================

def calculate_bollinger_bands(df: pd.DataFrame, period: int = 34, deviation: float = 1.75) -> pd.DataFrame:
    """
    Calculate Bollinger Bands - Your ENTRY tool.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    if len(df) < period:
        df['bb_middle'] = df['close']
        df['bb_upper'] = df['close'] * 1.02
        df['bb_lower'] = df['close'] * 0.98
        df['bb_position'] = 0.5
        df['bb_width'] = df['bb_upper'] - df['bb_lower']
        return df

    df['bb_middle'] = df['close'].rolling(period).mean()
    df['bb_std'] = df['close'].rolling(period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * deviation)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * deviation)
    df['bb_width'] = df['bb_upper'] - df['bb_lower']

    # BB position (0=lower, 1=upper)
    bb_range = df['bb_upper'] - df['bb_lower']
    df['bb_position'] = ((df['close'] - df['bb_lower']) / bb_range.replace(0, EPSILON)).clip(0, 1)

    # Touch detection
    df['bb_touch_lower'] = df['ha_low'] <= df['bb_lower'] if 'ha_low' in df.columns else df['close'] <= df['bb_lower']
    df['bb_touch_upper'] = df['ha_high'] >= df['bb_upper'] if 'ha_high' in df.columns else df['close'] >= df['bb_upper']

    # Reversal detection
    df['bb_reversal_buy'] = df['bb_touch_lower'] & (df['close'] > df['bb_lower']) & (df.get('ha_color', 1) == 1)
    df['bb_reversal_sell'] = df['bb_touch_upper'] & (df['close'] < df['bb_upper']) & (df.get('ha_color', -1) == -1)

    # Candles shrinking (momentum loss)
    candle_range = df['high'] - df['low']
    df['candles_shrinking'] = candle_range < candle_range.rolling(3).mean().shift(1)

    df = df.ffill().bfill()
    return df


# ==================== ATR (Risk Management) ====================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate ATR for risk management."""
    if df is None or df.empty:
        return df

    df = df.copy()

    if len(df) < period:
        df['atr'] = df['close'] * 0.01
        return df

    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.rolling(period).mean()
    df['atr'] = df['atr'].fillna(df['close'] * 0.01)

    return df


# ==================== VOLUME ====================

def calculate_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate basic volume indicators."""
    if df is None or df.empty or 'volume' not in df.columns:
        return df

    df = df.copy()
    df['volume_sma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma'].replace(0, EPSILON)
    df['volume_ratio'] = df['volume_ratio'].clip(0, 10).fillna(1)
    return df


# ==================== MAIN CALCULATION ====================

def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate ALL indicators needed for the strategy.
    This is the main entry point.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # 1. Heikin Ashi (candle patterns)
    df = calculate_heikin_ashi(df)

    # 2. TDI (PRIMARY - replaces RSI)
    df = calculate_tdi(df, rsi_period=10, fast_ma_period=1, slow_ma_period=5)

    # 3. MACD (SECONDARY - confirmation)
    df = calculate_macd(df, fast=12, slow=26, signal=9)

    # 4. Bollinger Bands (ENTRY tool)
    df = calculate_bollinger_bands(df, period=34, deviation=1.75)

    # 5. ATR (Risk management)
    df = calculate_atr(df, period=14)

    # 6. Volume
    df = calculate_volume_indicators(df)

    # Clean up
    df = df.ffill().bfill()

    indicator_logger.debug(f"✅ Calculated all indicators: {len(df)} rows, {len(df.columns)} columns")

    return df


# ==================== SINGLETON ====================

class Indicators:
    """Simple wrapper for indicator functions."""

    @staticmethod
    def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
        return calculate_all_indicators(df)

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Alias for backward compatibility."""
        return calculate_all_indicators(df)

    @staticmethod
    def calculate_tdi(df: pd.DataFrame) -> pd.DataFrame:
        return calculate_tdi(df)

    @staticmethod
    def calculate_macd(df: pd.DataFrame) -> pd.DataFrame:
        return calculate_macd(df)

    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame) -> pd.DataFrame:
        """Alias for calculate_bb - matches old API."""
        return calculate_bollinger_bands(df)

    @staticmethod
    def calculate_bb(df: pd.DataFrame) -> pd.DataFrame:
        return calculate_bollinger_bands(df)

    @staticmethod
    def calculate_atr(df: pd.DataFrame) -> pd.DataFrame:
        return calculate_atr(df)

    @staticmethod
    def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
        return calculate_heikin_ashi(df)


# Create singleton
indicators = Indicators()

__all__ = [
    "indicators",
    "Indicators",
    "calculate_all_indicators",
    "calculate_tdi",
    "calculate_macd",
    "calculate_bollinger_bands",
    "calculate_atr",
    "calculate_heikin_ashi",
    "get_tdi_zone",
    "get_tdi_zone_description",
]
