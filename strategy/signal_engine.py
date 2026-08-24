"""
Signal Engine - Super TDI + Super Bollinger Bands with AI
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from strategy.tdi_detector import TDIDetector
from strategy.bb_detector import BBDetector
from strategy.cheat_sheet import SignalCheatSheet
from strategy.ai_analyzer import ai_analyzer
from settings import config
import logging

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Signal Engine combining Super TDI and Super Bollinger Bands with AI validation.
    """

    def __init__(self, use_ai: bool = True):  # ✅ ADD THIS PARAMETER
        """
        Initialize Signal Engine.

        Args:
            use_ai: Whether to use AI validation (default: True)
        """
        self.tdi_detector = TDIDetector()
        self.bb_detector = BBDetector()
        self.cheat_sheet = SignalCheatSheet()
        self.use_ai = use_ai and ai_analyzer.enabled if ai_analyzer else False

        self.last_signal = None
        self.last_signal_time = None

        # Risk parameters
        self.min_rrr = getattr(config.strategy, 'min_rrr', 1.5)
        self.default_rrr = getattr(config.strategy, 'default_rrr', 2.0)
        self.max_rrr = getattr(config.strategy, 'max_rrr', 4.0)

        logger.info(f"🔧 Signal Engine initialized - AI: {'✅' if self.use_ai else '❌'}")

    def process(self, df: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict[str, Any]:
        """
        Process data and generate signals with AI validation.

        Returns:
            {
                'signal': 'BUY' or 'SELL' or 'NO_TRADE',
                'direction': 'BUY' or 'SELL' or 'NONE',
                'cheat_sheet': str,
                'ai_decision': str,
                'ai_reasoning': str,
                'ai_confidence': float,
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
                'ai_analysis': dict,
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
            signal_data = self._generate_buy_signal(symbol, df, tdi_result, bb_result, buy_reason)
        elif sell_ok:
            signal_data = self._generate_sell_signal(symbol, df, tdi_result, bb_result, sell_reason)
        else:
            tdi_level = tdi_result.get('tdi_level', 50)
            tdi_zone = tdi_result.get('tdi_zone', 'UNKNOWN')
            return self._no_signal(symbol, f"TDI: {tdi_level:.1f} ({tdi_zone})")

        # === AI VALIDATION ===
        if self.use_ai:
            logger.info(f"🤖 Requesting AI analysis for {symbol} {signal_data.get('direction')} signal...")
            ai_result = ai_analyzer.analyze_signal(signal_data)

            # Store AI result
            signal_data['ai_analysis'] = {
                'decision': ai_result.decision,
                'confidence': ai_result.confidence,
                'reasoning': ai_result.reasoning,
                'signal_strength': ai_result.signal_strength,
                'risk_level': ai_result.risk_level,
                'suggested_rrr': ai_result.suggested_rrr,
                'market_analysis': ai_result.market_analysis,
                'technical_factors': ai_result.technical_factors,
                'risk_factors': ai_result.risk_factors,
                'response_time_ms': ai_result.response_time_ms,
                'ai_validated': ai_result.ai_validated,
            }

            signal_data['ai_decision'] = ai_result.decision
            signal_data['ai_reasoning'] = ai_result.reasoning
            signal_data['ai_confidence'] = ai_result.confidence

            # If AI rejects, return no trade
            if ai_result.decision == 'REJECT':
                signal_data['signal'] = 'NO_TRADE'
                signal_data['direction'] = 'NONE'
                signal_data['cheat_sheet'] = self.cheat_sheet.generate_wait_cheat_sheet({
                    'symbol': symbol,
                    'tdi_level': signal_data.get('tdi_level', 50),
                    'reason': f"AI Rejected: {ai_result.reasoning}"
                })
                logger.info(f"🚫 AI REJECTED: {symbol} - {ai_result.reasoning}")
                return signal_data

            # If AI says WAIT, return no trade with reason
            if ai_result.decision == 'WAIT':
                signal_data['signal'] = 'NO_TRADE'
                signal_data['direction'] = 'NONE'
                signal_data['cheat_sheet'] = self.cheat_sheet.generate_wait_cheat_sheet({
                    'symbol': symbol,
                    'tdi_level': signal_data.get('tdi_level', 50),
                    'reason': f"AI Says Wait: {ai_result.reasoning}"
                })
                logger.info(f"⏳ AI WAIT: {symbol} - {ai_result.reasoning}")
                return signal_data

            # AI approved - update signal with AI insights
            logger.info(f"✅ AI APPROVED: {symbol} {signal_data.get('direction')} | Confidence: {ai_result.confidence:.0%}")

            # Adjust RRR based on AI suggestion
            if ai_result.suggested_rrr:
                signal_data['rrr'] = min(self.max_rrr, max(self.min_rrr, ai_result.suggested_rrr))
                # Recalculate TP with new RRR
                current_price = signal_data.get('entry_price', 0)
                stop_loss = signal_data.get('stop_loss', 0)
                risk = abs(current_price - stop_loss)
                if signal_data.get('direction') == 'BUY':
                    signal_data['take_profit'] = current_price + (signal_data['rrr'] * risk)
                else:
                    signal_data['take_profit'] = current_price - (signal_data['rrr'] * risk)

        # Generate cheat sheet with AI notes if available
        signal_data['cheat_sheet'] = self._generate_ai_enhanced_cheat_sheet(signal_data)

        self.last_signal = signal_data
        self.last_signal_time = datetime.now()

        return signal_data

    def _generate_ai_enhanced_cheat_sheet(self, signal_data: Dict[str, Any]) -> str:
        """Generate cheat sheet with AI insights."""
        direction = signal_data.get('direction', 'NONE')

        # Get base cheat sheet
        if direction == 'BUY':
            base = self.cheat_sheet.generate_buy_cheat_sheet(signal_data)
        elif direction == 'SELL':
            base = self.cheat_sheet.generate_sell_cheat_sheet(signal_data)
        else:
            return self.cheat_sheet.generate_wait_cheat_sheet(signal_data)

        # Add AI insights if available
        ai_data = signal_data.get('ai_analysis', {})
        if ai_data:
            ai_section = f"""
🤖 AI Analysis
• Decision: {ai_data.get('decision', 'UNKNOWN')}
• Confidence: {ai_data.get('confidence', 0)*100:.0f}%
• Reasoning: {ai_data.get('reasoning', 'N/A')}
• Risk Level: {ai_data.get('risk_level', 'MEDIUM')}
"""
            return base + "\n\n" + ai_section

        return base

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

        return {
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
            'tdi_bearish_cross': tdi_data.get('bearish_cross', False),
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
            'cheat_sheet': None,
            'ai_decision': 'PENDING',
            'ai_reasoning': 'Awaiting AI analysis...',
            'ai_confidence': 0.0,
            'ai_analysis': {},
        }

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

        return {
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
            'tdi_bullish_cross': tdi_data.get('bullish_cross', False),
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
            'cheat_sheet': None,
            'ai_decision': 'PENDING',
            'ai_reasoning': 'Awaiting AI analysis...',
            'ai_confidence': 0.0,
            'ai_analysis': {},
        }

    def _no_signal(self, symbol: str, reason: str) -> Dict[str, Any]:
        """Return no signal result."""
        data = {
            'symbol': symbol,
            'signal': 'NO_TRADE',
            'direction': 'NONE',
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'ai_decision': 'NONE',
            'ai_reasoning': 'No signal to analyze',
            'ai_confidence': 0.0,
            'ai_analysis': {},
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
