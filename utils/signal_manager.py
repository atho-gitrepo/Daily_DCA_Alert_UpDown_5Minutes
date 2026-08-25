"""
Signal Manager - Handles signal lifecycle, debouncing, and duplicate prevention
ALIGNED: Super TDI + Super Bollinger Bands Strategy with 1-Hour Holds
Version: 3.4.1 - FIXED: Lower grade thresholds for more signals
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
    "DIVERGENCE": "↩️", "PATTERN": "🕯️", "S_R": "📊", "SESSION": "🌍",
    "STRUCTURE": "🏗️", "REGIME": "📈", "STATE": "🔄",
    "TDI": "📈", "BB": "📊", "CANDLE": "🕯️", "CHEAT": "📋",
    "AI": "🤖", "APPROVE": "✅", "REJECT": "🚫", "EXIT": "⏰",
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
    AI_REJECTED = "AI_REJECTED"
    AI_WAITING = "AI_WAITING"
    EXIT_1H = "EXIT_1H"  # 1-hour forced exit


@dataclass
class SignalData:
    """Signal data structure aligned with Super TDI + Super BB strategy."""
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

    # Super TDI fields
    tdi_level: float = 0.0
    tdi_zone: str = "NEUTRAL"
    tdi_zone_description: str = ""
    tdi_fast: float = 0.0
    tdi_slow: float = 0.0
    tdi_bullish_cross: bool = False
    tdi_bearish_cross: bool = False

    # Super Bollinger Bands fields
    bb_position: float = 0.5
    bb_touch_lower: bool = False
    bb_touch_upper: bool = False
    bb_candles_shrinking: bool = False
    bb_reversal_confirm: bool = False
    bb_squeeze: bool = False

    # Strategy checklist (5 conditions)
    condition_1_tdi_zone: bool = False
    condition_2_tdi_cross: bool = False
    condition_3_bb_touch: bool = False
    condition_4_candles_shrinking: bool = False
    condition_5_reversal_confirm: bool = False
    conditions_met: int = 0
    conditions_total: int = 5

    # Cheat sheet
    cheat_sheet: str = ""

    # AI fields
    ai_decision: str = "PENDING"
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    ai_validated: bool = False
    ai_response_time_ms: float = 0.0

    # Risk
    rrr: float = 0.0
    signal_strength: str = "SOFT"
    risk_multiplier: float = 1.0

    # Quality
    quality_score: int = 50
    total_score: int = 0
    grade: str = ""

    # Features
    divergence_detected: bool = False
    divergence_type: str = ""
    candle_pattern: str = "NONE"
    sr_confirmed: bool = False
    session: str = "UNKNOWN"
    session_multiplier: float = 1.0

    raw_data: Dict = field(default_factory=dict)
    bar_count: int = 0
    min_bars_before_check: int = 3
    min_age_seconds_before_check: int = 300  # 5 minutes
    max_hold_minutes: int = 60  # 1 hour
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
            "tdi_zone_description": self.tdi_zone_description,
            "tdi_fast": self.tdi_fast,
            "tdi_slow": self.tdi_slow,
            "tdi_bullish_cross": self.tdi_bullish_cross,
            "tdi_bearish_cross": self.tdi_bearish_cross,
            "bb_position": self.bb_position,
            "bb_touch_lower": self.bb_touch_lower,
            "bb_touch_upper": self.bb_touch_upper,
            "bb_candles_shrinking": self.bb_candles_shrinking,
            "bb_reversal_confirm": self.bb_reversal_confirm,
            "bb_squeeze": self.bb_squeeze,
            "conditions_met": self.conditions_met,
            "condition_1_tdi_zone": self.condition_1_tdi_zone,
            "condition_2_tdi_cross": self.condition_2_tdi_cross,
            "condition_3_bb_touch": self.condition_3_bb_touch,
            "condition_4_candles_shrinking": self.condition_4_candles_shrinking,
            "condition_5_reversal_confirm": self.condition_5_reversal_confirm,
            "cheat_sheet": self.cheat_sheet[:500] if self.cheat_sheet else "",
            "ai_decision": self.ai_decision,
            "ai_confidence": self.ai_confidence,
            "ai_reasoning": self.ai_reasoning[:200] if self.ai_reasoning else "",
            "ai_validated": self.ai_validated,
            "ai_response_time_ms": self.ai_response_time_ms,
            "rrr": self.rrr,
            "signal_strength": self.signal_strength,
            "risk_multiplier": self.risk_multiplier,
            "quality_score": self.quality_score,
            "total_score": self.total_score,
            "grade": self.grade,
            "divergence_detected": self.divergence_detected,
            "divergence_type": self.divergence_type,
            "candle_pattern": self.candle_pattern,
            "sr_confirmed": self.sr_confirmed,
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

    def get_conditions_summary(self) -> str:
        """Get summary of conditions met."""
        conditions = []
        if self.condition_1_tdi_zone:
            conditions.append("✅ TDI Zone")
        if self.condition_2_tdi_cross:
            conditions.append("✅ TDI Cross")
        if self.condition_3_bb_touch:
            conditions.append("✅ BB Touch")
        if self.condition_4_candles_shrinking:
            conditions.append("✅ Candles Shrinking")
        if self.condition_5_reversal_confirm:
            conditions.append("✅ Reversal Confirm")
        return f"{len(conditions)}/{self.conditions_total}: " + " | ".join(conditions) if conditions else "No conditions met"

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

    def get_ai_summary(self) -> str:
        """Get AI decision summary."""
        if self.ai_decision == "APPROVE":
            return f"🤖 APPROVED (Conf: {self.ai_confidence*100:.0f}%)"
        elif self.ai_decision == "REJECT":
            return f"🚫 REJECTED: {self.ai_reasoning[:50]}..."
        elif self.ai_decision == "WAIT":
            return f"⏳ WAITING: {self.ai_reasoning[:50]}..."
        else:
            return "⏳ PENDING"

    def get_hold_status(self) -> str:
        """Get hold status for display."""
        age_minutes = self.get_age_minutes()
        remaining = max(0, self.max_hold_minutes - age_minutes)
        return f"{age_minutes:.0f}min / {self.max_hold_minutes}min ({remaining:.0f}min remaining)"


class SignalManager:
    """
    Manages trading signals aligned with Super TDI + Super BB strategy.
    Supports 1-hour holds with TP/SL priority.
    """

    def __init__(self):
        self.active_signals: Dict[str, SignalData] = {}
        self.signal_history: List[SignalData] = []
        self.max_history = 1000
        self.symbol_last_signal: Dict[str, datetime] = {}
        self.symbol_signal_count: Dict[str, int] = {}
        self.global_signal_timestamps: List[datetime] = []

        # ===== CONFIGURATION FOR 1-HOUR HOLDS =====
        self.SYMBOL_COOLDOWN_MINUTES = 30
        self.GLOBAL_COOLDOWN_SECONDS = 15
        self.MAX_SIGNALS_PER_HOUR = 8

        # === Exit Rules ===
        self.MAX_HOLD_MINUTES = 60          # Exit after 1 hour
        self.MIN_HOLD_MINUTES = 15          # Minimum 15 minutes before checking
        self.BREAK_EVEN_THRESHOLD_MINUTES = 60  # Check break-even at 1 hour
        self.BREAK_EVEN_PRICE_THRESHOLD = 0.001  # 0.1% for break-even

        # === Check Timing ===
        self.MIN_BARS_BEFORE_CHECK = 3      # 3 bars (15 min) before checking
        self.MIN_SIGNAL_AGE_SECONDS = 300   # 5 minutes minimum hold

        # === FIXED: Lower Grade Thresholds for More Signals ===
        self.GRADE_A_PLUS_THRESHOLD = 90
        self.GRADE_A_THRESHOLD = 80          # Changed from 82
        self.GRADE_B_PLUS_THRESHOLD = 72     # Changed from 75
        self.GRADE_B_THRESHOLD = 60          # Changed from 70
        self.GRADE_C_THRESHOLD = 50          # Changed from 60

        # === FIXED: Lower Minimum Signal Score ===
        self.MIN_SIGNAL_SCORE = 50           # Changed from 70

        self._signal_cache: Dict[str, Tuple[datetime, str]] = {}
        self._signal_cache_ttl = 600

        self.db_client = db_client
        self.db_enabled = self.db_client is not None and self.db_client.is_available() if self.db_client is not None else False

        logger.info(f"✅ SIGNAL_MANAGER v3.4.1: Initialized")
        logger.info(f"  - Strategy: Super TDI + Super Bollinger Bands")
        logger.info(f"  - Max Hold: {self.MAX_HOLD_MINUTES} minutes (1 hour)")
        logger.info(f"  - Min Hold: {self.MIN_HOLD_MINUTES} minutes")
        logger.info(f"  - Break-Even: {self.BREAK_EVEN_THRESHOLD_MINUTES} minutes")
        logger.info(f"  - Grade A+: {self.GRADE_A_PLUS_THRESHOLD}+")
        logger.info(f"  - Grade A: {self.GRADE_A_THRESHOLD}+")
        logger.info(f"  - Grade B+: {self.GRADE_B_PLUS_THRESHOLD}+")
        logger.info(f"  - Grade B: {self.GRADE_B_THRESHOLD}+")
        logger.info(f"  - Grade C: {self.GRADE_C_THRESHOLD}+")
        logger.info(f"  - Min Signal Score: {self.MIN_SIGNAL_SCORE}")

    def _get_grade(self, score: int) -> str:
        """Get grade based on score - FIXED to accept more signals."""
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
        """Lock a symbol with a new signal (Super TDI + Super BB strategy)."""
        try:
            total_score = raw_data.get('total_score', 0)
            # If total_score not set, use quality_score
            if total_score == 0:
                total_score = raw_data.get('quality_score', 0)

            grade = self._get_grade(total_score)

            # Extract strategy-specific fields
            conditions_met = raw_data.get('conditions_met', 0)
            conditions_total = raw_data.get('conditions_total', 5)

            # === FIXED: More lenient condition check ===
            # Allow signals with 3+ conditions (was rejecting < 3)
            if conditions_met < 3:
                logger.warning(f"{EMOJI['REJECT']} Only {conditions_met}/{conditions_total} conditions met for {symbol}")
                return False

            # === FIXED: Accept C grade signals (was rejecting C and D) ===
            # Only reject D grade (below 50)
            if grade == "D":
                logger.warning(f"{EMOJI['REJECT']} Grade {grade} signal rejected for {symbol} (score: {total_score})")
                return False

            # === FIXED: Accept signals with score >= 50 ===
            if total_score < self.MIN_SIGNAL_SCORE:
                logger.warning(f"{EMOJI['REJECT']} Score {total_score} below minimum {self.MIN_SIGNAL_SCORE} for {symbol}")
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

            # Create SignalData with all fields
            signal = SignalData(
                symbol=symbol,
                signal_type=signal_type,
                entry_price=entry_price,
                entry_time=datetime.now().isoformat(),
                stop_loss=raw_data.get('stop_loss'),
                take_profit=raw_data.get('take_profit'),
                confidence=raw_data.get('confidence', 0.5),

                # Super TDI
                tdi_level=raw_data.get('tdi_level', 50),
                tdi_zone=raw_data.get('tdi_zone', 'NEUTRAL'),
                tdi_zone_description=raw_data.get('tdi_zone_description', ''),
                tdi_fast=raw_data.get('tdi_fast', 50),
                tdi_slow=raw_data.get('tdi_slow', 50),
                tdi_bullish_cross=raw_data.get('tdi_bullish_cross', False),
                tdi_bearish_cross=raw_data.get('tdi_bearish_cross', False),

                # Super BB
                bb_position=raw_data.get('bb_position', 0.5),
                bb_touch_lower=raw_data.get('touch_lower', False),
                bb_touch_upper=raw_data.get('touch_upper', False),
                bb_candles_shrinking=raw_data.get('candles_shrinking', False),
                bb_reversal_confirm=raw_data.get('reversal_confirm', False),
                bb_squeeze=raw_data.get('bb_squeeze', False),

                # Conditions
                condition_1_tdi_zone=raw_data.get('condition_1_tdi_zone', False),
                condition_2_tdi_cross=raw_data.get('condition_2_tdi_cross', False),
                condition_3_bb_touch=raw_data.get('condition_3_bb_touch', False),
                condition_4_candles_shrinking=raw_data.get('condition_4_candles_shrinking', False),
                condition_5_reversal_confirm=raw_data.get('condition_5_reversal_confirm', False),
                conditions_met=conditions_met,
                conditions_total=conditions_total,

                # Cheat sheet
                cheat_sheet=raw_data.get('cheat_sheet', ''),

                # AI
                ai_decision=raw_data.get('ai_decision', 'PENDING'),
                ai_confidence=raw_data.get('ai_confidence', 0.0),
                ai_reasoning=raw_data.get('ai_reasoning', ''),
                ai_validated=raw_data.get('ai_validated', False),
                ai_response_time_ms=raw_data.get('ai_response_time_ms', 0.0),

                # Risk
                rrr=raw_data.get('rrr', 0),
                signal_strength=raw_data.get('signal_strength', 'SOFT'),
                risk_multiplier=raw_data.get('risk_multiplier', 1.0),

                # Quality
                quality_score=raw_data.get('quality_score', 50),
                total_score=total_score,
                grade=grade,

                # Features
                divergence_detected=raw_data.get('divergence_detected', False),
                divergence_type=raw_data.get('divergence_type', ''),
                candle_pattern=raw_data.get('candle_pattern', 'NONE'),
                sr_confirmed=raw_data.get('sr_confirmed', False),
                session=raw_data.get('session', 'UNKNOWN'),
                session_multiplier=raw_data.get('session_multiplier', 1.0),

                raw_data=raw_data,
                min_bars_before_check=self.MIN_BARS_BEFORE_CHECK,
                min_age_seconds_before_check=self.MIN_SIGNAL_AGE_SECONDS,
                max_hold_minutes=self.MAX_HOLD_MINUTES,
                highest_price=entry_price,
                lowest_price=entry_price,
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
                f"@ {entry_price:.4f} | Conditions: {conditions_met}/{conditions_total} | "
                f"Grade: {grade} | Score: {total_score} | AI: {signal.ai_decision} | "
                f"Features: {signal.get_feature_summary()}"
            )
            return True

        except Exception as e:
            logger.error(f"{EMOJI['ERROR']} Error locking symbol {symbol}: {e}")
            import traceback
            traceback.print_exc()
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
        """
        Check active signal for TP/SL/BreakEven.

        Exit Rules (in priority order):
        1. Stop Loss hit → EXIT LOSS
        2. Take Profit hit → EXIT PROFIT
        3. 1-hour hold expired → FORCE EXIT
        4. Break-even after 1 hour → EXIT BREAK-EVEN
        5. Otherwise → ACTIVE
        """
        if symbol not in self.active_signals:
            return "NO_SIGNAL", 0, None

        signal = self.active_signals[symbol]
        signal.bar_count += 1
        signal.last_checked_at = datetime.now().isoformat()

        # Update highest/lowest prices
        if signal.highest_price is None or current_price > signal.highest_price:
            signal.highest_price = current_price
        if signal.lowest_price is None or current_price < signal.lowest_price:
            signal.lowest_price = current_price

        age_seconds = signal.get_age_seconds()
        age_minutes = age_seconds / 60

        # ===== RULE 1: MINIMUM HOLD TIME =====
        if signal.bar_count < signal.min_bars_before_check:
            return "ACTIVE", current_price - signal.entry_price, signal
        if age_seconds < signal.min_age_seconds_before_check:
            return "ACTIVE", current_price - signal.entry_price, signal

        # ===== RULE 2: CHECK STOP LOSS =====
        if signal.signal_type == "BUY":
            if current_price <= signal.stop_loss:
                updated = self._unlock_symbol(symbol, TradeLifecycle.LOSS, current_price)
                logger.info(f"{EMOJI['LOSS']} {symbol}: SL HIT at ${current_price:.4f}")
                return TradeLifecycle.LOSS.value, current_price - signal.entry_price, updated
        else:
            if current_price >= signal.stop_loss:
                updated = self._unlock_symbol(symbol, TradeLifecycle.LOSS, current_price)
                logger.info(f"{EMOJI['LOSS']} {symbol}: SL HIT at ${current_price:.4f}")
                return TradeLifecycle.LOSS.value, signal.entry_price - current_price, updated

        # ===== RULE 3: CHECK TAKE PROFIT =====
        if signal.signal_type == "BUY":
            if current_price >= signal.take_profit:
                updated = self._unlock_symbol(symbol, TradeLifecycle.PROFIT, current_price)
                logger.info(f"{EMOJI['PROFIT']} {symbol}: TP HIT at ${current_price:.4f}")
                return TradeLifecycle.PROFIT.value, current_price - signal.entry_price, updated
        else:
            if current_price <= signal.take_profit:
                updated = self._unlock_symbol(symbol, TradeLifecycle.PROFIT, current_price)
                logger.info(f"{EMOJI['PROFIT']} {symbol}: TP HIT at ${current_price:.4f}")
                return TradeLifecycle.PROFIT.value, signal.entry_price - current_price, updated

        # ===== RULE 4: FORCE EXIT AFTER 1 HOUR =====
        if age_minutes >= self.MAX_HOLD_MINUTES:
            updated = self._unlock_symbol(symbol, TradeLifecycle.EXIT_1H, current_price)
            logger.info(f"{EMOJI['EXIT']} {symbol}: 1-HOUR FORCE EXIT at ${current_price:.4f} | PnL: ${updated.pnl:.2f}")
            return "EXIT_1H", current_price - signal.entry_price, updated

        # ===== RULE 5: BREAK-EVEN CHECK AT 1 HOUR =====
        if age_minutes >= self.BREAK_EVEN_THRESHOLD_MINUTES:
            price_diff_pct = abs((current_price - signal.entry_price) / signal.entry_price)
            if price_diff_pct < self.BREAK_EVEN_PRICE_THRESHOLD:
                updated = self._unlock_symbol(symbol, TradeLifecycle.BREAK_EVEN, current_price)
                logger.info(f"{EMOJI['BREAK']} {symbol}: BREAK-EVEN at ${current_price:.4f}")
                return TradeLifecycle.BREAK_EVEN.value, 0, updated

        # ===== RULE 6: ACTIVE =====
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

        # Calculate PnL
        if signal.signal_type == "BUY":
            signal.pnl = exit_price - signal.entry_price
        else:
            signal.pnl = signal.entry_price - exit_price
        signal.pnl_percent = (signal.pnl / signal.entry_price) * 100 if signal.entry_price > 0 else 0

        # Calculate fees (0.11% total - entry + exit)
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

        # Log exit details
        hold_minutes = signal.get_age_minutes()
        logger.info(
            f"{EMOJI['UNLOCK']} SIGNAL_UNLOCK: {symbol} {old_status} -> {status_str} | "
            f"PnL: ${signal.pnl:.2f} ({signal.pnl_percent:.2f}%) | "
            f"Hold: {hold_minutes:.1f}min | "
            f"Bars: {signal.bar_count} | "
            f"Conditions: {signal.conditions_met}/{signal.conditions_total}"
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
        """Get signal manager statistics."""
        active_count = len(self.active_signals)
        total_conditions = sum(s.conditions_met for s in self.active_signals.values()) if active_count > 0 else 0

        return {
            "active": active_count,
            "history": len(self.signal_history),
            "active_symbols": list(self.active_signals.keys()),
            "grade_summary": {
                "a_plus": sum(1 for s in self.active_signals.values() if s.grade == "A+"),
                "a": sum(1 for s in self.active_signals.values() if s.grade == "A"),
                "b_plus": sum(1 for s in self.active_signals.values() if s.grade == "B+"),
                "b": sum(1 for s in self.active_signals.values() if s.grade == "B"),
                "c": sum(1 for s in self.active_signals.values() if s.grade == "C"),
            },
            "conditions_summary": {
                "avg_conditions_met": total_conditions / max(1, active_count),
                "max_conditions": max([s.conditions_met for s in self.active_signals.values()]) if self.active_signals else 0,
            },
            "ai_summary": {
                "approved": sum(1 for s in self.active_signals.values() if s.ai_decision == "APPROVE"),
                "rejected": sum(1 for s in self.active_signals.values() if s.ai_decision == "REJECT"),
                "waiting": sum(1 for s in self.active_signals.values() if s.ai_decision == "WAIT"),
                "pending": sum(1 for s in self.active_signals.values() if s.ai_decision == "PENDING"),
            },
            "exit_rules": {
                "max_hold_minutes": self.MAX_HOLD_MINUTES,
                "min_hold_minutes": self.MIN_HOLD_MINUTES,
                "break_even_minutes": self.BREAK_EVEN_THRESHOLD_MINUTES,
                "min_bars_check": self.MIN_BARS_BEFORE_CHECK,
            },
            "version": "3.4.1"
        }


# Singleton
signal_manager = SignalManager()
