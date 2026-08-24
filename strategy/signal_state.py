"""
Signal State Machine - Manages signal lifecycle
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


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


@dataclass
class SetupData:
    """Setup detection data."""
    direction: str
    tdi_level: float
    tdi_zone: str
    bb_position: float
    setup_score: int
    setup_reason: str
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class TriggerData:
    """Trigger detection data."""
    tdi_fast: float
    tdi_slow: float
    tdi_cross: str
    candle_pattern: str
    structure_break: bool
    trigger_score: int
    triggered_at: datetime = field(default_factory=datetime.now)


class SignalStateMachine:
    """
    Signal State Machine.
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
        self.MAX_SETUP_AGE_SECONDS = 300
        self.MAX_TRIGGER_AGE_SECONDS = 120
        self.REQUIRED_CONFIRMATIONS = 2

    def transition(self, new_state: SignalState) -> bool:
        """Transition to new state if valid."""
        valid_transitions = {
            SignalState.NO_SETUP: [SignalState.SETUP_DETECTED],
            SignalState.SETUP_DETECTED: [SignalState.ARMED, SignalState.INVALIDATED, SignalState.EXPIRED],
            SignalState.ARMED: [SignalState.TRIGGER_DETECTED, SignalState.INVALIDATED, SignalState.EXPIRED],
            SignalState.TRIGGER_DETECTED: [SignalState.CONFIRMING, SignalState.INVALIDATED],
            SignalState.CONFIRMING: [SignalState.SIGNAL_READY, SignalState.INVALIDATED],
            SignalState.SIGNAL_READY: [SignalState.ENTRY_VALID, SignalState.EXPIRED],
            SignalState.ENTRY_VALID: [SignalState.ACTIVE],
            SignalState.ACTIVE: [SignalState.TP1_HIT, SignalState.TP2_HIT, SignalState.SL_HIT],
        }

        if new_state not in valid_transitions.get(self.state, []):
            if new_state in [SignalState.INVALIDATED, SignalState.EXPIRED]:
                pass  # Allow forced transitions
            else:
                return False

        self.state = new_state
        return True

    def reset(self):
        """Reset the state machine."""
        self.state = SignalState.NO_SETUP
        self.setup = None
        self.trigger = None
        self.entry_price = None
        self.entry_time = None
        self.expiry_time = None
        self.confirmation_count = 0

    def is_ready(self) -> bool:
        """Check if state machine is ready to generate signal."""
        return self.state == SignalState.ENTRY_VALID
