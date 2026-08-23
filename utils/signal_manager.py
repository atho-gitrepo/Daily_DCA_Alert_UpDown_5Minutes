"""
Signal Manager - Handles signal lifecycle, debouncing, and duplicate prevention
Version: 3.4.0 - UPDATED: Added v3.4.0 signal fields
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Tuple, List
from dataclasses import dataclass, field
from enum import Enum
import json
import traceback

# Import MongoDB client with fallback
try:
    from utils.mongodb_client import mongodb_client as db_client
except ImportError:
    db_client = None
    logging.warning("No database client available. Signal persistence disabled.")

logger = logging.getLogger(__name__)

EMOJI = {
    "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "INFO": "ℹ️",
    "SIGNAL": "📡", "PROFIT": "💰", "LOSS": "💸", "LOCK": "🔒",
    "UNLOCK": "🔓", "MONITOR": "📊", "WAIT": "⏳", "REJECT": "🚫",
    "RESTORE": "♻️", "BREAK": "⏹️", "LTF": "⏱️", "HTF": "📊",
    "CONFLICT": "⚔️", "ACTIVE": "🟢", "RESOLVED": "✅", "SCORE": "🎯",
    "COMPONENT": "📊", "GRADE_A": "🏆", "GRADE_B": "🥈", "GRADE_C": "🥉",
    "APPROVED": "✅", "DB": "💾", "MONGODB": "🍃",
    # v3.4.0
    "DIVERGENCE": "↩️", "PATTERN": "🕯️", "S_R": "📊", "SESSION": "🌍",
    "STRUCTURE": "🏗️", "REGIME": "📈", "STATE": "🔄",
}


class TradeLifecycle(str, Enum):
    """Trade lifecycle states."""
    ACTIVE = "ACTIVE"
    PROFIT = "PROFIT"
    LOSS = "LOSS"
    BREAK_EVEN = "BREAK_EVEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


@dataclass
class SignalData:
    """Signal data structure with v3.4.0 fields."""
    symbol: str
    signal_type: str
    entry_price: float
    entry_time: str
    stop_loss: float
    take_profit: float
    confidence: float
    status: str = "ACTIVE"
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pnl: float = 0.0
    pnl_percent: float = 0.0
    fees: float = 0.0

    # v3.3.0 fields
    tdi_level: float = 0.0
    tdi_zone: str = "NEUTRAL"
    rrr: float = 0.0
    signal_strength: str = "SOFT"
    risk_multiplier: float = 1.0
    ai_decision: str = "APPROVE"
    ai_confidence: float = 0.0
    ai_validated: bool = False
    quality_score: int = 50
    total_score: int = 0
    grade: str = ""
    ltf_confirmed: bool = False
    ltf_confidence: float = 0.0
    htf_trend: str = "NEUTRAL"
    htf_aligned: bool = False
    component_scores: Dict[str, float] = field(default_factory=dict)

    # v3.4.0 fields
    setup_score: int = 0
    trigger_score: int = 0
    final_score: int = 0
    entry_grade: str = ""
    state: str = "ACTIVE"
    regime: str = "NEUTRAL"
    structure_direction: str = "NEUTRAL"
    entry_distance_atr: float = 0.0
    ideal_entry: float = 0.0
    atr: float = 0.0

    # Feature flags
    divergence_detected: bool = False
    divergence_type: str = ""
    divergence_strength: float = 0.0
    candle_pattern: str = "NONE"
    candle_pattern_confidence: float = 0.0
    sr_confirmed: bool = False
    sr_position: str = ""
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    bb_squeeze: bool = False
    bb_squeeze_strength: float = 0.0
    session: str = "UNKNOWN"
    session_multiplier: float = 1.0

    raw_data: Dict = field(default_factory=dict)
    bar_count: int = 0
    min_bars_before_check: int = 2
    min_age_seconds_before_check: int = 120
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None
    restored_from_db: bool = False
    db_doc_id: Optional[str] = None
    last_checked_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence": self.confidence,
            "status": self.status,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "fees": self.fees,
            "tdi_level": self.tdi_level,
            "tdi_zone": self.tdi_zone,
            "rrr": self.rrr,
            "signal_strength": self.signal_strength,
            "risk_multiplier": self.risk_multiplier,
            "quality_score": self.quality_score,
            "total_score": self.total_score,
            "grade": self.grade,
            "ltf_confirmed": self.ltf_confirmed,
            "ltf_confidence": self.ltf_confidence,
            "htf_trend": self.htf_trend,
            "htf_aligned": self.htf_aligned,
            "component_scores": self.component_scores,
            # v3.4.0
            "setup_score": self.setup_score,
            "trigger_score": self.trigger_score,
            "final_score": self.final_score,
            "entry_grade": self.entry_grade,
            "state": self.state,
            "regime": self.regime,
            "structure_direction": self.structure_direction,
            "entry_distance_atr": self.entry_distance_atr,
            "ideal_entry": self.ideal_entry,
            "atr": self.atr,
            # Features
            "divergence_detected": self.divergence_detected,
            "divergence_type": self.divergence_type,
            "candle_pattern": self.candle_pattern,
            "sr_confirmed": self.sr_confirmed,
            "bb_squeeze": self.bb_squeeze,
            "session": self.session,
            "session_multiplier": self.session_multiplier,
            "bars_held": self.bar_count,
            "restored": self.restored_from_db,
            "db_doc_id": self.db_doc_id,
        }

    def get_age_minutes(self) -> float:
        try:
            entry_time = datetime.fromisoformat(self.entry_time)
            return (datetime.now() - entry_time).total_seconds() / 60
        except (ValueError, TypeError):
            return 0

    def get_age_seconds(self) -> float:
        try:
            entry_time = datetime.fromisoformat(self.entry_time)
            return (datetime.now() - entry_time).total_seconds()
        except (ValueError, TypeError):
            return 0

    def is_locked(self) -> bool:
        return self.status == "ACTIVE"

    def is_hard_signal(self) -> bool:
        return self.signal_strength == "HARD"

    def get_feature_summary(self) -> str:
        features = []
        if self.divergence_detected:
            features.append(f"DIV:{self.divergence_type.upper()}")
        if self.candle_pattern and self.candle_pattern != 'NONE':
            features.append(f"PAT:{self.candle_pattern}")
        if self.sr_confirmed:
            features.append("S/R")
        if self.bb_squeeze:
            features.append("SQZ")
        if self.session and self.session != 'NY':
            features.append(f"SES:{self.session}")
        return " | ".join(features) if features else "None"


class SignalManager:
    """
    Manages trading signals with v3.4.0 support.
    """

    def __init__(self):
        self.active_signals: Dict[str, SignalData] = {}
        self.signal_history: List[SignalData] = []
        self.max_history = 1000
        self.symbol_last_signal: Dict[str, datetime] = {}
        self.symbol_signal_count: Dict[str, int] = {}
        self.global_signal_timestamps: List[datetime] = []

        # Configuration
        self.SYMBOL_COOLDOWN_MINUTES = 30
        self.GLOBAL_COOLDOWN_SECONDS = 15
        self.MAX_SIGNALS_PER_HOUR = 8
        self.MIN_BARS_BEFORE_CHECK = 2
        self.MIN_SIGNAL_AGE_SECONDS = 120
        self.BREAK_EVEN_THRESHOLD_MINUTES = 480
        self.BREAK_EVEN_PRICE_THRESHOLD = 0.001

        # Grade thresholds (v3.4.0)
        self.GRADE_A_PLUS_THRESHOLD = 90
        self.GRADE_A_THRESHOLD = 82
        self.GRADE_B_PLUS_THRESHOLD = 75
        self.GRADE_B_THRESHOLD = 70
        self.GRADE_C_THRESHOLD = 60

        self.MIN_SIGNAL_SCORE = 70
        self._signal_cache: Dict[str, Tuple[datetime, str]] = {}
        self._signal_cache_ttl = 600

        self.db_client = db_client
        self.db_enabled = self.db_client is not None and self.db_client.is_available() if self.db_client is not None else False

        logger.info(f"✅ SIGNAL_MANAGER v3.4.0: Initialized")
        logger.info(f"  - Grade A+: {self.GRADE_A_PLUS_THRESHOLD}+")
        logger.info(f"  - Grade A: {self.GRADE_A_THRESHOLD}+")
        logger.info(f"  - Grade B+: {self.GRADE_B_PLUS_THRESHOLD}+")
        logger.info(f"  - Grade B: {self.GRADE_B_THRESHOLD}+")

    def _get_grade(self, score: int) -> str:
        if score >= self.GRADE_A_PLUS_THRESHOLD:
            return "A+"
        elif score >= self.GRADE_A_THRESHOLD:
            return "A"
        elif score >= self.GRADE_B_PLUS_THRESHOLD:
            return "B+"
        elif score >= self.GRADE_B_THRESHOLD:
            return "B"
        elif score >= self.GRADE_C_THRESHOLD:
            return "C"
        else:
            return "D"

    def is_symbol_locked(self, symbol: str) -> bool:
        if symbol in self.active_signals:
            signal = self.active_signals[symbol]
            if signal.status == "ACTIVE":
                return True
            else:
                del self.active_signals[symbol]
        return False

    def lock_symbol(self, symbol: str, signal_type: str, entry_price: float,
                    raw_data: Dict, **kwargs) -> bool:
        """Lock a symbol with a new signal (v3.4.0)."""
        try:
            total_score = raw_data.get('total_score', 0)
            grade = self._get_grade(total_score)

            if grade in ["C", "D"]:
                logger.warning(f"{EMOJI['REJECT']} Grade {grade} signal rejected for {symbol}")
                return False

            allowed, reason = self._check_allowed(symbol, signal_type, entry_price, total_score)
            if not allowed:
                logger.warning(f"{EMOJI['REJECT']} {reason} for {symbol}")
                return False

            required_fields = ['stop_loss', 'take_profit']
            for field in required_fields:
                if field not in raw_data or raw_data[field] == 0:
                    logger.error(f"{EMOJI['ERROR']} Missing {field} for {symbol}")
                    return False

            signal = SignalData(
                symbol=symbol,
                signal_type=signal_type,
                entry_price=entry_price,
                entry_time=datetime.now().isoformat(),
                stop_loss=raw_data.get('stop_loss'),
                take_profit=raw_data.get('take_profit'),
                confidence=raw_data.get('confidence', 0.5),
                tdi_level=raw_data.get('tdi_level', 0),
                tdi_zone=raw_data.get('tdi_zone', 'NEUTRAL'),
                rrr=raw_data.get('rrr', 0),
                signal_strength=raw_data.get('signal_strength', 'SOFT'),
                risk_multiplier=raw_data.get('risk_multiplier', 1.0),
                ai_decision=raw_data.get('ai_decision', 'APPROVE'),
                ai_confidence=raw_data.get('ai_confidence', 0.5),
                ai_validated=raw_data.get('ai_validated', False),
                quality_score=raw_data.get('quality_score', 50),
                total_score=total_score,
                grade=grade,
                component_scores=raw_data.get('component_scores', {}),
                ltf_confirmed=raw_data.get('ltf_confirmed', False),
                ltf_confidence=raw_data.get('ltf_confidence', 0.0),
                htf_trend=raw_data.get('htf_trend', 'NEUTRAL'),
                htf_aligned=raw_data.get('htf_aligned', False),
                raw_data=raw_data,
                min_bars_before_check=self.MIN_BARS_BEFORE_CHECK,
                min_age_seconds_before_check=self.MIN_SIGNAL_AGE_SECONDS,
                highest_price=entry_price,
                lowest_price=entry_price,
                # v3.4.0
                setup_score=raw_data.get('setup_score', 0),
                trigger_score=raw_data.get('trigger_score', 0),
                final_score=raw_data.get('final_score', total_score),
                entry_grade=grade,
                state='ACTIVE',
                regime=raw_data.get('regime', 'NEUTRAL'),
                structure_direction=raw_data.get('structure_direction', 'NEUTRAL'),
                entry_distance_atr=raw_data.get('entry_distance_atr', 0.0),
                ideal_entry=raw_data.get('ideal_entry', entry_price),
                atr=raw_data.get('atr', 0.0),
                divergence_detected=raw_data.get('divergence_detected', False),
                divergence_type=raw_data.get('divergence_type', ''),
                candle_pattern=raw_data.get('candle_pattern', 'NONE'),
                candle_pattern_confidence=raw_data.get('candle_pattern_confidence', 0.0),
                sr_confirmed=raw_data.get('sr_confirmed', False),
                nearest_support=raw_data.get('nearest_support', 0),
                nearest_resistance=raw_data.get('nearest_resistance', 0),
                bb_squeeze=raw_data.get('bb_squeeze', False),
                session=raw_data.get('session', 'UNKNOWN'),
                session_multiplier=raw_data.get('session_multiplier', 1.0),
            )

            # Save to database
            if self.db_enabled:
                signal_dict = signal.to_dict()
                signal_dict['status'] = 'ACTIVE'
                doc_id = self._save_to_db(signal_dict)
                if doc_id:
                    signal.db_doc_id = doc_id
                    raw_data['db_doc_id'] = doc_id

            self.active_signals[symbol] = signal
            self.symbol_last_signal[symbol] = datetime.now()
            self.symbol_signal_count[symbol] = self.symbol_signal_count.get(symbol, 0) + 1
            self.global_signal_timestamps.append(datetime.now())

            logger.info(
                f"{EMOJI['LOCK']} SIGNAL_LOCK: {signal_type} {symbol} "
                f"@ {entry_price:.4f} | Score: {total_score}/100 | Grade: {grade} | "
                f"Features: {signal.get_feature_summary()}"
            )
            return True

        except Exception as e:
            logger.error(f"{EMOJI['ERROR']} Error locking symbol {symbol}: {e}")
            return False

    def _check_allowed(self, symbol: str, signal_type: str, entry_price: float,
                       total_score: int) -> Tuple[bool, str]:
        """Check if signal is allowed."""
        if self.is_symbol_locked(symbol):
            return False, f"Symbol {symbol} is locked"

        if symbol in self.symbol_last_signal:
            time_since = (datetime.now() - self.symbol_last_signal[symbol]).total_seconds() / 60
            if time_since < self.SYMBOL_COOLDOWN_MINUTES:
                return False, f"Cooldown: {self.SYMBOL_COOLDOWN_MINUTES - time_since:.1f}min remaining"

        now = datetime.now()
        self.global_signal_timestamps = [
            ts for ts in self.global_signal_timestamps
            if (now - ts).total_seconds() < 3600
        ]
        if len(self.global_signal_timestamps) >= self.MAX_SIGNALS_PER_HOUR:
            return False, f"Global limit: {self.MAX_SIGNALS_PER_HOUR}/hour"

        return True, "OK"

    def _save_to_db(self, signal_data: Dict) -> Optional[str]:
        if not self.db_enabled:
            return None
        try:
            return self.db_client.save_signal(signal_data)
        except Exception as e:
            logger.warning(f"{EMOJI['WARNING']} Failed to save signal: {e}")
            return None

    def get_all_active_signals(self) -> Dict[str, SignalData]:
        return self.active_signals.copy()

    def get_signal(self, symbol: str) -> Optional[SignalData]:
        return self.active_signals.get(symbol)

    def remove_signal(self, symbol: str) -> bool:
        if symbol in self.active_signals:
            del self.active_signals[symbol]
            return True
        return False

    def check_active_signal(self, symbol: str, current_price: float,
                           last_candle: Dict) -> Tuple[str, float, Optional[SignalData]]:
        """Check active signal for TP/SL/BreakEven."""
        if symbol not in self.active_signals:
            return "NO_SIGNAL", 0, None

        signal = self.active_signals[symbol]
        signal.bar_count += 1
        signal.last_checked_at = datetime.now().isoformat()

        if signal.highest_price is None or current_price > signal.highest_price:
            signal.highest_price = current_price
        if signal.lowest_price is None or current_price < signal.lowest_price:
            signal.lowest_price = current_price

        age_seconds = signal.get_age_seconds()
        age_minutes = age_seconds / 60

        if signal.bar_count < signal.min_bars_before_check:
            return "ACTIVE", current_price - signal.entry_price, signal
        if age_seconds < signal.min_age_seconds_before_check:
            return "ACTIVE", current_price - signal.entry_price, signal

        # Check SL/TP
        if signal.signal_type == "BUY":
            if current_price <= signal.stop_loss:
                updated = self._unlock_symbol(symbol, TradeLifecycle.LOSS, current_price)
                return TradeLifecycle.LOSS.value, current_price - signal.entry_price, updated
            if current_price >= signal.take_profit:
                updated = self._unlock_symbol(symbol, TradeLifecycle.PROFIT, current_price)
                return TradeLifecycle.PROFIT.value, current_price - signal.entry_price, updated
        else:
            if current_price >= signal.stop_loss:
                updated = self._unlock_symbol(symbol, TradeLifecycle.LOSS, current_price)
                return TradeLifecycle.LOSS.value, signal.entry_price - current_price, updated
            if current_price <= signal.take_profit:
                updated = self._unlock_symbol(symbol, TradeLifecycle.PROFIT, current_price)
                return TradeLifecycle.PROFIT.value, signal.entry_price - current_price, updated

        # Break-even check (8 hours)
        if age_minutes > self.BREAK_EVEN_THRESHOLD_MINUTES:
            price_diff_pct = abs((current_price - signal.entry_price) / signal.entry_price)
            if price_diff_pct < self.BREAK_EVEN_PRICE_THRESHOLD:
                updated = self._unlock_symbol(symbol, TradeLifecycle.BREAK_EVEN, current_price)
                return TradeLifecycle.BREAK_EVEN.value, 0, updated

        return "ACTIVE", current_price - signal.entry_price, signal

    def _unlock_symbol(self, symbol: str, status: TradeLifecycle, exit_price: float) -> Optional[SignalData]:
        """Unlock a symbol and update its status."""
        if symbol not in self.active_signals:
            return None

        signal = self.active_signals[symbol]
        old_status = signal.status
        status_str = status.value if hasattr(status, 'value') else str(status)

        signal.status = status_str
        signal.exit_time = datetime.now().isoformat()
        signal.exit_price = exit_price

        if signal.signal_type == "BUY":
            signal.pnl = exit_price - signal.entry_price
        else:
            signal.pnl = signal.entry_price - exit_price
        signal.pnl_percent = (signal.pnl / signal.entry_price) * 100 if signal.entry_price > 0 else 0

        fee = signal.entry_price * 0.0011 + exit_price * 0.0011
        signal.fees = fee
        signal.pnl = signal.pnl - fee
        signal.pnl_percent = (signal.pnl / signal.entry_price) * 100 if signal.entry_price > 0 else 0

        # Update database
        if signal.db_doc_id:
            update_data = signal.to_dict()
            update_data['status'] = status_str
            self._update_in_db(signal.db_doc_id, status_str, update_data)

        self.signal_history.append(signal)
        if len(self.signal_history) > self.max_history:
            self.signal_history.pop(0)

        del self.active_signals[symbol]

        logger.info(
            f"{EMOJI['UNLOCK']} SIGNAL_UNLOCK: {symbol} {old_status} -> {status_str} | "
            f"PnL: ${signal.pnl:.2f} ({signal.pnl_percent:.2f}%) | "
            f"Bars: {signal.bar_count} | Age: {signal.get_age_minutes():.1f}min"
        )
        return signal

    def _update_in_db(self, doc_id: str, status: str, update_data: Dict) -> bool:
        if not self.db_enabled or not doc_id:
            return False
        try:
            return self.db_client.update_signal_status(doc_id, status, update_data)
        except Exception as e:
            logger.warning(f"{EMOJI['WARNING']} Failed to update signal: {e}")
            return False

    def get_stats(self) -> Dict:
        return {
            "active": len(self.active_signals),
            "history": len(self.signal_history),
            "active_symbols": list(self.active_signals.keys()),
            "grade_summary": {
                "a_plus": sum(1 for s in self.active_signals.values() if s.grade == "A+"),
                "a": sum(1 for s in self.active_signals.values() if s.grade == "A"),
                "b_plus": sum(1 for s in self.active_signals.values() if s.grade == "B+"),
                "b": sum(1 for s in self.active_signals.values() if s.grade == "B"),
            },
            "version": "3.4.0"
        }


# Singleton
signal_manager = SignalManager()
