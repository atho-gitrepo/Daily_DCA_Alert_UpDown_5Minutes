"""
Signal Manager - Handles signal lifecycle, debouncing, and duplicate prevention
UPDATED v3.3.0: Added Divergence, Candle Patterns, S/R, Session Filtering support
Version: 3.3.0 - ENHANCED: New signal fields for v3.3.0 features
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
    try:
        from utils.firebase_client import firebase_client as db_client
    except ImportError:
        db_client = None
        logging.warning("No database client available. Signal persistence disabled.")

logger = logging.getLogger(__name__)

EMOJI = {
    "SUCCESS": "✅",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "INFO": "ℹ️",
    "SIGNAL": "📡",
    "PROFIT": "💰",
    "LOSS": "💸",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "MONITOR": "📊",
    "WAIT": "⏳",
    "REJECT": "🚫",
    "RESTORE": "♻️",
    "BREAK": "⏹️",
    "LTF": "⏱️",
    "HTF": "📊",
    "CONFLICT": "⚔️",
    "ACTIVE": "🟢",
    "RESOLVED": "✅",
    "SCORE": "🎯",
    "COMPONENT": "📊",
    "GRADE_A": "🏆",
    "GRADE_B": "🥈",
    "GRADE_C": "🥉",
    "APPROVED": "✅",
    "DB": "💾",
    "FIREBASE": "🔥",
    "MONGODB": "🍃",
    # NEW v3.3.0
    "DIVERGENCE": "↩️",
    "PATTERN": "🕯️",
    "S_R": "📊",
    "SESSION": "🌍",
}


class TradeLifecycle(str, Enum):
    """Trade lifecycle states."""
    ACTIVE = "ACTIVE"
    PROFIT = "PROFIT"
    LOSS = "LOSS"
    BREAK_EVEN = "BREAK_EVEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


@dataclass
class SignalStats:
    """Signal statistics with v3.3.0 tracking."""
    total_signals: int = 0
    approved_signals: int = 0
    rejected_signals: int = 0
    profitable_signals: int = 0
    losing_signals: int = 0
    break_even_signals: int = 0
    active_signals: int = 0
    restored_signals: int = 0
    conflicts_detected: int = 0
    conflicts_overridden: int = 0
    ltf_confirmed_signals: int = 0
    htf_aligned_signals: int = 0
    hard_signals: int = 0
    soft_signals: int = 0

    # Grade tracking
    grade_a_signals: int = 0
    grade_b_signals: int = 0
    grade_c_rejected: int = 0

    score_approved: int = 0
    score_rejected: int = 0
    data_stale_events: int = 0
    volume_rejected: int = 0
    bb_rejected: int = 0

    # Database tracking
    db_saves: int = 0
    db_updates: int = 0
    db_errors: int = 0
    db_restores: int = 0

    # NEW v3.3.0
    divergence_signals: int = 0
    pattern_signals: int = 0
    sr_signals: int = 0
    squeeze_signals: int = 0
    session_adjusted: int = 0

    def to_dict(self) -> Dict:
        return {
            "total": self.total_signals,
            "approved": self.approved_signals,
            "rejected": self.rejected_signals,
            "profitable": self.profitable_signals,
            "losing": self.losing_signals,
            "break_even": self.break_even_signals,
            "active": self.active_signals,
            "restored": self.restored_signals,
            "conflicts_detected": self.conflicts_detected,
            "conflicts_overridden": self.conflicts_overridden,
            "ltf_confirmed": self.ltf_confirmed_signals,
            "htf_aligned": self.htf_aligned_signals,
            "hard_signals": self.hard_signals,
            "soft_signals": self.soft_signals,
            "grade_a": self.grade_a_signals,
            "grade_b": self.grade_b_signals,
            "grade_c_rejected": self.grade_c_rejected,
            "score_approved": self.score_approved,
            "score_rejected": self.score_rejected,
            "data_stale_events": self.data_stale_events,
            "volume_rejected": self.volume_rejected,
            "bb_rejected": self.bb_rejected,
            "db_saves": self.db_saves,
            "db_updates": self.db_updates,
            "db_errors": self.db_errors,
            "db_restores": self.db_restores,
            # NEW v3.3.0
            "divergence_signals": self.divergence_signals,
            "pattern_signals": self.pattern_signals,
            "sr_signals": self.sr_signals,
            "squeeze_signals": self.squeeze_signals,
            "session_adjusted": self.session_adjusted,
        }


@dataclass
class SignalData:
    """
    Signal data structure with v3.3.0 fields.
    No expiry, 8-hour break-even.
    """
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
    tdi_level: float = 0.0
    tdi_zone: str = "NEUTRAL"
    rrr: float = 0.0
    signal_strength: str = "SOFT"
    risk_multiplier: float = 1.0
    ai_decision: str = "APPROVE"
    ai_confidence: float = 0.0
    ai_validated: bool = False
    ai_suggested_rrr: Optional[float] = None
    has_conflict: bool = False
    conflict_reason: str = ""
    quality_score: int = 50
    ltf_confirmed: bool = False
    ltf_confidence: float = 0.0
    ltf_reason: str = ""
    htf_trend: str = "NEUTRAL"
    htf_aligned: bool = False
    htf_conflict: bool = False
    htf_conflict_reason: str = ""
    raw_data: Dict = field(default_factory=dict)
    bar_count: int = 0
    min_bars_before_check: int = 2
    min_age_seconds_before_check: int = 120
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None
    restored_from_db: bool = False
    db_doc_id: Optional[str] = None
    last_checked_at: Optional[str] = None

    total_score: int = 0
    component_scores: Dict[str, float] = field(default_factory=dict)
    bb_position: float = 0.5
    volume_ratio: float = 1.0
    tdi_zone_standardized: str = "NEUTRAL"
    rejection_reason: str = ""
    grade: str = ""

    # ===== NEW v3.3.0 FIELDS =====
    divergence_detected: bool = False
    divergence_strength: float = 0.0
    divergence_type: str = ""  # "bullish" or "bearish"
    candle_pattern: str = ""  # "DOJI", "ENGULFING", "HAMMER", etc.
    candle_pattern_confidence: float = 0.0
    candle_pattern_direction: str = ""  # "BUY", "SELL", "NONE"
    sr_confirmed: bool = False
    sr_position: str = ""  # "ABOVE_RESISTANCE", "IN_RANGE", "BELOW_SUPPORT"
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    bb_squeeze: bool = False
    bb_squeeze_strength: float = 0.0
    session: str = ""  # "ASIAN", "LONDON", "NY", "LATE"
    session_multiplier: float = 1.0

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
            "tdi_zone_standardized": self.tdi_zone_standardized,
            "rrr": self.rrr,
            "signal_strength": self.signal_strength,
            "risk_multiplier": self.risk_multiplier,
            "ai_decision": self.ai_decision,
            "ai_confidence": self.ai_confidence,
            "ai_validated": self.ai_validated,
            "ai_suggested_rrr": self.ai_suggested_rrr,
            "has_conflict": self.has_conflict,
            "conflict_reason": self.conflict_reason,
            "quality_score": self.quality_score,
            "total_score": self.total_score,
            "component_scores": self.component_scores,
            "bb_position": self.bb_position,
            "volume_ratio": self.volume_ratio,
            "ltf_confirmed": self.ltf_confirmed,
            "ltf_confidence": self.ltf_confidence,
            "ltf_reason": self.ltf_reason,
            "htf_trend": self.htf_trend,
            "htf_aligned": self.htf_aligned,
            "htf_conflict": self.htf_conflict,
            "htf_conflict_reason": self.htf_conflict_reason,
            "bars_held": self.bar_count,
            "restored": self.restored_from_db,
            "rejection_reason": self.rejection_reason,
            "grade": self.grade,
            "db_doc_id": self.db_doc_id,
            # NEW v3.3.0
            "divergence_detected": self.divergence_detected,
            "divergence_strength": self.divergence_strength,
            "divergence_type": self.divergence_type,
            "candle_pattern": self.candle_pattern,
            "candle_pattern_confidence": self.candle_pattern_confidence,
            "candle_pattern_direction": self.candle_pattern_direction,
            "sr_confirmed": self.sr_confirmed,
            "sr_position": self.sr_position,
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "bb_squeeze": self.bb_squeeze,
            "bb_squeeze_strength": self.bb_squeeze_strength,
            "session": self.session,
            "session_multiplier": self.session_multiplier,
        }

    def is_locked(self) -> bool:
        return self.status == "ACTIVE"

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

    def is_hard_signal(self) -> bool:
        return self.signal_strength == "HARD"

    def is_soft_signal(self) -> bool:
        return self.signal_strength == "SOFT"

    def is_high_score(self) -> bool:
        return self.total_score >= 80

    def is_medium_score(self) -> bool:
        return 70 <= self.total_score < 80

    def is_low_score(self) -> bool:
        return self.total_score < 70

    def get_score_grade(self) -> str:
        if self.total_score >= 85: return "A"
        elif self.total_score >= 75: return "B"
        elif self.total_score >= 70: return "C"
        elif self.total_score >= 50: return "D"
        else: return "F"

    def get_component_summary(self) -> str:
        if not self.component_scores: return "N/A"
        parts = []
        for key, label in [('ltf', 'LTF'), ('tdi', 'TDI'), ('bb', 'BB'),
                           ('volume', 'Vol'), ('reversal', 'Rev')]:
            if key in self.component_scores:
                parts.append(f"{label}={self.component_scores[key]:.0f}")
        return ", ".join(parts) if parts else "N/A"

    def get_feature_summary(self) -> str:
        """NEW v3.3.0: Get feature summary for logging."""
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
    Manages trading signals with v3.3.0 features.
    NO EXPIRY, 8-hour break-even.
    Version: 3.3.0
    """

    def __init__(self):
        self.active_signals: Dict[str, SignalData] = {}
        self.signal_history: List[SignalData] = []
        self.max_history = 1000
        self.symbol_last_signal: Dict[str, datetime] = {}
        self.symbol_signal_count: Dict[str, int] = {}
        self.global_signal_timestamps: List[datetime] = []
        self.stats = SignalStats()

        # Configuration
        self.SYMBOL_COOLDOWN_MINUTES = 30
        self.GLOBAL_COOLDOWN_SECONDS = 15
        self.MAX_SIGNALS_PER_HOUR = 8
        self.MIN_BARS_BEFORE_CHECK = 2
        self.MIN_SIGNAL_AGE_SECONDS = 120
        self.BREAK_EVEN_THRESHOLD_MINUTES = 480  # 8 hours
        self.BREAK_EVEN_PRICE_THRESHOLD = 0.001
        self.SIGNAL_EXPIRY_MINUTES = None

        # Grade thresholds
        self.GRADE_A_THRESHOLD = 80
        self.GRADE_B_THRESHOLD = 70
        self.GRADE_C_THRESHOLD = 60

        self.MIN_SIGNAL_SCORE = 65
        self.HIGH_SCORE_THRESHOLD = 80

        self._signal_cache: Dict[str, Tuple[datetime, str]] = {}
        self._signal_cache_ttl = 600
        self._conflict_cache: Dict[str, Dict[str, Any]] = {}

        # Database client
        self.db_client = db_client
        self.db_enabled = self.db_client is not None and self.db_client.is_available() if self.db_client is not None else False

        if self.db_enabled:
            db_type = "MongoDB" if hasattr(self.db_client, 'mongodb') else "Firebase"
            logger.info(f"{EMOJI['DB']} {db_type} database connected")
        else:
            logger.warning(f"{EMOJI['WARNING']} No database connection - signals will be in-memory only")

        logger.info(f"{EMOJI['SUCCESS']} SIGNAL_MANAGER v3.3.0: Initialized")
        logger.info(f"  - Symbol Cooldown: {self.SYMBOL_COOLDOWN_MINUTES}min")
        logger.info(f"  - Min Bars Before Check: {self.MIN_BARS_BEFORE_CHECK}")
        logger.info(f"  - Min Signal Age: {self.MIN_SIGNAL_AGE_SECONDS}s")
        logger.info(f"  - Break-Even Check: {self.BREAK_EVEN_THRESHOLD_MINUTES}min (8 hours)")
        logger.info(f"  - Signal Expiry: None (No expiry)")
        logger.info(f"  - Grade A Threshold: {self.GRADE_A_THRESHOLD}/100")
        logger.info(f"  - Grade B Threshold: {self.GRADE_B_THRESHOLD}/100")
        logger.info(f"  - Grade C Threshold: {self.GRADE_C_THRESHOLD}/100")
        logger.info(f"  - HARD Signals: 2x risk, SOFT Signals: 1x risk")
        logger.info(f"  - Database: {'Enabled' if self.db_enabled else 'Disabled (In-Memory Only)'}")
        # NEW v3.3.0
        logger.info(f"  - Divergence Tracking: Enabled")
        logger.info(f"  - Candle Pattern Tracking: Enabled")
        logger.info(f"  - S/R Level Tracking: Enabled")
        logger.info(f"  - Session Tracking: Enabled")

    def _get_cache_key(self, symbol: str, signal_type: str, entry_price: float) -> str:
        return f"{symbol}_{signal_type}_{round(entry_price, 6)}"

    def _get_grade(self, score: int) -> str:
        if score >= self.GRADE_A_THRESHOLD:
            return "A"
        elif score >= self.GRADE_B_THRESHOLD:
            return "B"
        elif score >= self.GRADE_C_THRESHOLD:
            return "C"
        else:
            return "D"

    def _save_to_db(self, signal_data: Dict) -> Optional[str]:
        if not self.db_enabled:
            return None

        try:
            doc_id = self.db_client.save_signal(signal_data)
            if doc_id:
                self.stats.db_saves += 1
                logger.debug(f"{EMOJI['DB']} Signal saved to database: {doc_id}")
            return doc_id
        except Exception as e:
            self.stats.db_errors += 1
            logger.warning(f"{EMOJI['WARNING']} Failed to save signal to database: {e}")
            return None

    def _update_in_db(self, doc_id: str, status: str, update_data: Dict) -> bool:
        if not self.db_enabled or not doc_id:
            return False

        try:
            success = self.db_client.update_signal_status(doc_id, status, update_data)
            if success:
                self.stats.db_updates += 1
                logger.debug(f"{EMOJI['DB']} Signal updated in database: {doc_id}")
            return success
        except Exception as e:
            self.stats.db_errors += 1
            logger.warning(f"{EMOJI['WARNING']} Failed to update signal in database: {e}")
            return False

    def _delete_from_db(self, doc_id: str) -> bool:
        if not self.db_enabled or not doc_id:
            return False

        try:
            success = self.db_client.delete_signal(doc_id, collection='active')
            if success:
                logger.debug(f"{EMOJI['DB']} Signal deleted from database: {doc_id}")
            return success
        except Exception as e:
            self.stats.db_errors += 1
            logger.warning(f"{EMOJI['WARNING']} Failed to delete signal from database: {e}")
            return False

    def is_symbol_locked(self, symbol: str) -> bool:
        if symbol in self.active_signals:
            signal = self.active_signals[symbol]
            if signal.status == "ACTIVE":
                return True
            else:
                del self.active_signals[symbol]
                self.stats.active_signals = len(self.active_signals)
        return False

    def get_locked_symbols(self) -> List[str]:
        return list(self.active_signals.keys())

    def is_signal_allowed(self, symbol: str, signal_type: str = None,
                          entry_price: float = None, total_score: int = 0) -> Tuple[bool, str]:
        """Check if signal is allowed with grade-based filtering."""
        try:
            if self.is_symbol_locked(symbol):
                return False, f"Symbol {symbol} is locked with active signal"

            grade = self._get_grade(total_score)

            if grade == "C":
                self.stats.grade_c_rejected += 1
                self.stats.score_rejected += 1
                return False, f"Grade C ({total_score}/100) - Only Grade A and B allowed"

            if grade == "D":
                self.stats.score_rejected += 1
                return False, f"Grade D ({total_score}/100) - Below minimum threshold"

            if grade == "B":
                if total_score < self.GRADE_B_THRESHOLD:
                    self.stats.score_rejected += 1
                    return False, f"Score {total_score} below Grade B threshold"
                self.stats.grade_b_signals += 1

            if grade == "A":
                self.stats.grade_a_signals += 1

            if symbol in self.symbol_last_signal:
                time_since = (datetime.now() - self.symbol_last_signal[symbol]).total_seconds() / 60
                if time_since < self.SYMBOL_COOLDOWN_MINUTES:
                    remaining = self.SYMBOL_COOLDOWN_MINUTES - time_since
                    return False, f"Symbol cooldown: {remaining:.1f}min remaining"

            if signal_type and entry_price:
                cache_key = self._get_cache_key(symbol, signal_type, entry_price)
                if cache_key in self._signal_cache:
                    last_time, _ = self._signal_cache[cache_key]
                    time_since = (datetime.now() - last_time).total_seconds()
                    if time_since < self._signal_cache_ttl:
                        return False, f"Duplicate signal detected"

            now = datetime.now()
            self.global_signal_timestamps = [
                ts for ts in self.global_signal_timestamps
                if (now - ts).total_seconds() < 3600
            ]
            if len(self.global_signal_timestamps) >= self.MAX_SIGNALS_PER_HOUR:
                return False, f"Global signal limit reached ({self.MAX_SIGNALS_PER_HOUR}/hour)"

            return True, "OK"
        except Exception as e:
            logger.error(f"{EMOJI['ERROR']} Error checking signal allowance: {e}")
            return False, f"Error: {e}"

    def lock_symbol(self, symbol: str, signal_type: str, entry_price: float,
                    raw_data: Dict, **kwargs) -> bool:
        """Lock a symbol with a new signal (v3.3.0)."""
        try:
            total_score = raw_data.get('total_score', 0)
            grade = raw_data.get('grade', self._get_grade(total_score))

            if grade == "C" or grade == "D":
                logger.warning(f"{EMOJI['REJECT']} Grade {grade} signal rejected for {symbol} ({total_score}/100)")
                self.stats.rejected_signals += 1
                self.stats.grade_c_rejected += 1
                return False

            allowed, reason = self.is_signal_allowed(symbol, signal_type, entry_price, total_score)
            if not allowed:
                logger.warning(f"{EMOJI['WARNING']} Signal rejected for {symbol}: {reason}")
                self.stats.rejected_signals += 1
                return False

            required_fields = ['stop_loss', 'take_profit']
            for field in required_fields:
                if field not in raw_data or raw_data[field] == 0:
                    logger.error(f"{EMOJI['ERROR']} Missing {field} for {symbol}")
                    return False

            signal_strength = raw_data.get('signal_strength', 'SOFT')
            risk_multiplier = 2.0 if signal_strength == "HARD" else 1.0

            if signal_strength == "HARD": self.stats.hard_signals += 1
            else: self.stats.soft_signals += 1
            if raw_data.get('ltf_confirmed', False): self.stats.ltf_confirmed_signals += 1
            if raw_data.get('htf_aligned', False): self.stats.htf_aligned_signals += 1
            if total_score >= self.MIN_SIGNAL_SCORE: self.stats.score_approved += 1

            if grade == "A": self.stats.grade_a_signals += 1
            elif grade == "B": self.stats.grade_b_signals += 1

            # NEW v3.3.0: Track features
            if raw_data.get('divergence_detected', False):
                self.stats.divergence_signals += 1
            if raw_data.get('candle_pattern', 'NONE') != 'NONE':
                self.stats.pattern_signals += 1
            if raw_data.get('sr_confirmed', False):
                self.stats.sr_signals += 1
            if raw_data.get('bb_squeeze', False):
                self.stats.squeeze_signals += 1
            if raw_data.get('session', 'UNKNOWN') != 'NY':
                self.stats.session_adjusted += 1

            signal = SignalData(
                symbol=symbol, signal_type=signal_type,
                entry_price=entry_price, entry_time=datetime.now().isoformat(),
                stop_loss=raw_data.get('stop_loss'),
                take_profit=raw_data.get('take_profit'),
                confidence=raw_data.get('confidence', 0.5),
                tdi_level=raw_data.get('tdi_level', 0),
                tdi_zone=raw_data.get('tdi_zone', 'NEUTRAL'),
                rrr=raw_data.get('rrr', 0),
                signal_strength=signal_strength,
                risk_multiplier=risk_multiplier,
                ai_decision=raw_data.get('ai_decision', 'APPROVE'),
                ai_confidence=raw_data.get('ai_confidence', 0.5),
                ai_validated=raw_data.get('ai_validated', False),
                ai_suggested_rrr=raw_data.get('suggested_rrr'),
                has_conflict=raw_data.get('has_conflict', False),
                conflict_reason=raw_data.get('conflict_reason', ''),
                quality_score=raw_data.get('quality_score', 50),
                ltf_confirmed=raw_data.get('ltf_confirmed', False),
                ltf_confidence=raw_data.get('ltf_confidence', 0.0),
                ltf_reason=raw_data.get('ltf_reason', ''),
                htf_trend=raw_data.get('htf_trend', 'NEUTRAL'),
                htf_aligned=raw_data.get('htf_aligned', False),
                htf_conflict=raw_data.get('htf_conflict', False),
                htf_conflict_reason=raw_data.get('htf_conflict_reason', ''),
                raw_data=raw_data,
                min_bars_before_check=self.MIN_BARS_BEFORE_CHECK,
                min_age_seconds_before_check=self.MIN_SIGNAL_AGE_SECONDS,
                bar_count=0, highest_price=entry_price, lowest_price=entry_price,
                restored_from_db=False,
                last_checked_at=datetime.now().isoformat(),
                total_score=total_score,
                component_scores=raw_data.get('component_scores', {}),
                bb_position=raw_data.get('bb_position', 0.5),
                volume_ratio=raw_data.get('volume_ratio', 1.0),
                tdi_zone_standardized=raw_data.get('tdi_zone', 'NEUTRAL'),
                rejection_reason=raw_data.get('rejection_reason', ''),
                grade=grade,
                # NEW v3.3.0
                divergence_detected=raw_data.get('divergence_detected', False),
                divergence_strength=raw_data.get('divergence_strength', 0.0),
                divergence_type=raw_data.get('divergence_type', ''),
                candle_pattern=raw_data.get('candle_pattern', 'NONE'),
                candle_pattern_confidence=raw_data.get('candle_pattern_confidence', 0.0),
                candle_pattern_direction=raw_data.get('candle_pattern_direction', 'NONE'),
                sr_confirmed=raw_data.get('sr_confirmed', False),
                sr_position=raw_data.get('sr_position', ''),
                nearest_support=raw_data.get('nearest_support', 0.0),
                nearest_resistance=raw_data.get('nearest_resistance', 0.0),
                bb_squeeze=raw_data.get('bb_squeeze', False),
                bb_squeeze_strength=raw_data.get('bb_squeeze_strength', 0.0),
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
                    logger.info(f"{EMOJI['DB']} Signal saved to database: {doc_id}")

            self.active_signals[symbol] = signal
            self.symbol_last_signal[symbol] = datetime.now()
            self.symbol_signal_count[symbol] = self.symbol_signal_count.get(symbol, 0) + 1
            self.global_signal_timestamps.append(datetime.now())

            cache_key = self._get_cache_key(symbol, signal_type, entry_price)
            self._signal_cache[cache_key] = (datetime.now(), signal_type)
            self._signal_cache[symbol] = (datetime.now(), signal_type)

            if signal.has_conflict:
                self.stats.conflicts_detected += 1
                self._conflict_cache[symbol] = {
                    'reason': signal.conflict_reason, 'time': datetime.now().isoformat(),
                    'overridden': False, 'htf_conflict': signal.htf_conflict,
                    'htf_conflict_reason': signal.htf_conflict_reason,
                }

            self.stats.total_signals += 1
            self.stats.approved_signals += 1
            self.stats.active_signals = len(self.active_signals)

            grade_emoji = "🏆" if grade == "A" else "🥈" if grade == "B" else "📊"
            ltf_info = f" | LTF: {'✅' if signal.ltf_confirmed else '❌'}"
            htf_info = f" | HTF: {signal.htf_trend} {'✅' if signal.htf_aligned else '❌'}"
            strength_info = f" | STRENGTH: {signal_strength} ({signal.risk_multiplier}x risk)"
            score_info = f" | SCORE: {signal.total_score}/100 {grade_emoji}{grade}"
            component_info = f" | [{signal.get_component_summary()}]" if signal.component_scores else ""
            db_info = f" | DB: {signal.db_doc_id[:16] if signal.db_doc_id else 'None'}..."

            # NEW v3.3.0: Feature info
            feature_info = f" | FEATURES: {signal.get_feature_summary()}"

            logger.info(
                f"{EMOJI['LOCK']} SIGNAL_LOCK: {signal_type} {symbol} "
                f"@ {entry_price:.6f} | TDI: {signal.tdi_level:.1f} ({signal.tdi_zone}) | "
                f"RRR: {signal.rrr:.1f} | Quality: {signal.quality_score}/100"
                f"{score_info}{component_info}{ltf_info}{htf_info}{strength_info}{feature_info}{db_info}"
            )
            return True
        except Exception as e:
            logger.error(f"{EMOJI['ERROR']} Error locking symbol {symbol}: {e}")
            logger.debug(traceback.format_exc())
            return False

    def restore_symbol(self, symbol: str, signal_type: str, entry_price: float,
                      entry_time: str, raw_data: Dict) -> bool:
        """Restore a symbol from database with v3.3.0 fields."""
        try:
            if self.is_symbol_locked(symbol):
                logger.warning(f"{EMOJI['WARNING']} Symbol {symbol} already locked")
                return False

            try: entry_dt = datetime.fromisoformat(entry_time)
            except (ValueError, TypeError):
                entry_dt = datetime.now(); entry_time = entry_dt.isoformat()

            age_minutes = (datetime.now() - entry_dt).total_seconds() / 60
            status = raw_data.get('status', 'ACTIVE')
            if status != 'ACTIVE': return False

            signal_strength = raw_data.get('signal_strength', 'SOFT')
            risk_multiplier = 2.0 if signal_strength == "HARD" else 1.0
            total_score = raw_data.get('total_score', 0)
            grade = raw_data.get('grade', self._get_grade(total_score))
            component_scores = raw_data.get('component_scores', {})

            if grade == "C" or grade == "D":
                logger.warning(f"{EMOJI['REJECT']} Grade {grade} signal cannot be restored for {symbol}")
                return False

            signal = SignalData(
                symbol=symbol, signal_type=signal_type,
                entry_price=entry_price, entry_time=entry_time,
                stop_loss=raw_data.get('stop_loss', 0),
                take_profit=raw_data.get('take_profit', 0),
                confidence=raw_data.get('confidence', 0.5),
                tdi_level=raw_data.get('tdi_level', 0),
                tdi_zone=raw_data.get('tdi_zone', 'NEUTRAL'),
                rrr=raw_data.get('rrr', 0),
                signal_strength=signal_strength,
                risk_multiplier=risk_multiplier,
                quality_score=raw_data.get('quality_score', 50),
                ltf_confirmed=raw_data.get('ltf_confirmed', False),
                ltf_confidence=raw_data.get('ltf_confidence', 0.0),
                htf_trend=raw_data.get('htf_trend', 'NEUTRAL'),
                htf_aligned=raw_data.get('htf_aligned', False),
                raw_data=raw_data,
                min_bars_before_check=self.MIN_BARS_BEFORE_CHECK,
                min_age_seconds_before_check=self.MIN_SIGNAL_AGE_SECONDS,
                bar_count=int(age_minutes / 15) + 1,
                highest_price=entry_price, lowest_price=entry_price,
                restored_from_db=True,
                db_doc_id=raw_data.get('doc_id', raw_data.get('db_doc_id')),
                last_checked_at=datetime.now().isoformat(),
                total_score=total_score,
                component_scores=component_scores,
                bb_position=raw_data.get('bb_position', 0.5),
                volume_ratio=raw_data.get('volume_ratio', 1.0),
                grade=grade,
                # NEW v3.3.0
                divergence_detected=raw_data.get('divergence_detected', False),
                divergence_strength=raw_data.get('divergence_strength', 0.0),
                divergence_type=raw_data.get('divergence_type', ''),
                candle_pattern=raw_data.get('candle_pattern', 'NONE'),
                candle_pattern_confidence=raw_data.get('candle_pattern_confidence', 0.0),
                candle_pattern_direction=raw_data.get('candle_pattern_direction', 'NONE'),
                sr_confirmed=raw_data.get('sr_confirmed', False),
                sr_position=raw_data.get('sr_position', ''),
                nearest_support=raw_data.get('nearest_support', 0.0),
                nearest_resistance=raw_data.get('nearest_resistance', 0.0),
                bb_squeeze=raw_data.get('bb_squeeze', False),
                bb_squeeze_strength=raw_data.get('bb_squeeze_strength', 0.0),
                session=raw_data.get('session', 'UNKNOWN'),
                session_multiplier=raw_data.get('session_multiplier', 1.0),
            )

            self.active_signals[symbol] = signal
            self.symbol_last_signal[symbol] = datetime.now()
            self.stats.total_signals += 1
            self.stats.approved_signals += 1
            self.stats.active_signals = len(self.active_signals)
            self.stats.restored_signals += 1
            self.stats.db_restores += 1
            if total_score >= self.MIN_SIGNAL_SCORE: self.stats.score_approved += 1
            if grade == "A": self.stats.grade_a_signals += 1
            elif grade == "B": self.stats.grade_b_signals += 1

            grade_emoji = "🏆" if grade == "A" else "🥈" if grade == "B" else "📊"
            feature_info = f" | FEATURES: {signal.get_feature_summary()}"
            logger.info(f"{EMOJI['RESTORE']} SIGNAL_RESTORE: {signal_type} {symbol} @ {entry_price:.6f} | Age: {age_minutes:.1f}min | Grade: {grade_emoji}{grade} | Score: {total_score}/100{feature_info}")
            return True
        except Exception as e:
            logger.error(f"{EMOJI['ERROR']} Error restoring symbol {symbol}: {e}")
            return False

    def unlock_symbol(self, symbol: str, status: Any, exit_price: float = None) -> Optional[SignalData]:
        """Unlock a symbol and update its status - COMPLETE DELETION from DB."""
        if symbol not in self.active_signals: return None

        signal = self.active_signals[symbol]
        old_status = signal.status

        status_str = status.value if hasattr(status, 'value') else str(status)
        if status_str == "ACTIVE": return signal

        signal.status = status_str
        signal.exit_time = datetime.now().isoformat()

        if exit_price is not None:
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

        # ✅ FIXED: Update database - COMPLETE DELETE from active
        if signal.db_doc_id:
            update_data = {
                'status': status_str,
                'exit_price': signal.exit_price,
                'exit_time': signal.exit_time,
                'pnl': signal.pnl,
                'pnl_percent': signal.pnl_percent,
                'fees': signal.fees,
                'bars_held': signal.bar_count,
                'age_minutes': signal.get_age_minutes(),
                'divergence_detected': signal.divergence_detected,
                'candle_pattern': signal.candle_pattern,
                'sr_confirmed': signal.sr_confirmed,
                'session': signal.session,
            }
            # This will now DELETE from active and SAVE to resolved
            self._update_in_db(signal.db_doc_id, status_str, update_data)

        if status_str == "PROFIT": self.stats.profitable_signals += 1
        elif status_str == "LOSS": self.stats.losing_signals += 1
        elif status_str == "BREAK_EVEN": self.stats.break_even_signals += 1

        self.signal_history.append(signal)
        if len(self.signal_history) > self.max_history: self.signal_history.pop(0)
        del self.active_signals[symbol]
        self.stats.active_signals = len(self.active_signals)
        if symbol in self._conflict_cache: del self._conflict_cache[symbol]

        grade_emoji = "🏆" if signal.grade == "A" else "🥈" if signal.grade == "B" else "📊"
        score_info = f" | Score: {signal.total_score}/100 {grade_emoji}{signal.grade}" if signal.total_score > 0 else ""
        feature_info = f" | FEATURES: {signal.get_feature_summary()}"
        db_info = f" | DB: {signal.db_doc_id[:16] if signal.db_doc_id else 'None'}..."

        logger.info(
            f"{EMOJI['UNLOCK']} SIGNAL_UNLOCK: {symbol} {old_status} -> {status_str} | "
            f"PnL: ${signal.pnl:.2f} ({signal.pnl_percent:.2f}%) | "
            f"Fees: ${signal.fees:.4f} | Bars: {signal.bar_count} | "
            f"Age: {signal.get_age_minutes():.1f}min{score_info}{feature_info}{db_info}"
        )
        return signal

    def check_active_signal(self, symbol: str, current_price: float,
                           last_candle: Dict) -> Tuple[str, float, Optional[SignalData]]:
        """
        Check active signal for TP/SL/BreakEven.
        NO EXPIRY - only TP/SL/BreakEven closes the signal.
        """
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

        # ========== CHECK SL/TP ==========
        if signal.signal_type == "BUY":
            if current_price <= signal.stop_loss:
                updated = self.unlock_symbol(symbol, TradeLifecycle.LOSS, current_price)
                return TradeLifecycle.LOSS.value, current_price - signal.entry_price, updated
            if current_price >= signal.take_profit:
                updated = self.unlock_symbol(symbol, TradeLifecycle.PROFIT, current_price)
                return TradeLifecycle.PROFIT.value, current_price - signal.entry_price, updated
            if current_price > signal.highest_price:
                signal.highest_price = current_price
        else:
            if current_price >= signal.stop_loss:
                updated = self.unlock_symbol(symbol, TradeLifecycle.LOSS, current_price)
                return TradeLifecycle.LOSS.value, signal.entry_price - current_price, updated
            if current_price <= signal.take_profit:
                updated = self.unlock_symbol(symbol, TradeLifecycle.PROFIT, current_price)
                return TradeLifecycle.PROFIT.value, signal.entry_price - current_price, updated
            if current_price < signal.lowest_price:
                signal.lowest_price = current_price

        # ========== BREAK-EVEN AFTER 8 HOURS ==========
        if age_minutes > self.BREAK_EVEN_THRESHOLD_MINUTES:
            price_diff_pct = abs((current_price - signal.entry_price) / signal.entry_price)
            if price_diff_pct < self.BREAK_EVEN_PRICE_THRESHOLD:
                updated = self.unlock_symbol(symbol, TradeLifecycle.BREAK_EVEN, current_price)
                return TradeLifecycle.BREAK_EVEN.value, 0, updated

        return "ACTIVE", current_price - signal.entry_price, signal

    def get_all_active_signals(self) -> Dict[str, SignalData]:
        return self.active_signals.copy()

    def get_signal(self, symbol: str) -> Optional[SignalData]:
        return self.active_signals.get(symbol)

    def remove_signal(self, symbol: str) -> bool:
        if symbol in self.active_signals:
            del self.active_signals[symbol]
            self.stats.active_signals = len(self.active_signals)
            return True
        return False

    def get_stats(self) -> Dict:
        """Get signal manager statistics with v3.3.0 features."""
        return {
            "active": len(self.active_signals),
            "history": len(self.signal_history),
            "stats": self.stats.to_dict(),
            "active_symbols": list(self.active_signals.keys()),
            "recent_signals": [
                {
                    "symbol": s.symbol, "type": s.signal_type, "entry": s.entry_price,
                    "status": s.status, "time": s.entry_time, "bars": s.bar_count,
                    "pnl": s.pnl, "pnl_percent": s.pnl_percent,
                    "strength": s.signal_strength, "risk_multiplier": s.risk_multiplier,
                    "restored": s.restored_from_db, "has_conflict": s.has_conflict,
                    "ltf_confirmed": s.ltf_confirmed, "htf_aligned": s.htf_aligned,
                    "total_score": s.total_score, "grade": s.grade,
                    "component_scores": s.get_component_summary(),
                    "db_doc_id": s.db_doc_id,
                    # NEW v3.3.0
                    "divergence": s.divergence_detected,
                    "pattern": s.candle_pattern,
                    "sr": s.sr_confirmed,
                    "session": s.session,
                }
                for s in self.signal_history[-10:]
            ],
            "grade_summary": {
                "grade_a": self.stats.grade_a_signals,
                "grade_b": self.stats.grade_b_signals,
                "grade_c_rejected": self.stats.grade_c_rejected,
                "grade_a_active": sum(1 for s in self.active_signals.values() if s.grade == "A"),
                "grade_b_active": sum(1 for s in self.active_signals.values() if s.grade == "B"),
            },
            "score_summary": {
                "min_threshold": self.MIN_SIGNAL_SCORE,
                "high_threshold": self.HIGH_SCORE_THRESHOLD,
                "grade_a_threshold": self.GRADE_A_THRESHOLD,
                "grade_b_threshold": self.GRADE_B_THRESHOLD,
                "approved": self.stats.score_approved,
                "rejected": self.stats.score_rejected,
            },
            "database": {
                "enabled": self.db_enabled,
                "saves": self.stats.db_saves,
                "updates": self.stats.db_updates,
                "restores": self.stats.db_restores,
                "errors": self.stats.db_errors,
            },
            # NEW v3.3.0
            "feature_stats": {
                "divergence_signals": self.stats.divergence_signals,
                "pattern_signals": self.stats.pattern_signals,
                "sr_signals": self.stats.sr_signals,
                "squeeze_signals": self.stats.squeeze_signals,
                "session_adjusted": self.stats.session_adjusted,
            },
            "config": {
                "symbol_cooldown_minutes": self.SYMBOL_COOLDOWN_MINUTES,
                "break_even_threshold_minutes": self.BREAK_EVEN_THRESHOLD_MINUTES,
                "signal_expiry": "None (No expiry)",
                "max_signals_per_hour": self.MAX_SIGNALS_PER_HOUR,
                "min_bars_before_check": self.MIN_BARS_BEFORE_CHECK,
                "min_signal_age_seconds": self.MIN_SIGNAL_AGE_SECONDS,
                "version": "3.3.0",
            }
        }

    def clear_expired(self, max_age_minutes: int = None):
        """Clear expired signals (no-op for no expiry)."""
        pass

    def get_active_count(self) -> int:
        return len(self.active_signals)

    def get_active_symbols(self) -> List[str]:
        return list(self.active_signals.keys())

    def get_restored_count(self) -> int:
        return self.stats.restored_signals

    def has_active_signal(self, symbol: str) -> bool:
        return symbol in self.active_signals

    def get_high_score_signals(self) -> List[SignalData]:
        return [s for s in self.active_signals.values() if s.is_high_score()]

    def get_signals_by_score(self, min_score: int = 0) -> List[SignalData]:
        return [s for s in self.active_signals.values() if s.total_score >= min_score]

    def get_score_distribution(self) -> Dict[str, int]:
        grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for s in self.active_signals.values():
            grade = s.grade or s.get_score_grade()
            if grade in grades: grades[grade] += 1
        return grades

    def override_conflict(self, symbol: str) -> bool:
        if symbol not in self._conflict_cache: return False
        if symbol in self.active_signals:
            signal = self.active_signals[symbol]
            if signal.has_conflict:
                signal.has_conflict = False
                signal.conflict_reason = "Overridden by user"
                self._conflict_cache[symbol]['overridden'] = True
                self.stats.conflicts_overridden += 1
                return True
        return False

    def get_conflict_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._conflict_cache.get(symbol)

    def get_signal_strength_stats(self) -> Dict[str, int]:
        hard_count = sum(1 for s in self.active_signals.values() if s.is_hard_signal())
        soft_count = sum(1 for s in self.active_signals.values() if s.is_soft_signal())
        return {
            "hard_active": hard_count,
            "soft_active": soft_count,
            "hard_total": self.stats.hard_signals,
            "soft_total": self.stats.soft_signals
        }

    def get_grade_stats(self) -> Dict[str, int]:
        grades = {"A": 0, "B": 0, "C": 0, "D": 0}
        for s in self.active_signals.values():
            if s.grade in grades:
                grades[s.grade] += 1
        return grades

    def get_db_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.db_enabled,
            "client_available": self.db_client is not None,
            "stats": {
                "saves": self.stats.db_saves,
                "updates": self.stats.db_updates,
                "restores": self.stats.db_restores,
                "errors": self.stats.db_errors,
            }
        }


# Create singleton instance
signal_manager = SignalManager()

__all__ = [
    "signal_manager",
    "SignalManager",
    "SignalData",
    "SignalStats",
    "TradeLifecycle"
]
