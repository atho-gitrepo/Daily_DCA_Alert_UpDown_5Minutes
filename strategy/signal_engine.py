"""
Signal Engine - Super TDI + Super Bollinger Bands with AI
Version: 3.4.0 - FULLY FUNCTIONAL
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from strategy.tdi_detector import TDIDetector
from strategy.bb_detector import BBDetector
from strategy.cheat_sheet import SignalCheatSheet
from strategy.ai_analyzer import ai_analyzer, AIAnalysisResult
from settings import config

# Setup logger
logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Signal Engine combining Super TDI and Super Bollinger Bands with AI validation.

    Strategy Rules (5 Conditions):
    1. TDI in buyer/seller zone
    2. Green line crossing above/below Red (crossover)
    3. Price touches Bollinger Band (oversold/overbought)
    4. Candles getting smaller (momentum loss)
    5. Price moving back inside band (reversal)

    ALL 5 = ENTER TRADE
    """

    def __init__(self, use_ai: bool = True):
        """
        Initialize Signal Engine.

        Args:
            use_ai: Whether to use AI validation (default: True)
        """
        self.tdi_detector = TDIDetector()
        self.bb_detector = BBDetector()
        self.cheat_sheet = SignalCheatSheet()

        # Check if AI should be used
        self.use_ai = use_ai and ai_analyzer.enabled if ai_analyzer else False

        self.last_signal = None
        self.last_signal_time = None

        # Risk parameters
        self.min_rrr = getattr(config.strategy, 'min_rrr', 1.5)
        self.default_rrr = getattr(config.strategy, 'default_rrr', 2.0)
        self.max_rrr = getattr(config.strategy, 'max_rrr', 4.0)

        logger.info(f"🔧 Signal Engine initialized - AI: {'✅' if self.use_ai else '❌'}")
        logger.info(f"   RRR Range: {self.min_rrr} - {self.max_rrr}")
        logger.info(f"   Default RRR: {self.default_rrr}")

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
                'tdi_zone_description': str,
                'bb_position': float,
                'reasons': list,
                'timestamp': str,
                'ai_analysis': dict,
            }
        """
        if df is None or df.empty:
            logger.warning(f"⚠️ {symbol}: No data received")
            return self._no_signal(symbol, "No data")

        # ========== STEP 1: GET TDI OPPORTUNITY ==========
        tdi_result = self.tdi_detector.detect_opportunity(df)

        # Log TDI result
        logger.debug(f"📊 {symbol} TDI: {tdi_result.get('opportunity')} | Zone: {tdi_result.get('tdi_zone')} | Direction: {tdi_result.get('direction')} | TDI: {tdi_result.get('tdi_level', 50):.1f}")
        if tdi_result.get('reason'):
            logger.debug(f"   Reason: {tdi_result.get('reason')}")

        # ========== STEP 2: GET BB INTERACTION ==========
        bb_result = self.bb_detector.detect_bb_interaction(df)

        # Log BB result
        logger.debug(f"📊 {symbol} BB: Position: {bb_result.get('position', 0.5):.2f} | Touch Lower: {bb_result.get('touch_lower', False)} | Touch Upper: {bb_result.get('touch_upper', False)} | Reversal: {bb_result.get('reversal_buy', False) or bb_result.get('reversal_sell', False)}")

        # ========== STEP 3: CHECK BUY CONDITIONS ==========
        buy_conditions = self.bb_detector.check_buy_conditions(bb_result, tdi_result)
        buy_ok, buy_reason = buy_conditions

        # Log BUY conditions
        logger.debug(f"📊 {symbol} BUY Conditions: {buy_ok} - {buy_reason if buy_reason else 'N/A'}")

        # ========== STEP 4: CHECK SELL CONDITIONS ==========
        sell_conditions = self.bb_detector.check_sell_conditions(bb_result, tdi_result)
        sell_ok, sell_reason = sell_conditions

        # Log SELL conditions
        logger.debug(f"📊 {symbol} SELL Conditions: {sell_ok} - {sell_reason if sell_reason else 'N/A'}")

        # ========== STEP 5: GENERATE SIGNAL ==========
        signal_data = None

        if buy_ok:
            signal_data = self._generate_buy_signal(symbol, df, tdi_result, bb_result, buy_reason)
            logger.info(f"🟢 {symbol}: BUY signal generated - {buy_reason}")
        elif sell_ok:
            signal_data = self._generate_sell_signal(symbol, df, tdi_result, bb_result, sell_reason)
            logger.info(f"🔴 {symbol}: SELL signal generated - {sell_reason}")
        else:
            tdi_level = tdi_result.get('tdi_level', 50)
            tdi_zone = tdi_result.get('tdi_zone', 'UNKNOWN')
            reason = f"TDI: {tdi_level:.1f} ({tdi_zone})"
            return self._no_signal(symbol, reason)

        # ========== STEP 6: AI VALIDATION ==========
        if self.use_ai:
            signal_data = self._apply_ai_validation(symbol, signal_data)

        # ========== STEP 7: GENERATE CHEAT SHEET ==========
        signal_data['cheat_sheet'] = self._generate_ai_enhanced_cheat_sheet(signal_data)

        self.last_signal = signal_data
        self.last_signal_time = datetime.now()

        return signal_data

    def _apply_ai_validation(self, symbol: str, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply AI validation to signal."""
        try:
            logger.info(f"🤖 {symbol}: Requesting AI analysis...")

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
                logger.info(f"🚫 {symbol}: AI REJECTED - {ai_result.reasoning}")
                return signal_data

            # If AI says WAIT
            if ai_result.decision == 'WAIT':
                signal_data['signal'] = 'NO_TRADE'
                signal_data['direction'] = 'NONE'
                signal_data['cheat_sheet'] = self.cheat_sheet.generate_wait_cheat_sheet({
                    'symbol': symbol,
                    'tdi_level': signal_data.get('tdi_level', 50),
                    'reason': f"AI Says Wait: {ai_result.reasoning}"
                })
                logger.info(f"⏳ {symbol}: AI WAIT - {ai_result.reasoning}")
                return signal_data

            # AI approved
            logger.info(f"✅ {symbol}: AI APPROVED - Confidence: {ai_result.confidence:.0%}")

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

            return signal_data

        except Exception as e:
            logger.error(f"❌ {symbol}: AI validation error: {e}")
            # If AI fails, still proceed with signal
            signal_data['ai_decision'] = 'ERROR'
            signal_data['ai_reasoning'] = f"AI Error: {str(e)}"
            signal_data['ai_confidence'] = 0.0
            return signal_data

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
        rrr = min(self.max_rrr, max(self.min_rrr, rrr))

        # Calculate quality score
        quality_score = self._calculate_quality_score(tdi_data, bb_data)

        # Determine signal strength
        signal_strength = tdi_data.get('signal_strength', 'SOFT')
        risk_multiplier = tdi_data.get('risk_multiplier', 1.0)

        # Get TDI zone description
        tdi_zone_desc = tdi_data.get('tdi_zone_description', '')

        return {
            'symbol': symbol,
            'direction': 'BUY',
            'signal': 'BUY',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rrr': rrr,
            'confidence': tdi_data.get('confidence', 0.7),
            'quality_score': quality_score,
            'tdi_level': tdi_data.get('tdi_level', 50),
            'tdi_zone': tdi_data.get('tdi_zone', 'UNKNOWN'),
            'tdi_zone_description': tdi_zone_desc,
            'tdi_bullish_cross': tdi_data.get('bullish_cross', False),
            'tdi_bearish_cross': tdi_data.get('bearish_cross', False),
            'tdi_fast': tdi_data.get('tdi_fast', 50),
            'tdi_slow': tdi_data.get('tdi_slow', 50),
            'bb_position': bb_data.get('position', 0.5),
            'touch_lower': bb_data.get('touch_lower', False),
            'touch_upper': bb_data.get('touch_upper', False),
            'candles_shrinking': bb_data.get('candles_shrinking', False),
            'reversal_confirm': bb_data.get('reversal_buy', False),
            'signal_strength': signal_strength,
            'risk_multiplier': risk_multiplier,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': None,
            'ai_decision': 'PENDING',
            'ai_reasoning': 'Awaiting AI analysis...',
            'ai_confidence': 0.0,
            'ai_analysis': {},
            # 5 Conditions tracking
            'condition_1_tdi_zone': tdi_data.get('tdi_zone') in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE'],
            'condition_2_tdi_cross': tdi_data.get('bullish_cross', False) or tdi_data.get('green_above_red', False),
            'condition_3_bb_touch': bb_data.get('touch_lower', False) or bb_data.get('position', 0.5) < 0.30,
            'condition_4_candles_shrinking': bb_data.get('candles_shrinking', False),
            'condition_5_reversal_confirm': bb_data.get('reversal_buy', False),
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
        rrr = min(self.max_rrr, max(self.min_rrr, rrr))

        # Calculate quality score
        quality_score = self._calculate_quality_score(tdi_data, bb_data)

        # Determine signal strength
        signal_strength = tdi_data.get('signal_strength', 'SOFT')
        risk_multiplier = tdi_data.get('risk_multiplier', 1.0)

        # Get TDI zone description
        tdi_zone_desc = tdi_data.get('tdi_zone_description', '')

        return {
            'symbol': symbol,
            'direction': 'SELL',
            'signal': 'SELL',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rrr': rrr,
            'confidence': tdi_data.get('confidence', 0.7),
            'quality_score': quality_score,
            'tdi_level': tdi_data.get('tdi_level', 50),
            'tdi_zone': tdi_data.get('tdi_zone', 'UNKNOWN'),
            'tdi_zone_description': tdi_zone_desc,
            'tdi_bullish_cross': tdi_data.get('bullish_cross', False),
            'tdi_bearish_cross': tdi_data.get('bearish_cross', False),
            'tdi_fast': tdi_data.get('tdi_fast', 50),
            'tdi_slow': tdi_data.get('tdi_slow', 50),
            'bb_position': bb_data.get('position', 0.5),
            'touch_lower': bb_data.get('touch_lower', False),
            'touch_upper': bb_data.get('touch_upper', False),
            'candles_shrinking': bb_data.get('candles_shrinking', False),
            'reversal_confirm': bb_data.get('reversal_sell', False),
            'signal_strength': signal_strength,
            'risk_multiplier': risk_multiplier,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': None,
            'ai_decision': 'PENDING',
            'ai_reasoning': 'Awaiting AI analysis...',
            'ai_confidence': 0.0,
            'ai_analysis': {},
            # 5 Conditions tracking
            'condition_1_tdi_zone': tdi_data.get('tdi_zone') in ['SOFT_SELL', 'OVERBOUGHT'],
            'condition_2_tdi_cross': tdi_data.get('bearish_cross', False) or tdi_data.get('green_below_red', False),
            'condition_3_bb_touch': bb_data.get('touch_upper', False) or bb_data.get('position', 0.5) > 0.70,
            'condition_4_candles_shrinking': bb_data.get('candles_shrinking', False),
            'condition_5_reversal_confirm': bb_data.get('reversal_sell', False),
        }

    def _calculate_quality_score(self, tdi_data: Dict, bb_data: Dict) -> int:
        """Calculate quality score (0-100)."""
        score = 50  # Base score

        # TDI zone bonus
        zone = tdi_data.get('tdi_zone', '')
        if zone == 'OVERSOLD' or zone == 'OVERBOUGHT':
            score += 15
        elif zone == 'SOFT_BUY' or zone == 'SOFT_SELL':
            score += 10
        elif zone == 'BUY_ZONE':
            score += 5

        # Crossover bonus
        if tdi_data.get('bullish_cross', False) or tdi_data.get('bearish_cross', False):
            score += 10

        # BB position bonus
        position = bb_data.get('position', 0.5)
        if position < 0.15 or position > 0.85:
            score += 15
        elif position < 0.30 or position > 0.70:
            score += 10

        # Reversal bonus
        if bb_data.get('reversal_buy', False) or bb_data.get('reversal_sell', False):
            score += 10

        # Candles shrinking bonus
        if bb_data.get('candles_shrinking', False):
            score += 5

        return min(100, max(0, score))

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
        if ai_data and ai_data.get('decision'):
            ai_section = f"""
🤖 <b>AI Analysis (Groq)</b>
• Decision: <b>{ai_data.get('decision', 'UNKNOWN')}</b>
• Confidence: <b>{ai_data.get('confidence', 0)*100:.0f}%</b>
• Reasoning: {ai_data.get('reasoning', 'N/A')}
• Risk Level: <b>{ai_data.get('risk_level', 'MEDIUM')}</b>
• Response Time: {ai_data.get('response_time_ms', 0):.0f}ms"""

            if ai_data.get('market_analysis'):
                ai_section += f"\n• Market: {ai_data.get('market_analysis')}"

            return base + "\n\n" + ai_section

        return base

    def _no_signal(self, symbol: str, reason: str) -> Dict[str, Any]:
        """Return no signal result."""
        data = {
            'symbol': symbol,
            'signal': 'NO_TRADE',
            'direction': 'NONE',
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': self.cheat_sheet.generate_wait_cheat_sheet({
                'symbol': symbol,
                'tdi_level': 50,
                'reason': reason
            }),
            'ai_decision': 'NONE',
            'ai_reasoning': 'No signal to analyze',
            'ai_confidence': 0.0,
            'ai_analysis': {},
        }
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
        except Exception as e:
            logger.debug(f"ATR calculation error: {e}")
            return df['close'].iloc[-1] * 0.01 if not df.empty else 0

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            'last_signal': self.last_signal,
            'last_signal_time': self.last_signal_time,
            'use_ai': self.use_ai,
            'min_rrr': self.min_rrr,
            'default_rrr': self.default_rrr,
            'max_rrr': self.max_rrr,
        }
