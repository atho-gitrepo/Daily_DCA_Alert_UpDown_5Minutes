# strategy/signal_state.py
"""
Signal State Machine - v3.4.0
Separates setup from signal with proper state management.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


class SignalState(Enum):
    """Signal lifecycle states."""
    NO_SETUP = "NO_SETUP"
    SETUP_DETECTED = "SETUP_DETECTED"
    ARMED = "ARMED"
    TRIGGER_DETECTED = "TRIGGER_DETECTED"
    CONFIRMING = "CONFIRMING"
    SIGNAL_READY = "SIGNAL_READY"
    ENTRY_VALID = "ENTRY_VALID"
    ACTIVE = "ACTIVE"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    MISSED = "MISSED"


@dataclass
class SetupData:
    """Setup detection data."""
    direction: str  # "BUY" or "SELL"
    tdi_level: float
    tdi_zone: str
    bb_position: float
    support_level: float
    resistance_level: float
    setup_score: int
    setup_reason: str
    detected_at: datetime = field(default_factory=datetime.now)
    divergence_detected: bool = False
    candle_pattern: str = "NONE"
    sr_confirmed: bool = False
    bb_squeeze: bool = False
    session: str = "UNKNOWN"


@dataclass
class TriggerData:
    """Trigger detection data."""
    tdi_fast: float
    tdi_slow: float
    tdi_cross: str  # "BULLISH", "BEARISH", "NONE"
    tdi_slope: str  # "POSITIVE", "NEGATIVE", "FLAT"
    candle_pattern: str
    structure_break: bool
    volume_ratio: float
    trigger_score: int
    triggered_at: datetime = field(default_factory=datetime.now)


class SignalStateMachine:
    """
    v3.4.0 Signal State Machine.
    Setup ≠ Signal - requires setup + trigger + confirmation.
    """

    def __init__(self):
        self.state = SignalState.NO_SETUP
        self.setup: Optional[SetupData] = None
        self.trigger: Optional[TriggerData] = None
        self.entry_price: Optional[float] = None
        self.entry_time: Optional[datetime] = None
        self.expiry_time: Optional[datetime] = None
        self.confirmation_count: int = 0

        # Configuration
        self.MAX_SETUP_AGE_SECONDS = 300  # 5 minutes
        self.MAX_TRIGGER_AGE_SECONDS = 120  # 2 minutes
        self.REQUIRED_CONFIRMATIONS = 2
        self.MAX_ENTRY_DISTANCE_ATR = 0.25  # 25% of ATR

    def transition(self, new_state: SignalState) -> bool:
        """Transition to new state if valid."""
        valid_transitions = {
            SignalState.NO_SETUP: [SignalState.SETUP_DETECTED],
            SignalState.SETUP_DETECTED: [SignalState.ARMED, SignalState.INVALIDATED, SignalState.EXPIRED],
            SignalState.ARMED: [SignalState.TRIGGER_DETECTED, SignalState.INVALIDATED, SignalState.EXPIRED],
            SignalState.TRIGGER_DETECTED: [SignalState.CONFIRMING, SignalState.INVALIDATED],
            SignalState.CONFIRMING: [SignalState.SIGNAL_READY, SignalState.INVALIDATED],
            SignalState.SIGNAL_READY: [SignalState.ENTRY_VALID, SignalState.EXPIRED, SignalState.MISSED],
            SignalState.ENTRY_VALID: [SignalState.ACTIVE, SignalState.EXPIRED, SignalState.MISSED],
            SignalState.ACTIVE: [SignalState.TP1_HIT, SignalState.TP2_HIT, SignalState.SL_HIT],
        }

        if new_state not in valid_transitions.get(self.state, []):
            if new_state == SignalState.INVALIDATED and self.state != SignalState.NO_SETUP:
                # Allow invalidation from any non-NO_SETUP state
                pass
            elif new_state == SignalState.EXPIRED and self.state not in [SignalState.NO_SETUP, SignalState.ACTIVE]:
                # Allow expiry from setup/armed/ready states
                pass
            else:
                return False

        self.state = new_state
        return True

    def detect_setup(self, data: Dict[str, Any]) -> bool:
        """
        Stage 2: Setup detection.
        Returns True if a valid setup is detected.
        """
        # Hard gates for setup
        if not self._validate_htf_regime(data):
            return False

        if not self._validate_location(data):
            return False

        if not self._validate_tdi_setup(data):
            return False

        # Calculate setup score
        setup_score = self._calculate_setup_score(data)

        if setup_score < 70:
            return False

        self.setup = SetupData(
            direction=data.get('direction', 'NONE'),
            tdi_level=data.get('tdi_level', 50),
            tdi_zone=data.get('tdi_zone', 'NEUTRAL'),
            bb_position=data.get('bb_position', 0.5),
            support_level=data.get('nearest_support', 0),
            resistance_level=data.get('nearest_resistance', 0),
            setup_score=setup_score,
            setup_reason=data.get('reason', ''),
            divergence_detected=data.get('divergence_detected', False),
            candle_pattern=data.get('candle_pattern', 'NONE'),
            sr_confirmed=data.get('sr_confirmed', False),
            bb_squeeze=data.get('bb_squeeze', False),
            session=data.get('session', 'UNKNOWN'),
        )

        self.expiry_time = datetime.now() + timedelta(seconds=self.MAX_SETUP_AGE_SECONDS)
        return self.transition(SignalState.SETUP_DETECTED)

    def arm_setup(self) -> bool:
        """Stage 4: Arm the setup - ready for trigger."""
        if self.state != SignalState.SETUP_DETECTED:
            return False

        # Check freshness
        if self._is_expired():
            self.transition(SignalState.EXPIRED)
            return False

        return self.transition(SignalState.ARMED)

    def detect_trigger(self, data: Dict[str, Any]) -> bool:
        """
        Stage 5: Trigger detection.
        Requires TDI cross + candle confirmation + structure.
        """
        if self.state not in [SignalState.ARMED, SignalState.SETUP_DETECTED]:
            return False

        if self._is_expired():
            self.transition(SignalState.EXPIRED)
            return False

        # Hard gates for trigger
        if not self._validate_tdi_cross(data):
            return False

        if not self._validate_candle_confirmation(data):
            return False

        if not self._validate_structure(data):
            return False

        # Calculate trigger score
        trigger_score = self._calculate_trigger_score(data)

        if trigger_score < 70:
            return False

        self.trigger = TriggerData(
            tdi_fast=data.get('tdi_fast', 50),
            tdi_slow=data.get('tdi_slow', 50),
            tdi_cross=data.get('tdi_cross', 'NONE'),
            tdi_slope=data.get('tdi_slope', 'FLAT'),
            candle_pattern=data.get('candle_pattern', 'NONE'),
            structure_break=data.get('structure_break', False),
            volume_ratio=data.get('volume_ratio', 1.0),
            trigger_score=trigger_score,
            triggered_at=datetime.now(),
        )

        return self.transition(SignalState.TRIGGER_DETECTED)

    def confirm(self, data: Dict[str, Any]) -> bool:
        """
        Stage 6: LTF confirmation.
        Requires 5M confirmation candle.
        """
        if self.state != SignalState.TRIGGER_DETECTED:
            return False

        self.confirmation_count += 1

        if self.confirmation_count >= self.REQUIRED_CONFIRMATIONS:
            self.transition(SignalState.SIGNAL_READY)
            return True

        self.transition(SignalState.CONFIRMING)
        return True

    def validate_entry(self, current_price: float, atr: float, ideal_price: float) -> bool:
        """
        Stage 9: Entry validation.
        Check distance from ideal entry.
        """
        if self.state != SignalState.SIGNAL_READY:
            return False

        if self._is_expired():
            self.transition(SignalState.EXPIRED)
            return False

        distance = abs(current_price - ideal_price) / atr if atr > 0 else 0

        if distance > self.MAX_ENTRY_DISTANCE_ATR:
            self.transition(SignalState.MISSED)
            return False

        self.entry_price = current_price
        self.entry_time = datetime.now()
        self.transition(SignalState.ENTRY_VALID)
        return True

    def generate_signal(self) -> Optional[Dict[str, Any]]:
        """Stage 11: Generate final signal."""
        if self.state != SignalState.ENTRY_VALID:
            return None

        if self._is_expired():
            self.transition(SignalState.EXPIRED)
            return None

        return {
            'state': self.state.value,
            'direction': self.setup.direction if self.setup else 'NONE',
            'entry_price': self.entry_price,
            'setup_score': self.setup.setup_score if self.setup else 0,
            'trigger_score': self.trigger.trigger_score if self.trigger else 0,
            'tdi_level': self.setup.tdi_level if self.setup else 50,
            'tdi_zone': self.setup.tdi_zone if self.setup else 'NEUTRAL',
            'divergence_detected': self.setup.divergence_detected if self.setup else False,
            'candle_pattern': self.setup.candle_pattern if self.setup else 'NONE',
            'sr_confirmed': self.setup.sr_confirmed if self.setup else False,
            'bb_squeeze': self.setup.bb_squeeze if self.setup else False,
            'session': self.setup.session if self.setup else 'UNKNOWN',
        }

    def _validate_htf_regime(self, data: Dict[str, Any]) -> bool:
        """Validate HTF regime filter."""
        htf_4h = data.get('htf_4h', 'NEUTRAL')
        htf_1h = data.get('htf_1h', 'NEUTRAL')
        direction = data.get('direction', 'NONE')

        # Check HTF alignment with direction
        if direction == 'BUY':
            if htf_4h == 'BEARISH' and htf_1h == 'BEARISH':
                # Strong Bear - counter-trend needs special handling
                return data.get('counter_trend_allowed', False)
            return htf_4h in ['BULLISH', 'NEUTRAL'] or htf_1h in ['BULLISH', 'NEUTRAL']

        if direction == 'SELL':
            if htf_4h == 'BULLISH' and htf_1h == 'BULLISH':
                # Strong Bull - counter-trend needs special handling
                return data.get('counter_trend_allowed', False)
            return htf_4h in ['BEARISH', 'NEUTRAL'] or htf_1h in ['BEARISH', 'NEUTRAL']

        return True

    def _validate_location(self, data: Dict[str, Any]) -> bool:
        """Validate price location (S/R, BB)."""
        direction = data.get('direction', 'NONE')
        bb_position = data.get('bb_position', 0.5)
        nearest_support = data.get('nearest_support', 0)
        nearest_resistance = data.get('nearest_resistance', 0)
        current_price = data.get('current_price', 0)

        if direction == 'BUY':
            # Price near support or BB lower
            near_support = False
            if nearest_support > 0 and current_price > 0:
                near_support = (current_price - nearest_support) / current_price < 0.02

            near_bb_lower = bb_position < 0.25

            return near_support or near_bb_lower

        if direction == 'SELL':
            # Price near resistance or BB upper
            near_resistance = False
            if nearest_resistance > 0 and current_price > 0:
                near_resistance = (nearest_resistance - current_price) / current_price < 0.02

            near_bb_upper = bb_position > 0.75

            return near_resistance or near_bb_upper

        return False

    def _validate_tdi_setup(self, data: Dict[str, Any]) -> bool:
        """Validate TDI setup conditions."""
        direction = data.get('direction', 'NONE')
        tdi_level = data.get('tdi_level', 50)
        tdi_zone = data.get('tdi_zone', 'NEUTRAL')

        if direction == 'BUY':
            return tdi_zone in ['OVERSOLD', 'SOFT_BUY', 'BUY_ZONE']

        if direction == 'SELL':
            return tdi_zone in ['OVERBOUGHT', 'SOFT_SELL']

        return False

    def _validate_tdi_cross(self, data: Dict[str, Any]) -> bool:
        """Validate TDI crossover."""
        tdi_cross = data.get('tdi_cross', 'NONE')
        direction = data.get('direction', 'NONE')

        if direction == 'BUY':
            return tdi_cross == 'BULLISH'

        if direction == 'SELL':
            return tdi_cross == 'BEARISH'

        return False

    def _validate_candle_confirmation(self, data: Dict[str, Any]) -> bool:
        """Validate candle confirmation."""
        direction = data.get('direction', 'NONE')
        candle_bullish = data.get('candle_bullish', False)
        candle_bearish = data.get('candle_bearish', False)
        candle_break = data.get('candle_break', False)

        if direction == 'BUY':
            return candle_bullish and candle_break

        if direction == 'SELL':
            return candle_bearish and candle_break

        return False

    def _validate_structure(self, data: Dict[str, Any]) -> bool:
        """Validate market structure."""
        direction = data.get('direction', 'NONE')
        bos = data.get('bos', False)
        choch = data.get('choch', False)
        reclaim = data.get('reclaim', False)

        if direction == 'BUY':
            return reclaim or bos or choch

        if direction == 'SELL':
            return reclaim or bos or choch

        return False

    def _calculate_setup_score(self, data: Dict[str, Any]) -> int:
        """Calculate setup score (0-100)."""
        score = 0

        # HTF regime (20 points)
        htf_4h = data.get('htf_4h', 'NEUTRAL')
        htf_1h = data.get('htf_1h', 'NEUTRAL')
        if htf_4h in ['BULLISH', 'BEARISH'] and htf_1h in ['BULLISH', 'BEARISH']:
            score += 20
        elif htf_4h != 'NEUTRAL' or htf_1h != 'NEUTRAL':
            score += 10

        # Location (20 points)
        bb_position = data.get('bb_position', 0.5)
        if bb_position < 0.15 or bb_position > 0.85:
            score += 20
        elif bb_position < 0.30 or bb_position > 0.70:
            score += 15
        elif bb_position < 0.45 or bb_position > 0.55:
            score += 5

        # TDI zone (15 points)
        tdi_zone = data.get('tdi_zone', 'NEUTRAL')
        if tdi_zone in ['OVERSOLD', 'OVERBOUGHT']:
            score += 15
        elif tdi_zone in ['SOFT_BUY', 'SOFT_SELL']:
            score += 10
        elif tdi_zone in ['BUY_ZONE']:
            score += 5

        # Divergence bonus (15 points)
        if data.get('divergence_detected', False):
            score += 15

        # Candle pattern bonus (10 points)
        if data.get('candle_pattern') and data.get('candle_pattern') != 'NONE':
            score += 10

        # S/R confirmation (10 points)
        if data.get('sr_confirmed', False):
            score += 10

        # Momentum (10 points)
        if data.get('momentum_improving', False):
            score += 10

        return min(100, score)

    def _calculate_trigger_score(self, data: Dict[str, Any]) -> int:
        """Calculate trigger score (0-100)."""
        score = 0

        # TDI cross (20 points)
        if data.get('tdi_cross', 'NONE') != 'NONE':
            score += 20

        # TDI slope (10 points)
        if data.get('tdi_slope') in ['POSITIVE', 'NEGATIVE']:
            score += 10

        # Candle confirmation (15 points)
        if data.get('candle_bullish') or data.get('candle_bearish'):
            score += 15

        # Candle break (15 points)
        if data.get('candle_break', False):
            score += 15

        # HA reversal (10 points)
        if data.get('ha_reversal', False):
            score += 10

        # Volume (15 points)
        volume_ratio = data.get('volume_ratio', 1.0)
        if volume_ratio > 1.5:
            score += 15
        elif volume_ratio > 1.0:
            score += 10
        elif volume_ratio > 0.7:
            score += 5

        # Structure (15 points)
        if data.get('bos', False) or data.get('choch', False) or data.get('reclaim', False):
            score += 15

        return min(100, score)

    def _is_expired(self) -> bool:
        """Check if current state has expired."""
        if self.expiry_time is None:
            return False

        return datetime.now() > self.expiry_time

    def reset(self):
        """Reset the state machine."""
        self.state = SignalState.NO_SETUP
        self.setup = None
        self.trigger = None
        self.entry_price = None
        self.entry_time = None
        self.expiry_time = None
        self.confirmation_count = 0


# Singleton instance
signal_state_machine = SignalStateMachine()
