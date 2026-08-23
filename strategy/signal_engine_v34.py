# strategy/signal_engine_v34.py
"""
v3.4.0 Signal Engine - Compact Integration
Combines all v3.4.0 improvements into a single streamlined engine.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

from strategy.signal_state import SignalStateMachine, SignalState, SetupData
from strategy.htf_regime import HTFRegimeAnalyzer, Regime, RegimeData
from strategy.structure import MarketStructureAnalyzer, StructureData
from utils.indicators import Indicators, calculate_heikin_ashi, get_trading_session

logger = logging.getLogger(__name__)


class SignalEngineV34:
    """
    v3.4.0 Signal Engine - Complete Implementation.

    Key Improvements:
    1. Setup ≠ Signal (separate detection from entry)
    2. HTF Regime Filter (4H/1H directional bias)
    3. TDI cross/slope (not zone alone)
    4. 5M entry trigger confirmation
    5. Volume as confirmation gate
    6. Market structure (BOS/CHoCH/reclaim/sweep)
    7. Signal state machine (SETUP → ARMED → TRIGGER → CONFIRMED)
    8. Entry freshness and distance protection
    9. ATR-based risk model
    10. Reversal vs Continuation separation
    """

    def __init__(self):
        # Core components
        self.state_machine = SignalStateMachine()
        self.regime_analyzer = HTFRegimeAnalyzer()
        self.structure_analyzer = MarketStructureAnalyzer()

        # State
        self.current_regime: Optional[RegimeData] = None
        self.current_structure: Optional[StructureData] = None
        self.last_setup_time: Optional[datetime] = None
        self.signal_count = 0

        # Configuration
        self.MIN_SETUP_SCORE = 70
        self.MIN_TRIGGER_SCORE = 70
        self.COUNTER_TREND_MIN_SCORE = 82
        self.MAX_SIGNALS_PER_HOUR = 2
        self.SETUP_EXPIRY_SECONDS = 300  # 5 minutes

        # TDI thresholds
        self.OVERSOLD = 25
        self.SOFT_BUY = 35
        self.OVERBOUGHT = 75
        self.SOFT_SELL = 65

        # Scoring weights
        self.WEIGHTS = {
            'htf_regime': 20,
            'location': 20,
            'momentum': 20,
            'trigger': 25,
            'volume': 15,
        }

        logger.info("🚀 SignalEngine v3.4.0 initialized")
        logger.info(f"  - Min Setup Score: {self.MIN_SETUP_SCORE}")
        logger.info(f"  - Min Trigger Score: {self.MIN_TRIGGER_SCORE}")
        logger.info(f"  - Counter-Trend Min: {self.COUNTER_TREND_MIN_SCORE}")

    def process(self, df: pd.DataFrame, ltf_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main processing pipeline.

        Returns:
            {
                'signal': 'BUY'/'SELL'/'NO_TRADE',
                'state': SignalState,
                'data': {...}
            }
        """
        try:
            # ===== STAGE 0: Data Validation =====
            if df is None or df.empty or len(df) < 50:
                return self._no_signal("Insufficient data")

            # ===== STAGE 1: HTF Regime =====
            regime_data = self._get_regime(df)
            self.current_regime = regime_data

            # ===== STAGE 2-3: Setup Detection =====
            setup_result = self._detect_setup(df, ltf_data, regime_data)

            if setup_result['setup_detected']:
                logger.info(f"📊 SETUP DETECTED: {setup_result['direction']} (Score: {setup_result['setup_score']})")

                # Arm the setup
                if self.state_machine.arm_setup():
                    logger.info(f"🔫 SETUP ARMED: Waiting for trigger...")

                    # ===== STAGE 5: Trigger Detection =====
                    trigger_result = self._detect_trigger(df, setup_result)

                    if trigger_result['trigger_detected']:
                        logger.info(f"🎯 TRIGGER DETECTED: {trigger_result['direction']} (Score: {trigger_result['trigger_score']})")

                        # ===== STAGE 6: LTF Confirmation =====
                        if self.state_machine.confirm(ltf_data):
                            logger.info(f"✅ CONFIRMED: Ready for entry")

                            # ===== STAGE 9-11: Entry Validation & Signal =====
                            return self._generate_final_signal(
                                df, setup_result, trigger_result, regime_data
                            )

            # No signal
            return self._no_signal(
                setup_result.get('reason', 'No setup detected')
            )

        except Exception as e:
            logger.error(f"❌ SignalEngine error: {e}")
            return self._no_signal(f"Error: {str(e)}")

    def _get_regime(self, df: pd.DataFrame) -> RegimeData:
        """Get HTF regime from available data."""
        # Try to get 4H and 1H data from cached values
        # In practice, you'd fetch these separately
        # For now, use the current timeframe as proxy

        df_4h = df  # Placeholder - use actual 4H data
        df_1h = df  # Placeholder - use actual 1H data

        return self.regime_analyzer.analyze(df_4h, df_1h)

    def _detect_setup(self, df: pd.DataFrame, ltf_data: Dict[str, Any],
                      regime_data: RegimeData) -> Dict[str, Any]:
        """
        Detect setup conditions.

        Returns:
            {
                'setup_detected': bool,
                'direction': str,
                'setup_score': int,
                'tdi_level': float,
                'tdi_zone': str,
                'bb_position': float,
                'divergence_detected': bool,
                'candle_pattern': str,
                'sr_confirmed': bool,
                'reason': str
            }
        """
        result = {
            'setup_detected': False,
            'direction': 'NONE',
            'setup_score': 0,
            'tdi_level': 50,
            'tdi_zone': 'NEUTRAL',
            'bb_position': 0.5,
            'divergence_detected': False,
            'candle_pattern': 'NONE',
            'sr_confirmed': False,
            'bb_squeeze': False,
            'session': 'UNKNOWN',
            'reason': 'No setup conditions met'
        }

        try:
            # Get last candle data
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            # TDI values
            tdi_slow = last.get('tdi_slow_ma', 50)
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_zone = self._get_tdi_zone(tdi_slow)

            # BB position
            bb_position = last.get('bb_position', 0.5)
            bb_lower = last.get('bb_lower', 0)
            bb_upper = last.get('bb_upper', 0)
            ha_low = last.get('ha_low', last.get('low', 0))
            ha_high = last.get('ha_high', last.get('high', 0))

            # Volume
            volume_ratio = last.get('volume_ratio', 1.0)

            # New features
            divergence_bullish = last.get('divergence_bullish', False)
            divergence_bearish = last.get('divergence_bearish', False)
            candle_pattern = last.get('candle_pattern', 'NONE')
            bb_squeeze = last.get('bb_squeeze', False)

            # S/R
            nearest_support = last.get('nearest_support', 0)
            nearest_resistance = last.get('nearest_resistance', 0)

            # Session
            session = get_trading_session()

            # Check BUY setup
            buy_result = self._check_buy_setup(
                df, last, prev, tdi_slow, tdi_zone, bb_position,
                volume_ratio, divergence_bullish, candle_pattern,
                nearest_support, bb_squeeze, session, regime_data
            )

            if buy_result['setup_detected']:
                return {**result, **buy_result}

            # Check SELL setup
            sell_result = self._check_sell_setup(
                df, last, prev, tdi_slow, tdi_zone, bb_position,
                volume_ratio, divergence_bearish, candle_pattern,
                nearest_resistance, bb_squeeze, session, regime_data
            )

            if sell_result['setup_detected']:
                return {**result, **sell_result}

            return result

        except Exception as e:
            logger.error(f"Setup detection error: {e}")
            return result

    def _check_buy_setup(self, df, last, prev, tdi_slow, tdi_zone, bb_position,
                         volume_ratio, divergence, candle_pattern,
                         nearest_support, bb_squeeze, session,
                         regime_data: RegimeData) -> Dict[str, Any]:
        """Check BUY setup conditions."""
        result = {'setup_detected': False, 'direction': 'NONE'}

        # ===== Hard Gates =====
        # 1. HTF Regime
        if not regime_data.is_bullish and regime_data.regime != Regime.CONFLICT:
            result['reason'] = 'HTF not bullish'
            return result

        # 2. Location: Near support or BB lower
        current_price = last.get('close', 0)
        near_support = False
        if nearest_support > 0 and current_price > 0:
            near_support = (current_price - nearest_support) / current_price < 0.02

        if not near_support and bb_position > 0.3:
            result['reason'] = 'Not near support/BB lower'
            return result

        # 3. TDI Zone
        if tdi_zone not in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE']:
            result['reason'] = f'TDI zone {tdi_zone} not buyable'
            return result

        # ===== Setup Score =====
        score = 0

        # HTF Regime (20 pts)
        if regime_data.regime == Regime.STRONG_BULL:
            score += 20
        elif regime_data.regime in [Regime.BULL, Regime.MILD_BULL]:
            score += 15

        # Location (20 pts)
        if near_support:
            score += 15
        if bb_position < 0.15:
            score += 10
        elif bb_position < 0.30:
            score += 5

        # TDI Zone (15 pts)
        if tdi_zone == 'OVERSOLD':
            score += 15
        elif tdi_zone == 'SOFT_BUY':
            score += 10
        elif tdi_zone == 'BUY_ZONE':
            score += 5

        # Divergence (15 pts)
        if divergence:
            score += 15

        # Candle Pattern (10 pts)
        if candle_pattern in ['BULLISH_ENGULFING', 'MORNING_STAR', 'HAMMER']:
            score += 10

        # BB Squeeze (5 pts)
        if bb_squeeze:
            score += 5

        # Volume (15 pts) - as setup confirmation
        if volume_ratio > 1.3:
            score += 15
        elif volume_ratio > 1.0:
            score += 10

        # ===== Counter-Trend Check =====
        is_counter_trend = regime_data.regime in [Regime.BEAR, Regime.STRONG_BEAR, Regime.CONFLICT]
        min_score = self.COUNTER_TREND_MIN_SCORE if is_counter_trend else self.MIN_SETUP_SCORE

        if score >= min_score:
            result.update({
                'setup_detected': True,
                'direction': 'BUY',
                'setup_score': min(100, score),
                'tdi_level': tdi_slow,
                'tdi_zone': tdi_zone,
                'bb_position': bb_position,
                'divergence_detected': divergence,
                'candle_pattern': candle_pattern,
                'sr_confirmed': near_support,
                'bb_squeeze': bb_squeeze,
                'session': session,
                'reason': f'BUY setup score: {score}/100'
            })

        return result

    def _check_sell_setup(self, df, last, prev, tdi_slow, tdi_zone, bb_position,
                          volume_ratio, divergence, candle_pattern,
                          nearest_resistance, bb_squeeze, session,
                          regime_data: RegimeData) -> Dict[str, Any]:
        """Check SELL setup conditions."""
        result = {'setup_detected': False, 'direction': 'NONE'}

        # ===== Hard Gates =====
        # 1. HTF Regime
        if not regime_data.is_bearish and regime_data.regime != Regime.CONFLICT:
            result['reason'] = 'HTF not bearish'
            return result

        # 2. Location: Near resistance or BB upper
        current_price = last.get('close', 0)
        near_resistance = False
        if nearest_resistance > 0 and current_price > 0:
            near_resistance = (nearest_resistance - current_price) / current_price < 0.02

        if not near_resistance and bb_position < 0.7:
            result['reason'] = 'Not near resistance/BB upper'
            return result

        # 3. TDI Zone
        if tdi_zone not in ['OVERBOUGHT', 'SOFT_SELL']:
            result['reason'] = f'TDI zone {tdi_zone} not sellable'
            return result

        # ===== Setup Score =====
        score = 0

        # HTF Regime (20 pts)
        if regime_data.regime == Regime.STRONG_BEAR:
            score += 20
        elif regime_data.regime in [Regime.BEAR, Regime.MILD_BEAR]:
            score += 15

        # Location (20 pts)
        if near_resistance:
            score += 15
        if bb_position > 0.85:
            score += 10
        elif bb_position > 0.70:
            score += 5

        # TDI Zone (15 pts)
        if tdi_zone == 'OVERBOUGHT':
            score += 15
        elif tdi_zone == 'SOFT_SELL':
            score += 10

        # Divergence (15 pts)
        if divergence:
            score += 15

        # Candle Pattern (10 pts)
        if candle_pattern in ['BEARISH_ENGULFING', 'EVENING_STAR', 'SHOOTING_STAR']:
            score += 10

        # BB Squeeze (5 pts)
        if bb_squeeze:
            score += 5

        # Volume (15 pts)
        if volume_ratio > 1.3:
            score += 15
        elif volume_ratio > 1.0:
            score += 10

        # ===== Counter-Trend Check =====
        is_counter_trend = regime_data.regime in [Regime.BULL, Regime.STRONG_BULL, Regime.CONFLICT]
        min_score = self.COUNTER_TREND_MIN_SCORE if is_counter_trend else self.MIN_SETUP_SCORE

        if score >= min_score:
            result.update({
                'setup_detected': True,
                'direction': 'SELL',
                'setup_score': min(100, score),
                'tdi_level': tdi_slow,
                'tdi_zone': tdi_zone,
                'bb_position': bb_position,
                'divergence_detected': divergence,
                'candle_pattern': candle_pattern,
                'sr_confirmed': near_resistance,
                'bb_squeeze': bb_squeeze,
                'session': session,
                'reason': f'SELL setup score: {score}/100'
            })

        return result

    def _detect_trigger(self, df: pd.DataFrame, setup_result: Dict[str, Any]) -> Dict[str, Any]:
        """Detect trigger conditions (TDI cross + candle + structure)."""
        result = {
            'trigger_detected': False,
            'direction': 'NONE',
            'trigger_score': 0,
            'tdi_cross': 'NONE',
            'tdi_slope': 'FLAT',
            'candle_bullish': False,
            'candle_bearish': False,
            'structure_break': False,
            'reason': 'No trigger conditions met'
        }

        try:
            # Get last candles
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last
            prev2 = df.iloc[-3] if len(df) > 2 else prev

            direction = setup_result.get('direction', 'NONE')
            if direction == 'NONE':
                return result

            # TDI values
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_slow = last.get('tdi_slow_ma', 50)
            tdi_fast_prev = prev.get('tdi_fast_ma', 50)
            tdi_slow_prev = prev.get('tdi_slow_ma', 50)

            # TDI Cross
            if tdi_fast > tdi_slow and tdi_fast_prev <= tdi_slow_prev:
                tdi_cross = 'BULLISH'
            elif tdi_fast < tdi_slow and tdi_fast_prev >= tdi_slow_prev:
                tdi_cross = 'BEARISH'
            else:
                tdi_cross = 'NONE'

            # TDI Slope (using 3-period slope)
            tdi_slope = self._calculate_slope(df['tdi_slow_ma'].values[-5:]) if 'tdi_slow_ma' in df.columns else 'FLAT'

            # Candle patterns
            candle_bullish = last.get('ha_color', 0) == 1
            candle_bearish = last.get('ha_color', 0) == -1

            # Candle break (break of trigger candle high/low)
            prev_high = prev.get('high', 0)
            prev_low = prev.get('low', 0)
            current_close = last.get('close', 0)

            bullish_break = direction == 'BUY' and current_close > prev_high
            bearish_break = direction == 'SELL' and current_close < prev_low

            # Structure
            structure = self.structure_analyzer.analyze(df)
            self.current_structure = structure

            # Volume
            volume_ratio = last.get('volume_ratio', 1.0)

            # ===== Trigger Score =====
            score = 0

            # TDI Cross (20 pts)
            if direction == 'BUY' and tdi_cross == 'BULLISH':
                score += 20
            elif direction == 'SELL' and tdi_cross == 'BEARISH':
                score += 20
            elif tdi_cross != 'NONE':
                score += 10

            # TDI Slope (10 pts)
            if direction == 'BUY' and tdi_slope == 'POSITIVE':
                score += 10
            elif direction == 'SELL' and tdi_slope == 'NEGATIVE':
                score += 10
            elif tdi_slope != 'FLAT':
                score += 5

            # Candle (15 pts)
            if direction == 'BUY' and candle_bullish:
                score += 15
            elif direction == 'SELL' and candle_bearish:
                score += 15

            # Break (15 pts)
            if bullish_break or bearish_break:
                score += 15

            # HA Reversal (10 pts)
            ha_color = last.get('ha_color', 0)
            ha_prev_color = prev.get('ha_color', 0)
            if ha_color != ha_prev_color:
                score += 10

            # Structure (15 pts)
            if direction == 'BUY' and (structure.support_reclaim or structure.bos):
                score += 15
            elif direction == 'SELL' and (structure.resistance_rejection or structure.bos):
                score += 15
            elif structure.bos or structure.choch:
                score += 10

            # Volume (15 pts)
            if volume_ratio > 1.5:
                score += 15
            elif volume_ratio > 1.0:
                score += 10
            elif volume_ratio > 0.7:
                score += 5

            min_score = self.MIN_TRIGGER_SCORE
            if score >= min_score:
                result.update({
                    'trigger_detected': True,
                    'direction': direction,
                    'trigger_score': min(100, score),
                    'tdi_cross': tdi_cross,
                    'tdi_slope': tdi_slope,
                    'candle_bullish': candle_bullish,
                    'candle_bearish': candle_bearish,
                    'structure_break': structure.bos or structure.choch,
                    'reason': f'Trigger score: {score}/100'
                })

            return result

        except Exception as e:
            logger.error(f"Trigger detection error: {e}")
            return result

    def _calculate_slope(self, values: np.ndarray, lookback: int = 3) -> str:
        """Calculate slope of values."""
        if len(values) < lookback:
            return 'FLAT'

        recent = values[-lookback:]
        slope = (recent[-1] - recent[0]) / lookback

        if slope > 0.5:
            return 'POSITIVE'
        elif slope < -0.5:
            return 'NEGATIVE'
        else:
            return 'FLAT'

    def _generate_final_signal(self, df: pd.DataFrame, setup_result: Dict[str, Any],
                               trigger_result: Dict[str, Any], regime_data: RegimeData) -> Dict[str, Any]:
        """Generate final signal with entry validation."""
        try:
            last = df.iloc[-1]
            current_price = last.get('close', 0)

            # Calculate ATR
            atr = self._calculate_atr(df)

            # Ideal entry price (from setup)
            if setup_result['direction'] == 'BUY':
                ideal_entry = setup_result.get('nearest_support', current_price * 0.998)
                stop_loss = ideal_entry * 0.995
                take_profit = ideal_entry * 1.025
            else:
                ideal_entry = setup_result.get('nearest_resistance', current_price * 1.002)
                stop_loss = ideal_entry * 1.005
                take_profit = ideal_entry * 0.975

            # Validate entry distance
            distance_atr = abs(current_price - ideal_entry) / atr if atr > 0 else 0

            if distance_atr > 0.25:
                logger.info(f"❌ Entry too far: {distance_atr:.2f} ATR (max 0.25)")
                return self._no_signal("Entry too far from ideal")

            # Calculate final score
            final_score = self._calculate_final_score(
                setup_result, trigger_result, regime_data
            )

            # Determine grade
            if final_score >= 90:
                grade = "A+"
            elif final_score >= 82:
                grade = "A"
            elif final_score >= 75:
                grade = "B+"
            elif final_score >= 70:
                grade = "B"
            else:
                grade = "C"

            # Generate signal
            signal_data = {
                'signal': setup_result['direction'],
                'state': SignalState.ENTRY_VALID.value,
                'direction': setup_result['direction'],
                'entry_price': current_price,
                'ideal_entry': ideal_entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'final_score': final_score,
                'grade': grade,
                'setup_score': setup_result.get('setup_score', 0),
                'trigger_score': trigger_result.get('trigger_score', 0),
                'tdi_level': setup_result.get('tdi_level', 50),
                'tdi_zone': setup_result.get('tdi_zone', 'NEUTRAL'),
                'divergence_detected': setup_result.get('divergence_detected', False),
                'candle_pattern': setup_result.get('candle_pattern', 'NONE'),
                'sr_confirmed': setup_result.get('sr_confirmed', False),
                'bb_squeeze': setup_result.get('bb_squeeze', False),
                'session': setup_result.get('session', 'UNKNOWN'),
                'regime': regime_data.regime.value,
                'structure': self.current_structure.structure_direction if self.current_structure else 'NEUTRAL',
                'timestamp': datetime.now().isoformat(),
                'version': '3.4.0'
            }

            logger.info(f"🎯 SIGNAL GENERATED: {setup_result['direction']} {grade} (Score: {final_score}/100)")

            return {
                'signal': setup_result['direction'],
                'state': SignalState.ENTRY_VALID.value,
                'data': signal_data
            }

        except Exception as e:
            logger.error(f"Final signal generation error: {e}")
            return self._no_signal(f"Error: {str(e)}")

    def _calculate_final_score(self, setup_result: Dict, trigger_result: Dict,
                               regime_data: RegimeData) -> int:
        """Calculate final signal score."""
        score = 0

        # Setup quality (30%)
        score += setup_result.get('setup_score', 0) * 0.30

        # Trigger quality (30%)
        score += trigger_result.get('trigger_score', 0) * 0.30

        # HTF Regime alignment (20%)
        regime_weight = self.regime_analyzer.get_regime_weight()
        score += regime_weight * 20

        # Structure confirmation (10%)
        if self.current_structure:
            if self.current_structure.bos or self.current_structure.choch:
                score += 10
            elif self.current_structure.liquidity_sweep:
                score += 5
            elif self.current_structure.support_reclaim or self.current_structure.resistance_rejection:
                score += 5

        # Divergence bonus (5%)
        if setup_result.get('divergence_detected', False):
            score += 5

        # Candle pattern bonus (5%)
        if setup_result.get('candle_pattern', 'NONE') != 'NONE':
            score += 5

        return min(100, int(score))

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR."""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            tr1 = high - low
            tr2 = np.abs(high - np.roll(close, 1))
            tr3 = np.abs(low - np.roll(close, 1))
            tr = np.maximum(tr1, np.maximum(tr2, tr3))

            return np.mean(tr[-period:]) if len(tr) >= period else 0

        except Exception as e:
            return df['close'].iloc[-1] * 0.01

    def _get_tdi_zone(self, tdi_value: float) -> str:
        """Get standardized TDI zone."""
        if tdi_value <= self.OVERSOLD:
            return 'OVERSOLD'
        elif tdi_value <= self.SOFT_BUY:
            return 'SOFT_BUY'
        elif tdi_value < 50:
            return 'BUY_ZONE'
        elif tdi_value < self.SOFT_SELL:
            return 'NO_TRADE'
        elif tdi_value < self.OVERBOUGHT:
            return 'SOFT_SELL'
        else:
            return 'OVERBOUGHT'

    def _no_signal(self, reason: str) -> Dict[str, Any]:
        """Return no signal response."""
        return {
            'signal': 'NO_TRADE',
            'state': self.state_machine.state.value,
            'data': {
                'reason': reason,
                'version': '3.4.0'
            }
        }


# Singleton
signal_engine = SignalEngineV34()
