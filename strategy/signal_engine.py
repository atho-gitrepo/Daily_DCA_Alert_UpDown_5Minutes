"""
Signal Engine - Super TDI + MACD + Bollinger Bands with AI
Version: 3.4.2 - ADDED: MACD Confirmation, REMOVED: HTF Trend Filter
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
    Signal Engine combining Super TDI + MACD + Bollinger Bands with AI validation.
    MATCHES YOUR MANUAL STRATEGY.

    Strategy Rules (Your Manual Strategy):
    1. TDI (RSI) in buyer/seller zone (Primary)
    2. MACD confirmation (Secondary)
    3. Price touches Bollinger Band (Entry)
    4. Candles getting smaller (Momentum loss)
    5. Price moving back inside band (Reversal)

    1H is used for CONTEXT only - NOT for filtering trades.
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

        # MACD Settings
        self.macd_fast = getattr(config.strategy, 'macd_fast', 12)
        self.macd_slow = getattr(config.strategy, 'macd_slow', 26)
        self.macd_signal = getattr(config.strategy, 'macd_signal', 9)
        self.require_macd = getattr(config.strategy, 'require_macd_confirmation', True)

        # HTF is for CONTEXT only - NOT a filter
        self.require_htf_alignment = False  # DISABLED

        self.last_signal = None
        self.last_signal_time = None

        # Risk parameters
        self.min_rrr = getattr(config.strategy, 'min_rrr', 1.5)
        self.default_rrr = getattr(config.strategy, 'default_rrr', 2.0)
        self.max_rrr = getattr(config.strategy, 'max_rrr', 4.0)

        # Grade thresholds
        self.grade_a_threshold = getattr(config.strategy, 'grade_a_threshold', 80)
        self.grade_b_threshold = getattr(config.strategy, 'grade_b_threshold', 60)
        self.grade_c_threshold = getattr(config.strategy, 'grade_c_threshold', 50)
        self.min_quality_score = getattr(config.strategy, 'min_quality_score', 50)

        logger.info(f"🔧 Signal Engine v3.4.2 initialized - AI: {'✅' if self.use_ai else '❌'}")
        logger.info(f"   RRR Range: {self.min_rrr} - {self.max_rrr}")
        logger.info(f"   Default RRR: {self.default_rrr}")
        logger.info(f"   MACD Confirmation: {'✅' if self.require_macd else '❌'}")
        logger.info(f"   HTF Trend Filter: ❌ DISABLED (Manual strategy)")
        logger.info(f"   Min Quality Score: {self.min_quality_score}")

    def process(self, df: pd.DataFrame, symbol: str = "UNKNOWN", htf_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Process data and generate signals with MACD confirmation.

        Args:
            df: LTF data (5m)
            symbol: Trading symbol
            htf_df: HTF data (1h) for CONTEXT only (not used as filter)

        Returns:
            Signal dictionary or NO_TRADE
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

        # ========== STEP 3: GET MACD CONFIRMATION ==========
        macd_result = self._check_macd(df)

        # Log MACD result
        if macd_result:
            logger.debug(f"📊 {symbol} MACD: Histogram={macd_result.get('histogram', 0):.4f}, Bullish={macd_result.get('bullish', False)}")

        # ========== STEP 4: CHECK BUY CONDITIONS ==========
        buy_conditions = self._check_buy_conditions(tdi_result, bb_result, macd_result)
        buy_ok, buy_reason = buy_conditions

        # Log BUY conditions
        logger.debug(f"📊 {symbol} BUY Conditions: {buy_ok} - {buy_reason if buy_reason else 'N/A'}")

        # ========== STEP 5: CHECK SELL CONDITIONS ==========
        sell_conditions = self._check_sell_conditions(tdi_result, bb_result, macd_result)
        sell_ok, sell_reason = sell_conditions

        # Log SELL conditions
        logger.debug(f"📊 {symbol} SELL Conditions: {sell_ok} - {sell_reason if sell_reason else 'N/A'}")

        # ========== STEP 6: GENERATE SIGNAL ==========
        signal_data = None

        if buy_ok:
            signal_data = self._generate_buy_signal(symbol, df, tdi_result, bb_result, buy_reason, macd_result)
            logger.info(f"🟢 {symbol}: BUY signal generated - {buy_reason}")

        elif sell_ok:
            signal_data = self._generate_sell_signal(symbol, df, tdi_result, bb_result, sell_reason, macd_result)
            logger.info(f"🔴 {symbol}: SELL signal generated - {sell_reason}")

        else:
            tdi_level = tdi_result.get('tdi_level', 50)
            tdi_zone = tdi_result.get('tdi_zone', 'UNKNOWN')
            reason = f"TDI: {tdi_level:.1f} ({tdi_zone})"
            return self._no_signal(symbol, reason)

        # ========== STEP 7: QUALITY SCORE VALIDATION ==========
        quality_score = signal_data.get('quality_score', 0)
        if quality_score < self.min_quality_score:
            logger.debug(f"🚫 {symbol}: Quality score {quality_score} below minimum {self.min_quality_score}")
            return self._no_signal(symbol, f"Quality score too low: {quality_score}")

        # ========== STEP 8: AI VALIDATION ==========
        if self.use_ai:
            signal_data = self._apply_ai_validation(symbol, signal_data)
            if signal_data.get('signal') == 'NO_TRADE':
                return signal_data

        # ========== STEP 9: GENERATE CHEAT SHEET ==========
        signal_data['cheat_sheet'] = self._generate_ai_enhanced_cheat_sheet(signal_data)

        self.last_signal = signal_data
        self.last_signal_time = datetime.now()

        return signal_data

    def _check_macd(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Check MACD for confirmation."""
        try:
            # Calculate MACD if not present
            if 'macd' not in df.columns:
                exp1 = df['close'].ewm(span=self.macd_fast, adjust=False).mean()
                exp2 = df['close'].ewm(span=self.macd_slow, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
                histogram = macd - signal
            else:
                macd = df['macd']
                signal = df['macd_signal']
                histogram = df['macd_histogram']

            last_macd = macd.iloc[-1]
            last_signal = signal.iloc[-1]
            last_hist = histogram.iloc[-1]
            prev_hist = histogram.iloc[-2] if len(histogram) > 1 else last_hist

            # Bullish: MACD above signal AND histogram rising
            bullish = last_macd > last_signal and last_hist > prev_hist

            # Bearish: MACD below signal AND histogram falling
            bearish = last_macd < last_signal and last_hist < prev_hist

            return {
                'macd': last_macd,
                'signal': last_signal,
                'histogram': last_hist,
                'prev_histogram': prev_hist,
                'bullish': bullish,
                'bearish': bearish,
                'above_signal': last_macd > last_signal,
                'hist_rising': last_hist > prev_hist,
                'hist_falling': last_hist < prev_hist,
            }

        except Exception as e:
            logger.debug(f"MACD calculation error: {e}")
            return None

    def _check_buy_conditions(self, tdi_data: Dict, bb_data: Dict, macd_data: Dict) -> Tuple[bool, str]:
        """Check all BUY conditions."""
        conditions = []

        # Condition 1: TDI in buyer zone
        tdi_zone = tdi_data.get('tdi_zone', '')
        if tdi_zone in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE']:
            conditions.append("TDI buyer zone")
        else:
            return False, f"TDI not in buyer zone: {tdi_zone}"

        # Condition 2: BB touch lower or near lower
        if bb_data.get('touch_lower', False) or bb_data.get('position', 0.5) < 0.30:
            conditions.append("BB touch lower")
        else:
            return False, f"BB not touching lower: {bb_data.get('position', 0.5):.2f}"

        # Condition 3: Reversal confirmed
        if bb_data.get('reversal_buy', False):
            conditions.append("Reversal confirmed")
        else:
            return False, "No reversal confirmation"

        # Condition 4: Candles shrinking (momentum loss)
        if bb_data.get('candles_shrinking', False):
            conditions.append("Candles shrinking")
        # Not required for your strategy but adds confidence

        # Condition 5: MACD confirmation
        if self.require_macd and macd_data:
            if macd_data.get('bullish', False):
                conditions.append("MACD bullish")
            else:
                return False, "MACD not bullish"
        elif self.require_macd and not macd_data:
            return False, "MACD data unavailable"

        return True, f"✅ {len(conditions)} conditions: " + " | ".join(conditions)

    def _check_sell_conditions(self, tdi_data: Dict, bb_data: Dict, macd_data: Dict) -> Tuple[bool, str]:
        """Check all SELL conditions."""
        conditions = []

        # Condition 1: TDI in seller zone
        tdi_zone = tdi_data.get('tdi_zone', '')
        if tdi_zone in ['OVERBOUGHT', 'SOFT_SELL']:
            conditions.append("TDI seller zone")
        else:
            return False, f"TDI not in seller zone: {tdi_zone}"

        # Condition 2: BB touch upper or near upper
        if bb_data.get('touch_upper', False) or bb_data.get('position', 0.5) > 0.70:
            conditions.append("BB touch upper")
        else:
            return False, f"BB not touching upper: {bb_data.get('position', 0.5):.2f}"

        # Condition 3: Reversal confirmed
        if bb_data.get('reversal_sell', False):
            conditions.append("Reversal confirmed")
        else:
            return False, "No reversal confirmation"

        # Condition 4: Candles shrinking
        if bb_data.get('candles_shrinking', False):
            conditions.append("Candles shrinking")

        # Condition 5: MACD confirmation
        if self.require_macd and macd_data:
            if macd_data.get('bearish', False):
                conditions.append("MACD bearish")
            else:
                return False, "MACD not bearish"
        elif self.require_macd and not macd_data:
            return False, "MACD data unavailable"

        return True, f"✅ {len(conditions)} conditions: " + " | ".join(conditions)

    def _generate_buy_signal(self, symbol: str, df: pd.DataFrame,
                             tdi_data: Dict, bb_data: Dict,
                             reason: str, macd_data: Dict) -> Dict[str, Any]:
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
        quality_score = self._calculate_quality_score(tdi_data, bb_data, macd_data)

        # Determine signal strength
        signal_strength = self._determine_strength(tdi_data, quality_score)

        return {
            'symbol': symbol,
            'direction': 'BUY',
            'signal': 'BUY',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rrr': rrr,
            'confidence': 0.7,
            'quality_score': quality_score,
            'total_score': quality_score,
            'grade': self._get_grade(quality_score),
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
            'signal_strength': signal_strength,
            'risk_multiplier': 1.0,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': None,
            'ai_decision': 'PENDING',
            'ai_reasoning': 'Awaiting AI analysis...',
            'ai_confidence': 0.0,
            'ai_analysis': {},
            # MACD
            'macd_bullish': macd_data.get('bullish', False) if macd_data else False,
            'macd_histogram': macd_data.get('histogram', 0) if macd_data else 0,
            'macd_above_signal': macd_data.get('above_signal', False) if macd_data else False,
            # 5 Conditions tracking
            'condition_1_tdi_zone': tdi_data.get('tdi_zone') in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE'],
            'condition_2_tdi_cross': tdi_data.get('bullish_cross', False),
            'condition_3_bb_touch': bb_data.get('touch_lower', False) or bb_data.get('position', 0.5) < 0.30,
            'condition_4_candles_shrinking': bb_data.get('candles_shrinking', False),
            'condition_5_reversal_confirm': bb_data.get('reversal_buy', False),
        }

    def _generate_sell_signal(self, symbol: str, df: pd.DataFrame,
                              tdi_data: Dict, bb_data: Dict,
                              reason: str, macd_data: Dict) -> Dict[str, Any]:
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
        quality_score = self._calculate_quality_score(tdi_data, bb_data, macd_data)

        # Determine signal strength
        signal_strength = self._determine_strength(tdi_data, quality_score)

        return {
            'symbol': symbol,
            'direction': 'SELL',
            'signal': 'SELL',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rrr': rrr,
            'confidence': 0.7,
            'quality_score': quality_score,
            'total_score': quality_score,
            'grade': self._get_grade(quality_score),
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
            'signal_strength': signal_strength,
            'risk_multiplier': 1.0,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'cheat_sheet': None,
            'ai_decision': 'PENDING',
            'ai_reasoning': 'Awaiting AI analysis...',
            'ai_confidence': 0.0,
            'ai_analysis': {},
            # MACD
            'macd_bearish': macd_data.get('bearish', False) if macd_data else False,
            'macd_histogram': macd_data.get('histogram', 0) if macd_data else 0,
            'macd_below_signal': not macd_data.get('above_signal', True) if macd_data else False,
            # 5 Conditions tracking
            'condition_1_tdi_zone': tdi_data.get('tdi_zone') in ['OVERBOUGHT', 'SOFT_SELL'],
            'condition_2_tdi_cross': tdi_data.get('bearish_cross', False),
            'condition_3_bb_touch': bb_data.get('touch_upper', False) or bb_data.get('position', 0.5) > 0.70,
            'condition_4_candles_shrinking': bb_data.get('candles_shrinking', False),
            'condition_5_reversal_confirm': bb_data.get('reversal_sell', False),
        }

    def _calculate_quality_score(self, tdi_data: Dict, bb_data: Dict, macd_data: Dict = None) -> int:
        """Calculate quality score (0-100) with MACD bonus."""
        score = 50  # Base score

        # TDI zone bonus
        zone = tdi_data.get('tdi_zone', '')
        if zone in ['OVERSOLD', 'OVERBOUGHT']:
            score += 15
        elif zone in ['SOFT_BUY', 'SOFT_SELL']:
            score += 10
        elif zone in ['BUY_ZONE', 'SELL_ZONE']:
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

        # MACD bonus
        if macd_data:
            if macd_data.get('bullish', False) or macd_data.get('bearish', False):
                score += 10
            if macd_data.get('hist_rising', False) or macd_data.get('hist_falling', False):
                score += 5

        return min(100, max(0, score))

    def _determine_strength(self, tdi_data: Dict, quality_score: int) -> str:
        """Determine signal strength."""
        zone = tdi_data.get('tdi_zone', '')
        if zone in ['OVERSOLD', 'OVERBOUGHT'] and quality_score >= 70:
            return "HARD"
        elif zone in ['SOFT_BUY', 'SOFT_SELL'] and quality_score >= 60:
            return "SOFT"
        else:
            return "SOFT"

    def _get_grade(self, score: int) -> str:
        """Get grade based on score."""
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 72:
            return "B+"
        elif score >= 60:
            return "B"
        elif score >= 50:
            return "C"
        else:
            return "D"

    def _generate_ai_enhanced_cheat_sheet(self, signal_data: Dict[str, Any]) -> str:
        """Generate cheat sheet with AI insights."""
        direction = signal_data.get('direction', 'NONE')

        if direction == 'BUY':
            base = self.cheat_sheet.generate_buy_cheat_sheet(signal_data)
        elif direction == 'SELL':
            base = self.cheat_sheet.generate_sell_cheat_sheet(signal_data)
        else:
            return self.cheat_sheet.generate_wait_cheat_sheet(signal_data)

        # Add MACD info
        macd_section = f"""
📊 <b>MACD Confirmation</b>
• Bullish: {'✅' if signal_data.get('macd_bullish', False) else '❌'}
• Histogram: {signal_data.get('macd_histogram', 0):.4f}
• Above Signal: {'✅' if signal_data.get('macd_above_signal', False) else '❌'}"""

        # Add AI insights if available
        ai_data = signal_data.get('ai_analysis', {})
        if ai_data and ai_data.get('decision'):
            ai_section = f"""
🤖 <b>AI Analysis (Groq)</b>
• Decision: <b>{ai_data.get('decision', 'UNKNOWN')}</b>
• Confidence: <b>{ai_data.get('confidence', 0)*100:.0f}%</b>
• Reasoning: {ai_data.get('reasoning', 'N/A')}"""

            if ai_data.get('market_analysis'):
                ai_section += f"\n• Market: {ai_data.get('market_analysis')}"

            return base + "\n\n" + macd_section + "\n\n" + ai_section

        return base + "\n\n" + macd_section

    def _no_signal(self, symbol: str, reason: str) -> Dict[str, Any]:
        """Return no signal result."""
        return {
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

    def _apply_ai_validation(self, symbol: str, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply AI validation to signal."""
        try:
            logger.info(f"🤖 {symbol}: Requesting AI analysis...")

            ai_result = ai_analyzer.analyze_signal(signal_data)

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

            if ai_result.decision == 'REJECT':
                signal_data['signal'] = 'NO_TRADE'
                signal_data['direction'] = 'NONE'
                logger.info(f"🚫 {symbol}: AI REJECTED - {ai_result.reasoning}")
                return signal_data

            if ai_result.decision == 'WAIT':
                signal_data['signal'] = 'NO_TRADE'
                signal_data['direction'] = 'NONE'
                logger.info(f"⏳ {symbol}: AI WAIT - {ai_result.reasoning}")
                return signal_data

            logger.info(f"✅ {symbol}: AI APPROVED - Confidence: {ai_result.confidence:.0%}")

            return signal_data

        except Exception as e:
            logger.error(f"❌ {symbol}: AI validation error: {e}")
            signal_data['ai_decision'] = 'ERROR'
            signal_data['ai_reasoning'] = f"AI Error: {str(e)}"
            signal_data['ai_confidence'] = 0.0
            return signal_data

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            'last_signal': self.last_signal,
            'last_signal_time': self.last_signal_time,
            'use_ai': self.use_ai,
            'min_rrr': self.min_rrr,
            'default_rrr': self.default_rrr,
            'max_rrr': self.max_rrr,
            'require_macd': self.require_macd,
            'require_htf_alignment': False,
            'min_quality_score': self.min_quality_score,
            'version': '3.4.2'
        }
