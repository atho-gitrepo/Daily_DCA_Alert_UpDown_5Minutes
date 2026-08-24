"""
Signal Engine - Super TDI + Super Bollinger Bands
Combines all strategy components with cheat sheet generation.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from strategy.tdi_detector import TDIDetector
from strategy.bb_detector import BBDetector
from strategy.cheat_sheet import SignalCheatSheet


class SignalEngine:
    """
    Main Signal Engine combining Super TDI and Super Bollinger Bands.

    Strategy Rules:
    1. TDI in buyer/seller zone
    2. Green line crossing above/below Red (crossover)
    3. Price touches Bollinger Band (oversold/overbought)
    4. Candles getting smaller (momentum loss)
    5. Price moving back inside band (reversal)

    ALL 5 = ENTER TRADE
    """

    def __init__(self):
        self.tdi_detector = TDIDetector()
        self.bb_detector = BBDetector()
        self.cheat_sheet = SignalCheatSheet()

        self.last_signal = None
        self.last_signal_time = None

        # Risk parameters
        self.min_rrr = 1.5
        self.default_rrr = 2.0
        self.max_rrr = 4.0

    def process(self, df: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict[str, Any]:
        """
        Process data and generate signals.

        Returns:
            {
                'signal': 'BUY' or 'SELL' or 'NO_TRADE',
                'direction': 'BUY' or 'SELL' or 'NONE',
                'cheat_sheet': str,
                'entry_price': float,
                'stop_loss': float,
                'take_profit': float,
                'rrr': float,
                'confidence': float,
                'tdi_level': float,
                'tdi_zone': str,
                'bb_position': float,
                'reasons': list,
                'timestamp': str,
            }
        """
        if df is None or df.empty:
            return self._no_signal(symbol, "No data")

        # Get TDI opportunity
        tdi_result = self.tdi_detector.detect_opportunity(df)

        # Get BB interaction
        bb_result = self.bb_detector.detect_bb_interaction(df)

        # Check BUY conditions
        buy_conditions = self.bb_detector.check_buy_conditions(bb_result, tdi_result)
        buy_ok, buy_reason = buy_conditions

        # Check SELL conditions
        sell_conditions = self.bb_detector.check_sell_conditions(bb_result, tdi_result)
        sell_ok, sell_reason = sell_conditions

        # Generate signal
        if buy_ok:
            return self._generate_buy_signal(symbol, df, tdi_result, bb_result, buy_reason)

        elif sell_ok:
            return self._generate_sell_signal(symbol, df, tdi_result, bb_result, sell_reason)

        else:
            # No signal - create wait message
            tdi_level = tdi_result.get('tdi_level', 50)
            tdi_zone = tdi_result.get('tdi_zone', 'UNKNOWN')
            return self._no_signal(symbol, f"TDI: {tdi_level:.1f} ({tdi_zone})")

    def _generate_buy_signal(self, symbol: str, df: pd.DataFrame,
                             tdi_data: Dict, bb_data: Dict,
                             reason: str) -> Dict[str, Any]:
        """Generate BUY signal."""
        last = df.iloc[-1]
        current_price = last.get('close', 0)
        atr = self._calculate_atr(df)

        # Calculate SL/TP
        stop_loss = current_price - (1.5 * atr) if atr > 0 else current_price * 0.985
        take_profit = current_price + (self.default_rrr * (current_price - stop_loss))

        # Calculate RRR
        risk = current_price - stop_loss
        reward = take_profit - current_price
        rrr = reward / risk if risk > 0 else self.default_rrr

        signal_data = {
            'symbol': symbol,
            'direction': 'BUY',
            'signal': 'BUY',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rrr': min(self.max_rrr, max(self.min_rrr, rrr)),
            'confidence': tdi_data.get('confidence', 0.7),
            'tdi_level': tdi_data.get('tdi_level', 50),
            'tdi_zone': tdi_data.get('tdi_zone', 'UNKNOWN'),
            'tdi_zone_description': tdi_data.get('tdi_zone_description', ''),
            'tdi_bullish_cross': tdi_data.get('bullish_cross', False),
            'tdi_fast': tdi_data.get('tdi_fast', 50),
            'tdi_slow': tdi_data.get('tdi_slow', 50),
            'bb_position': bb_data.get('position', 0.5),
            'touch_lower': bb_data.get('touch_lower', False),
            'touch_upper': bb_data.get('touch_upper', False),
            'candles_shrinking': bb_data.get('candles_shrinking', False),
            'reversal_confirm': bb_data.get('reversal_buy', False),
            'signal_strength': tdi_data.get('signal_strength', 'SOFT'),
            'risk_multiplier': tdi_data.get('risk_multiplier', 1.0),
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': None,  # Will be generated
        }

        # Generate cheat sheet
        signal_data['cheat_sheet'] = self.cheat_sheet.generate_buy_cheat_sheet(signal_data)

        self.last_signal = signal_data
        self.last_signal_time = datetime.now()

        return signal_data

    def _generate_sell_signal(self, symbol: str, df: pd.DataFrame,
                              tdi_data: Dict, bb_data: Dict,
                              reason: str) -> Dict[str, Any]:
        """Generate SELL signal."""
        last = df.iloc[-1]
        current_price = last.get('close', 0)
        atr = self._calculate_atr(df)

        # Calculate SL/TP
        stop_loss = current_price + (1.5 * atr) if atr > 0 else current_price * 1.015
        take_profit = current_price - (self.default_rrr * (stop_loss - current_price))

        # Calculate RRR
        risk = stop_loss - current_price
        reward = current_price - take_profit
        rrr = reward / risk if risk > 0 else self.default_rrr

        signal_data = {
            'symbol': symbol,
            'direction': 'SELL',
            'signal': 'SELL',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rrr': min(self.max_rrr, max(self.min_rrr, rrr)),
            'confidence': tdi_data.get('confidence', 0.7),
            'tdi_level': tdi_data.get('tdi_level', 50),
            'tdi_zone': tdi_data.get('tdi_zone', 'UNKNOWN'),
            'tdi_zone_description': tdi_data.get('tdi_zone_description', ''),
            'tdi_bearish_cross': tdi_data.get('bearish_cross', False),
            'tdi_fast': tdi_data.get('tdi_fast', 50),
            'tdi_slow': tdi_data.get('tdi_slow', 50),
            'bb_position': bb_data.get('position', 0.5),
            'touch_lower': bb_data.get('touch_lower', False),
            'touch_upper': bb_data.get('touch_upper', False),
            'candles_shrinking': bb_data.get('candles_shrinking', False),
            'reversal_confirm': bb_data.get('reversal_sell', False),
            'signal_strength': tdi_data.get('signal_strength', 'SOFT'),
            'risk_multiplier': tdi_data.get('risk_multiplier', 1.0),
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': None,  # Will be generated
        }

        # Generate cheat sheet
        signal_data['cheat_sheet'] = self.cheat_sheet.generate_sell_cheat_sheet(signal_data)

        self.last_signal = signal_data
        self.last_signal_time = datetime.now()

        return signal_data

    def _no_signal(self, symbol: str, reason: str) -> Dict[str, Any]:
        """Return no signal result."""
        data = {
            'symbol': symbol,
            'signal': 'NO_TRADE',
            'direction': 'NONE',
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
        }
        data['cheat_sheet'] = self.cheat_sheet.generate_wait_cheat_sheet(data)
        return data

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR."""
        try:
            if df is None or len(df) < period:
                return df['close'].iloc[-1] * 0.01 if not df.empty else 0

            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            tr1 = high - low
            tr2 = np.abs(high - np.roll(close, 1))
            tr3 = np.abs(low - np.roll(close, 1))
            tr = np.maximum(tr1, np.maximum(tr2, tr3))

            return np.mean(tr[-period:])
        except Exception:
            return df['close'].iloc[-1] * 0.01 if not df.empty else 0
