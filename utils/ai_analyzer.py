"""
AI Strategic Advisor for Trading Signals - HYBRID STRATEGY.
UPDATED v3.3.0: Added Divergence, Candle Patterns, S/R, Session Filtering support
Version: 3.3.0 - ENHANCED: New signal features in analysis
"""

import json
import logging
import time
import asyncio
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import re
from collections import deque
from enum import Enum

# Groq AI imports
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logging.warning("Groq library not installed. AI features will be disabled.")

# Local imports
from settings import config, Config

# Configure logging
logger = logging.getLogger(__name__)
ai_logger = logging.getLogger("ai_analyzer")

EMOJI = {
    "START": "🚀", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️",
    "INFO": "ℹ️", "DEBUG": "🔍", "AI": "🤖", "VALIDATE": "✔️",
    "SENTIMENT": "📊", "RISK": "🎯", "LEVERAGE": "⚡", "CACHE": "💾",
    "ANALYZE": "🔬", "RECOMMEND": "📈", "EXPLAIN": "📝", "RETRY": "🔄",
    "SNIPER": "🎯", "PROFIT": "💰", "REJECT": "🚫", "WAIT": "⏳",
    "RATE": "🚀", "LTF": "⏱️", "CONFLICT": "⚠️", "HTF": "📊",
    "RRR": "📈", "HARD": "🔴", "SOFT": "🟡", "TDI": "📈",
    "BB": "📉", "ZONE": "🎯", "SCORE": "🎯", "COMPONENT": "📊",
    "FILTER": "🔍", "PERFORMANCE": "📈", "LIMIT": "🛑",
    "CLUSTER": "📦", "REDUCE": "✂️", "PRIORITY": "⭐",
    "GRADE_A": "🏆", "GRADE_B": "🥈", "GRADE_C": "🥉",
    "APPROVED": "✅",
    # NEW v3.3.0
    "DIVERGENCE": "↩️", "PATTERN": "🕯️", "S_R": "📊", "SESSION": "🌍",
}


# ========== PERFORMANCE-BASED CRITERIA ==========
PERFORMANCE_CRITERIA = {
    "signal_strength_win_rates": {
        "SOFT": 0.85, "HARD": 0.00,
    },
    "score_grade_win_rates": {
        "A": 0.25, "B": 0.78, "C": 0.43, "D": 0.00, "F": 0.00,
    },
    "tdi_zone_win_rates": {
        "SOFT_BUY": 0.75, "SOFT_SELL": 1.00, "BUY_ZONE": 0.57,
        "NO_TRADE": 0.67, "HARD_BUY": 0.20, "HARD_SELL": 0.20,
        "OVERSOLD": 0.20, "OVERBOUGHT": 0.20,
    },
    "htf_aligned_win_rate": 0.67,
    "htf_not_aligned_win_rate": 0.50,
    "confidence_sweet_spot": [0.88, 0.95],
    "position_sizing": {
        "soft_base": 1.0, "htf_aligned_bonus": 0.20,
        "grade_b_bonus": 0.15, "soft_zone_bonus": 0.10,
        "htf_misaligned_penalty": -0.30,
        "max_multiplier": 1.5, "min_multiplier": 0.5,
        # NEW v3.3.0
        "divergence_bonus": 0.15,
        "pattern_bonus": 0.10,
        "sr_bonus": 0.10,
        "session_penalty_asian": -0.15,
        "session_bonus_ny": 0.10,
    },
}

# ========== SIGNAL REDUCTION RULES ==========
SIGNAL_REDUCTION_RULES = {
    "max_signals_per_day": 5,
    "max_signals_per_4h_window": 2,
    "max_concurrent_signals": 3,
    "min_minutes_between_signals": 30,
    "min_minutes_same_symbol": 120,
    "minimum_signal_score": 70,
    "preferred_score_range": [75, 84],
    "reject_score_above": 84,
    "allow_hard_signals": False,
    "preferred_tdi_zones": ["SOFT_BUY", "SOFT_SELL", "BUY_ZONE", "NO_TRADE"],
    "reject_tdi_zones": ["OVERSOLD", "OVERBOUGHT", "HARD_BUY", "HARD_SELL"],
    "require_ltf_confirmation": True,
    "minimum_ltf_confidence": 0.71,
    "minimum_confidence": 0.85,
    "preferred_confidence_range": [0.88, 0.95],
    "priority_scoring": {
        "grade_b_score": 30,
        "htf_aligned": 25,
        "soft_tdi_zone": 20,
        "ltf_high_confidence": 15,
        "high_volume": 10,
        # NEW v3.3.0
        "divergence": 20,
        "candle_pattern": 15,
        "sr_confirmed": 10,
        "bb_squeeze": 5,
    },
}


@dataclass
class AIAnalysisResult:
    """AI analysis result with v3.3.0 fields."""
    symbol: str = ""
    decision: str = "WAIT"
    confidence: float = 0.5
    risk_level: str = "MEDIUM"
    reasoning: str = ""
    market_analysis: str = ""
    technical_factors: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    recommendation: str = ""
    signal_quality: float = 0.5
    market_alignment: float = 0.5
    probability_success: float = 0.5
    expected_profitability: float = 0.5
    suggested_rrr: Optional[float] = None
    leverage_recommendation: Optional[Dict] = None
    analysis_time: str = field(default_factory=lambda: datetime.now().isoformat())
    raw_response: Optional[str] = None
    ai_validated: bool = False
    has_conflict: bool = False
    conflict_reason: str = ""
    tokens_used: int = 0
    signal_strength: str = "SOFT"
    risk_multiplier: float = 1.0
    total_score: int = 0
    component_scores: Dict[str, float] = field(default_factory=dict)
    score_grade: str = ""
    bb_position: float = 0.5
    volume_ratio: float = 1.0
    position_multiplier: float = 1.0
    performance_win_rate: float = 0.0
    auto_rejected: bool = False
    rejection_category: str = ""
    priority_score: int = 0
    signal_limit_rejected: bool = False
    cluster_rejected: bool = False

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
    feature_bonus_total: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "symbol": self.symbol, "decision": self.decision,
            "confidence": self.confidence, "risk_level": self.risk_level,
            "reasoning": self.reasoning[:150] if self.reasoning else "",
            "market_analysis": self.market_analysis[:100] if self.market_analysis else "",
            "technical_factors": self.technical_factors[:3],
            "risk_factors": self.risk_factors[:3],
            "recommendation": self.recommendation,
            "signal_quality": self.signal_quality,
            "market_alignment": self.market_alignment,
            "probability_success": self.probability_success,
            "expected_profitability": self.expected_profitability,
            "suggested_rrr": self.suggested_rrr,
            "analysis_time": self.analysis_time,
            "ai_validated": self.ai_validated,
            "has_conflict": self.has_conflict,
            "conflict_reason": self.conflict_reason,
            "tokens_used": self.tokens_used,
            "signal_strength": self.signal_strength,
            "risk_multiplier": self.risk_multiplier,
            "total_score": self.total_score,
            "component_scores": self.component_scores,
            "score_grade": self.score_grade,
            "bb_position": self.bb_position,
            "volume_ratio": self.volume_ratio,
            "position_multiplier": self.position_multiplier,
            "performance_win_rate": self.performance_win_rate,
            "auto_rejected": self.auto_rejected,
            "rejection_category": self.rejection_category,
            "priority_score": self.priority_score,
            "signal_limit_rejected": self.signal_limit_rejected,
            "cluster_rejected": self.cluster_rejected,
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
            "feature_bonus_total": self.feature_bonus_total,
        }
        if self.leverage_recommendation:
            result["leverage_recommendation"] = self.leverage_recommendation
        return result


class SignalLimiter:
    """Signal limiter to reduce overtrading."""

    def __init__(self):
        self.daily_signals: List[Dict] = []
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.symbol_last_trade: Dict[str, datetime] = {}
        self.last_signal_time: Optional[datetime] = None
        self.window_signals: List[datetime] = []
        self.window_hours = 4

        self.metrics = {
            "signals_allowed": 0,
            "signals_blocked_daily_limit": 0,
            "signals_blocked_cluster": 0,
            "signals_blocked_symbol_cooldown": 0,
            "signals_blocked_window_limit": 0,
        }

    def _reset_daily_if_needed(self):
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if now > self.daily_reset_time:
            self.daily_signals = []
            self.daily_reset_time = now

    def _clean_window_signals(self):
        now = datetime.now()
        cutoff = now - timedelta(hours=self.window_hours)
        self.window_signals = [t for t in self.window_signals if t > cutoff]

    def can_send_signal(self, symbol: str, signal_time: Optional[datetime] = None) -> Tuple[bool, str, int]:
        self._reset_daily_if_needed()
        self._clean_window_signals()

        now = signal_time or datetime.now()

        if len(self.daily_signals) >= SIGNAL_REDUCTION_RULES["max_signals_per_day"]:
            self.metrics["signals_blocked_daily_limit"] += 1
            return False, f"Daily limit reached ({SIGNAL_REDUCTION_RULES['max_signals_per_day']} signals)", 0

        if len(self.window_signals) >= SIGNAL_REDUCTION_RULES["max_signals_per_4h_window"]:
            self.metrics["signals_blocked_window_limit"] += 1
            return False, f"4h window limit reached ({SIGNAL_REDUCTION_RULES['max_signals_per_4h_window']} signals)", 0

        if self.last_signal_time:
            minutes_since = (now - self.last_signal_time).total_seconds() / 60
            if minutes_since < SIGNAL_REDUCTION_RULES["min_minutes_between_signals"]:
                remaining = SIGNAL_REDUCTION_RULES["min_minutes_between_signals"] - minutes_since
                self.metrics["signals_blocked_cluster"] += 1
                return False, f"Too soon: {remaining:.0f}min until next signal", 0

        if symbol in self.symbol_last_trade:
            minutes_since_symbol = (now - self.symbol_last_trade[symbol]).total_seconds() / 60
            if minutes_since_symbol < SIGNAL_REDUCTION_RULES["min_minutes_same_symbol"]:
                remaining = SIGNAL_REDUCTION_RULES["min_minutes_same_symbol"] - minutes_since_symbol
                self.metrics["signals_blocked_symbol_cooldown"] += 1
                return False, f"Symbol cooldown: {remaining:.0f}min for {symbol}", 0

        remaining_slots = SIGNAL_REDUCTION_RULES["max_signals_per_day"] - len(self.daily_signals)

        self.metrics["signals_allowed"] += 1
        return True, f"OK (slots remaining: {remaining_slots})", remaining_slots

    def record_signal(self, symbol: str, signal_time: Optional[datetime] = None):
        now = signal_time or datetime.now()
        self.daily_signals.append({"symbol": symbol, "time": now})
        self.symbol_last_trade[symbol] = now
        self.last_signal_time = now
        self.window_signals.append(now)

    def get_remaining_slots(self) -> int:
        self._reset_daily_if_needed()
        return max(0, SIGNAL_REDUCTION_RULES["max_signals_per_day"] - len(self.daily_signals))

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.metrics,
            "signals_today": len(self.daily_signals),
            "remaining_slots": self.get_remaining_slots(),
            "max_per_day": SIGNAL_REDUCTION_RULES["max_signals_per_day"],
            "symbols_on_cooldown": list(self.symbol_last_trade.keys()),
        }


class LeverageCalculator:
    """Leverage calculation utility."""

    MAX_LEVERAGE = {
        "BTCUSDT": 100, "ETHUSDT": 50, "BNBUSDT": 30, "SOLUSDT": 20,
        "XRPUSDT": 20, "ADAUSDT": 20, "DOGEUSDT": 20, "AVAXUSDT": 20,
        "DOTUSDT": 20, "TRXUSDT": 20, "BCHUSDT": 20, "LTCUSDT": 20,
        "UNIUSDT": 20, "NEARUSDT": 20, "ETCUSDT": 20, "XLMUSDT": 20,
        "APTUSDT": 20, "SUIUSDT": 20, "IMXUSDT": 20, "FILUSDT": 20,
        "ATOMUSDT": 20, "VETUSDT": 20,
    }

    VOLATILITY_LEVELS = {"LOW": 0.02, "MEDIUM": 0.05, "HIGH": 0.08, "EXTREME": 0.12}

    @classmethod
    def get_max_leverage_for_symbol(cls, symbol: str) -> int:
        return cls.MAX_LEVERAGE.get(symbol, 20)

    @classmethod
    def calculate_optimal_leverage(cls, symbol: str, volatility: float,
                                   risk_per_trade: float = 0.005,
                                   max_drawdown: float = 0.10,
                                   profile: str = "MODERATE",
                                   signal_quality: float = 0.5,
                                   signal_strength: str = "SOFT",
                                   total_score: int = 0,
                                   position_multiplier: float = 1.0,
                                   feature_bonus_total: float = 0.0) -> Dict[str, Any]:
        """Calculate optimal leverage with feature bonuses."""
        max_allowed = cls.get_max_leverage_for_symbol(symbol)
        risk_based = min(10, (risk_per_trade * 2000))

        if volatility < cls.VOLATILITY_LEVELS["LOW"]:
            vol_multiplier = 1.5
        elif volatility < cls.VOLATILITY_LEVELS["MEDIUM"]:
            vol_multiplier = 1.0
        elif volatility < cls.VOLATILITY_LEVELS["HIGH"]:
            vol_multiplier = 0.7
        elif volatility < cls.VOLATILITY_LEVELS["EXTREME"]:
            vol_multiplier = 0.5
        else:
            vol_multiplier = 0.3

        profile_multipliers = {
            "CONSERVATIVE": 0.3, "MODERATE": 0.6, "AGGRESSIVE": 1.0,
            "PROFESSIONAL": 1.2, "EXTREME": 1.5
        }
        profile_multiplier = profile_multipliers.get(profile.upper(), 0.6)
        quality_multiplier = 0.8 + (signal_quality * 0.4)

        if total_score >= 80: score_multiplier = 1.3
        elif total_score >= 65: score_multiplier = 1.0
        elif total_score > 0: score_multiplier = 0.7
        else: score_multiplier = 1.0

        strength_multiplier = 1.0
        performance_multiplier = max(0.3, position_multiplier)

        # NEW v3.3.0: Feature bonus
        feature_multiplier = 1.0 + feature_bonus_total

        recommended = int(
            risk_based * vol_multiplier * profile_multiplier *
            quality_multiplier * strength_multiplier * score_multiplier *
            performance_multiplier * feature_multiplier
        )

        drawdown_cap = int(max_drawdown / (risk_per_trade * 2))
        recommended = min(recommended, drawdown_cap)
        recommended = min(recommended, max_allowed)
        recommended = max(recommended, 1)

        min_leverage = max(1, int(recommended * 0.5))
        max_leverage = min(max_allowed, int(recommended * 2))

        if recommended <= 3: risk_level = "LOW"
        elif recommended <= 10: risk_level = "MEDIUM"
        elif recommended <= 25: risk_level = "HIGH"
        else: risk_level = "EXTREME"

        base_position = 1.0 / recommended
        position_size = min(0.5, base_position)

        return {
            "recommended_leverage": recommended,
            "min_leverage": min_leverage,
            "max_leverage": max_leverage,
            "risk_level": risk_level,
            "position_size_percent": round(position_size * 100, 1),
            "max_drawdown_percent": max_drawdown * 100,
            "strength_multiplier": strength_multiplier,
            "signal_strength": signal_strength,
            "score_multiplier": score_multiplier,
            "total_score": total_score,
            "performance_multiplier": round(performance_multiplier, 2),
            "feature_multiplier": round(feature_multiplier, 2),
            "feature_bonus_total": round(feature_bonus_total, 2),
        }


class AICache:
    """AI response cache."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 600):
        self.cache = {}
        self.timestamps = {}
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if key not in self.cache: self.misses += 1; return None
        if time.time() - self.timestamps[key] > self.ttl:
            del self.cache[key]; del self.timestamps[key]
            self.misses += 1; return None
        self.hits += 1; return self.cache[key]

    def set(self, key: str, value: Dict[str, Any]):
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.timestamps, key=self.timestamps.get)
            del self.cache[oldest_key]; del self.timestamps[oldest_key]
        self.cache[key] = value; self.timestamps[key] = time.time()

    def clear(self):
        self.cache.clear(); self.timestamps.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {"size": len(self.cache), "hits": self.hits, "misses": self.misses,
                "hit_rate": f"{self.hits/total*100:.1f}%" if total > 0 else "0%"}


def log_ai_operation(operation: str, status: str, details: Optional[Dict] = None,
                     emoji: str = "", error: Optional[Exception] = None):
    """Log AI operations."""
    timestamp = datetime.now().isoformat()
    log_message = f"[{timestamp}] {emoji} AI_{operation}: {status}"
    if details:
        safe_details = {}
        for k, v in details.items():
            if isinstance(v, float): safe_details[k] = round(v, 4)
            elif isinstance(v, str) and len(v) > 100: safe_details[k] = v[:100] + "..."
            else: safe_details[k] = v
        log_message += f" | Details: {safe_details}"
    if error: log_message += f" | Error: {str(error)}"
    if status == "FAILURE": ai_logger.error(log_message)
    elif status == "WARNING": ai_logger.warning(log_message)
    elif status == "START": ai_logger.debug(log_message)
    else: ai_logger.info(log_message)


class AIAnalyzer:
    """
    AI Analyzer with v3.3.0 support for divergence, patterns, S/R, session.
    """

    def __init__(self, enabled: bool = True):
        log_ai_operation("INIT", "START", emoji=EMOJI['START'])

        self.enabled = enabled and GROQ_AVAILABLE and config.groq.enabled
        self.client = None
        self.cache = AICache()
        self.leverage_calculator = LeverageCalculator()
        self.signal_limiter = SignalLimiter()

        # Rate limiting
        self.request_timestamps = deque()
        self.max_requests_per_minute = 2
        self.min_request_interval = 30
        self._last_request_time = 0
        self._lock = asyncio.Lock()

        # Token tracking
        self.daily_tokens_used = 0
        self.max_daily_tokens = 80000
        self.token_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Cooldown tracking
        self._rate_limited_until: Optional[datetime] = None
        self._cooldown_symbols: Dict[str, datetime] = {}
        self._symbol_cooldown_minutes = 15

        # TDI Levels
        self.OVERSOLD = 25.0; self.SOFT_BUY = 35.0; self.CENTER_LINE = 50.0
        self.SOFT_SELL = 65.0; self.OVERBOUGHT = 75.0

        # RRR
        self.MIN_RRR = 1.5; self.MAX_RRR = 4.0; self.DEFAULT_RRR = 2.0

        # Score thresholds
        self.HIGH_SCORE = 80
        self.MEDIUM_SCORE = 65
        self.SCORE_GRADE_A_PLUS = 85
        self.SCORE_GRADE_B_MIN = 75
        self.SCORE_GRADE_B_MAX = 84
        self.SCORE_GRADE_C_MIN = 65

        self.MINIMUM_SIGNAL_SCORE = SIGNAL_REDUCTION_RULES["minimum_signal_score"]

        # Metrics
        self.metrics = {
            "total_requests": 0, "successful_requests": 0, "failed_requests": 0,
            "avg_response_time": 0.0, "rate_limit_hits": 0, "cache_hits": 0,
            "signals_approved": 0, "signals_rejected": 0, "signals_waited": 0,
            "signals_conflicted": 0, "cooldown_skips": 0,
            "ltf_analyzed": 0, "hard_signals": 0, "soft_signals": 0,
            "score_analyzed": 0, "high_score_signals": 0,
            "medium_score_signals": 0, "low_score_signals": 0,
            "decision_breakdown": {"approved": 0, "rejected": 0, "waited": 0, "conflicted": 0},
            "auto_rejected_hard_strength": 0, "auto_rejected_grade_a_plus": 0,
            "auto_rejected_low_score": 0, "auto_rejected_hard_tdi": 0,
            "grade_b_approved": 0, "grade_b_performance_tracked": 0,
            "signal_limit_rejected": 0, "cluster_rejected": 0,
            "signals_blocked_daily_limit": 0,
            # NEW v3.3.0
            "divergence_signals": 0,
            "pattern_signals": 0,
            "sr_signals": 0,
            "squeeze_signals": 0,
            "session_adjusted": 0,
        }

        if self.enabled:
            self._init_client()

        log_ai_operation("INIT", "SUCCESS",
                        {"enabled": self.enabled, "version": "3.3.0"},
                        emoji=EMOJI['SUCCESS'])
        ai_logger.info(f"{EMOJI['AI']} AI_INIT: v3.3.0 (Divergence, Patterns, S/R, Session)")
        ai_logger.info(f"{EMOJI['LIMIT']} Max signals/day: {SIGNAL_REDUCTION_RULES['max_signals_per_day']}")
        ai_logger.info(f"{EMOJI['DIVERGENCE']} Divergence detection: Enabled")
        ai_logger.info(f"{EMOJI['PATTERN']} Candle patterns: Enabled")
        ai_logger.info(f"{EMOJI['S_R']} Support/Resistance: Enabled")
        ai_logger.info(f"{EMOJI['SESSION']} Session filtering: Enabled")

    def _init_client(self):
        """Initialize Groq client."""
        try:
            if not GROQ_AVAILABLE:
                ai_logger.warning(f"{EMOJI['WARNING']} AI_INIT: Groq not available")
                self.enabled = False; return
            api_key = config.groq.api_key
            if not api_key:
                ai_logger.warning(f"{EMOJI['WARNING']} AI_INIT: No API key")
                self.enabled = False; return
            self.client = Groq(api_key=api_key)
            ai_logger.info(f"{EMOJI['SUCCESS']} AI_INIT: Groq client ready")
        except Exception as e:
            ai_logger.error(f"{EMOJI['ERROR']} AI_INIT: {e}")
            self.enabled = False

    def _calculate_priority_score(self, signal_data: Dict[str, Any]) -> int:
        """Calculate priority score with v3.3.0 features."""
        score = 0
        priority = SIGNAL_REDUCTION_RULES["priority_scoring"]

        total_score = signal_data.get('total_score', 0)
        htf_aligned = signal_data.get('htf_aligned', False)
        tdi_zone = signal_data.get('tdi_zone', '')
        ltf_confidence = signal_data.get('ltf_confidence', 0)
        volume_ratio = signal_data.get('volume_ratio', 1.0)

        # Base scoring
        if 75 <= total_score <= 84:
            score += priority["grade_b_score"]
        if htf_aligned:
            score += priority["htf_aligned"]
        if tdi_zone in ["SOFT_BUY", "SOFT_SELL"]:
            score += priority["soft_tdi_zone"]
        if ltf_confidence >= 0.85:
            score += priority["ltf_high_confidence"]
        if volume_ratio > 1.5:
            score += priority["high_volume"]

        # NEW v3.3.0: Feature bonuses
        if signal_data.get('divergence_detected', False):
            score += priority["divergence"]
            ai_logger.debug(f"{EMOJI['DIVERGENCE']} Divergence bonus +{priority['divergence']}")

        if signal_data.get('candle_pattern') and signal_data.get('candle_pattern') != 'NONE':
            score += priority["candle_pattern"]
            ai_logger.debug(f"{EMOJI['PATTERN']} Pattern bonus +{priority['candle_pattern']}")

        if signal_data.get('sr_confirmed', False):
            score += priority["sr_confirmed"]
            ai_logger.debug(f"{EMOJI['S_R']} S/R bonus +{priority['sr_confirmed']}")

        if signal_data.get('bb_squeeze', False):
            score += priority["bb_squeeze"]
            ai_logger.debug(f"{EMOJI['BB']} BB Squeeze bonus +{priority['bb_squeeze']}")

        return score

    def _apply_performance_filters(self, signal_data: Dict[str, Any]) -> Tuple[str, float, str, int]:
        """Apply filters with v3.3.0 feature bonuses."""
        score = signal_data.get('total_score', 0)
        strength = signal_data.get('signal_strength', 'SOFT')
        tdi_zone = signal_data.get('tdi_zone', 'NEUTRAL')
        htf_aligned = signal_data.get('htf_aligned', False)
        ltf_confidence = signal_data.get('ltf_confidence', 0)
        symbol = signal_data.get('symbol', 'UNKNOWN')

        # NEW v3.3.0: Feature bonuses for position sizing
        feature_bonus_total = 0.0
        divergence_detected = signal_data.get('divergence_detected', False)
        candle_pattern = signal_data.get('candle_pattern', 'NONE')
        sr_confirmed = signal_data.get('sr_confirmed', False)
        session = signal_data.get('session', 'UNKNOWN')

        if divergence_detected:
            feature_bonus_total += 0.15
            self.metrics["divergence_signals"] += 1
            ai_logger.info(f"{EMOJI['DIVERGENCE']} Divergence bonus: +0.15")

        if candle_pattern != 'NONE':
            feature_bonus_total += 0.10
            self.metrics["pattern_signals"] += 1
            ai_logger.info(f"{EMOJI['PATTERN']} Pattern bonus: +0.10 ({candle_pattern})")

        if sr_confirmed:
            feature_bonus_total += 0.10
            self.metrics["sr_signals"] += 1
            ai_logger.info(f"{EMOJI['S_R']} S/R bonus: +0.10")

        if signal_data.get('bb_squeeze', False):
            feature_bonus_total += 0.05
            self.metrics["squeeze_signals"] += 1
            ai_logger.info(f"{EMOJI['BB']} BB Squeeze bonus: +0.05")

        # Session adjustment
        if session != 'NY':
            feature_bonus_total -= 0.10
            self.metrics["session_adjusted"] += 1
            ai_logger.info(f"{EMOJI['SESSION']} Session penalty: -0.10 ({session})")

        priority_score = self._calculate_priority_score(signal_data)

        # AUTO-REJECT: HARD signal strength
        if strength == 'HARD':
            self.metrics["auto_rejected_hard_strength"] += 1
            return 'REJECT', 0.0, f"HARD signals: 0% win rate", priority_score

        # AUTO-REJECT: Grade A+ (85+)
        if score >= self.SCORE_GRADE_A_PLUS:
            self.metrics["auto_rejected_grade_a_plus"] += 1
            return 'REJECT', 0.0, f"Grade A+ ({score}): 25% win rate", priority_score

        # AUTO-REJECT: Score below minimum (70)
        if score < self.MINIMUM_SIGNAL_SCORE:
            self.metrics["auto_rejected_low_score"] += 1
            return 'REJECT', 0.0, f"Score {score} < {self.MINIMUM_SIGNAL_SCORE}", priority_score

        # AUTO-REJECT: Hard TDI zones
        if tdi_zone in SIGNAL_REDUCTION_RULES["reject_tdi_zones"]:
            self.metrics["auto_rejected_hard_tdi"] += 1
            return 'REJECT', 0.0, f"Hard TDI: {tdi_zone} (20% win rate)", priority_score

        # CHECK SIGNAL LIMITER
        can_send, limit_reason, remaining_slots = self.signal_limiter.can_send_signal(symbol)
        if not can_send:
            self.metrics["signal_limit_rejected"] += 1
            return 'WAIT', 0.0, f"Signal limit: {limit_reason}", priority_score

        # CALCULATE POSITION MULTIPLIER
        position_multiplier = PERFORMANCE_CRITERIA["position_sizing"]["soft_base"]

        if self.SCORE_GRADE_B_MIN <= score <= self.SCORE_GRADE_B_MAX:
            position_multiplier += PERFORMANCE_CRITERIA["position_sizing"]["grade_b_bonus"]
            self.metrics["grade_b_approved"] += 1

        if htf_aligned:
            position_multiplier += PERFORMANCE_CRITERIA["position_sizing"]["htf_aligned_bonus"]
        else:
            position_multiplier += PERFORMANCE_CRITERIA["position_sizing"]["htf_misaligned_penalty"]

        if tdi_zone in ['SOFT_BUY', 'SOFT_SELL']:
            position_multiplier += PERFORMANCE_CRITERIA["position_sizing"]["soft_zone_bonus"]

        # NEW v3.3.0: Feature bonus to position sizing
        position_multiplier += feature_bonus_total

        position_multiplier = max(
            PERFORMANCE_CRITERIA["position_sizing"]["min_multiplier"],
            min(PERFORMANCE_CRITERIA["position_sizing"]["max_multiplier"], position_multiplier)
        )

        return 'PASS', position_multiplier, f"Passed ({remaining_slots} slots left, features: +{feature_bonus_total:.2f})", priority_score

    def _is_symbol_on_cooldown(self, symbol: str) -> Tuple[bool, Optional[int]]:
        if symbol not in self._cooldown_symbols: return False, None
        cooldown_until = self._cooldown_symbols[symbol]
        if datetime.now() < cooldown_until:
            remaining = int((cooldown_until - datetime.now()).total_seconds() / 60)
            return True, remaining
        del self._cooldown_symbols[symbol]
        return False, None

    def _update_symbol_cooldown(self, symbol: str):
        self._cooldown_symbols[symbol] = datetime.now() + timedelta(minutes=self._symbol_cooldown_minutes)

    async def _check_rate_limit(self, symbol: str = None) -> Tuple[bool, str]:
        async with self._lock:
            now = time.time()
            if self._rate_limited_until and datetime.now() < self._rate_limited_until:
                self.metrics["rate_limit_hits"] += 1
                return False, "Rate limited"
            if symbol:
                on_cooldown, remaining = self._is_symbol_on_cooldown(symbol)
                if on_cooldown:
                    self.metrics["cooldown_skips"] += 1
                    return False, f"Cooldown: {remaining}min"
            while self.request_timestamps and now - self.request_timestamps[0] > 60:
                self.request_timestamps.popleft()
            if len(self.request_timestamps) >= self.max_requests_per_minute:
                self.metrics["rate_limit_hits"] += 1
                return False, "Rate limit"
            if now - self._last_request_time < self.min_request_interval:
                return False, "Min interval"
            now_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if now_date > self.token_reset_time:
                self.daily_tokens_used = 0; self.token_reset_time = now_date
            if self.daily_tokens_used >= self.max_daily_tokens:
                self.metrics["rate_limit_hits"] += 1
                return False, "Token limit"
            return True, "OK"

    async def _call_groq(self, prompt: str, symbol: str = None) -> Optional[str]:
        if not self.enabled or not self.client: return None
        can_proceed, reason = await self._check_rate_limit(symbol)
        if not can_proceed: return None
        start_time = time.time()
        self.metrics["total_requests"] += 1
        self._last_request_time = start_time
        try:
            response = self.client.chat.completions.create(
                model=config.groq.model,
                messages=[
                    {"role": "system", "content": """Trading strategist v3.3.0. Rules:
- HARD signals (TDI ≤25/≥75) = 0% win → REJECT
- Grade A (85+ score) = 25% win → REJECT
- Grade B (75-84) = 78% win → PREFER
- SOFT signals = 85% win
- HTF aligned = 67% win; NOT aligned = 50% → reduce size 30%
- Score 70-74 (Grade C): only if HTF aligned + LTF ≥85%
- Max 5 signals/day, 2 per 4h window

NEW v3.3.0 Features (add to analysis):
- Divergence: Bullish/Bearish divergence adds +15% confidence
- Candle Patterns: Doji, Engulfing, Hammer, Star add +10% confidence
- S/R: Near support/resistance adds +10% confidence
- Session: NY session = +10%, Asian session = -10%
- BB Squeeze: Low volatility breakout adds +5% confidence

Return JSON: decision, confidence, risk_level, reasoning(30 words), signal_quality, market_alignment, probability_success, suggested_rrr, feature_analysis"""},
                    {"role": "user", "content": prompt}
                ],
                temperature=float(config.groq.temperature), max_tokens=600
            )
            result = response.choices[0].message.content
            elapsed = time.time() - start_time
            self.metrics["successful_requests"] += 1
            self.metrics["avg_response_time"] = (
                (self.metrics["avg_response_time"] * (self.metrics["successful_requests"] - 1) + elapsed) /
                self.metrics["successful_requests"]
            )
            self.daily_tokens_used += int(len(prompt.split()) * 1.3 + 600)
            return result
        except Exception as e:
            self.metrics["failed_requests"] += 1
            if "429" in str(e):
                self._rate_limited_until = datetime.now() + timedelta(minutes=5)
            return None

    def _generate_cache_key(self, data: Dict[str, Any]) -> str:
        key_parts = []
        for field in ['symbol', 'signal_type', 'tdi_level', 'tdi_zone', 'entry_price',
                      'ltf_confirmed', 'total_score', 'signal_strength', 'htf_aligned',
                      'divergence_detected', 'candle_pattern', 'sr_confirmed', 'session']:
            if field in data: key_parts.append(f"{field}:{data[field]}")
        key_parts.append("v3.3.0")
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()

    def _get_score_grade(self, score: int) -> str:
        if score >= self.SCORE_GRADE_A_PLUS: return "A"
        elif score >= self.SCORE_GRADE_B_MIN: return "B"
        elif score >= self.SCORE_GRADE_C_MIN: return "C"
        elif score >= 50: return "D"
        else: return "F"

    def _determine_signal_strength(self, tdi_level: float, tdi_zone: str) -> Tuple[str, float]:
        if tdi_level <= self.OVERSOLD or tdi_level >= self.OVERBOUGHT: return "HARD", 2.0
        return "SOFT", 1.0

    def _build_analysis_prompt(self, signal_data: Dict[str, Any]) -> str:
        symbol = signal_data.get('symbol', 'UNKNOWN')
        signal_type = signal_data.get('signal_type', 'UNKNOWN')
        entry = signal_data.get('entry_price', 0)
        tdi = signal_data.get('tdi_level', 50)
        tdi_zone = signal_data.get('tdi_zone', 'NEUTRAL')
        confidence = signal_data.get('confidence', 0.5)
        signal_strength = signal_data.get('signal_strength', 'SOFT')
        htf_aligned = signal_data.get('htf_aligned', False)
        ltf_confirmed = signal_data.get('ltf_confirmed', False)
        ltf_confidence = signal_data.get('ltf_confidence', 0)
        total_score = signal_data.get('total_score', 0)
        grade = self._get_score_grade(total_score)
        remaining = self.signal_limiter.get_remaining_slots()

        # NEW v3.3.0: Feature information
        divergence_detected = signal_data.get('divergence_detected', False)
        divergence_type = signal_data.get('divergence_type', '')
        candle_pattern = signal_data.get('candle_pattern', 'NONE')
        sr_confirmed = signal_data.get('sr_confirmed', False)
        nearest_support = signal_data.get('nearest_support', 0)
        nearest_resistance = signal_data.get('nearest_resistance', 0)
        bb_squeeze = signal_data.get('bb_squeeze', False)
        session = signal_data.get('session', 'UNKNOWN')

        grade_emoji = "🏆" if grade == "A" else "🥈" if grade == "B" else "🥉" if grade == "C" else "📊"

        zone_desc = {
            "SOFT_BUY": "SOFT BUY (75% win)", "SOFT_SELL": "SOFT SELL (100% win)",
            "BUY_ZONE": "BUY ZONE (57% win)", "NO_TRADE": "NO TRADE (67% win)",
            "OVERSOLD": "OVERSOLD-HARD (20% win)", "OVERBOUGHT": "OVERBOUGHT-HARD (20% win)",
        }.get(tdi_zone, tdi_zone)

        # Feature string
        features = []
        if divergence_detected:
            features.append(f"DIVERGENCE:{divergence_type.upper()}")
        if candle_pattern != 'NONE':
            features.append(f"PATTERN:{candle_pattern}")
        if sr_confirmed:
            features.append(f"S/R:${nearest_support:.2f}/R${nearest_resistance:.2f}")
        if bb_squeeze:
            features.append("BB_SQUEEZE")
        features.append(f"SESSION:{session}")
        feature_str = " | ".join(features) if features else "None"

        return f"""{grade_emoji} {symbol} {signal_type} | Score:{total_score}/100 (Grade {grade})
TDI:{tdi:.1f} ({zone_desc}) | HTF aligned:{'Y' if htf_aligned else 'N'}
Strength:{signal_strength} | LTF:{'Y' if ltf_confirmed else 'N'} ({ltf_confidence:.0%})
Entry:${entry:.4f} | Conf:{confidence:.0%} | Slots left:{remaining}/{SIGNAL_REDUCTION_RULES['max_signals_per_day']}
Features: {feature_str}
Return JSON decision (APPROVE/REJECT/WAIT) with feature analysis."""

    def _parse_ai_response(self, response: str, signal_data: Dict[str, Any],
                          position_multiplier: float = 1.0,
                          performance_win_rate: float = 0.0,
                          priority_score: int = 0,
                          feature_bonus_total: float = 0.0) -> Optional[AIAnalysisResult]:
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match: return None
            data = json.loads(json_match.group())
            decision = data.get('decision', 'WAIT')
            if decision not in ['APPROVE', 'REJECT', 'WAIT']: decision = 'WAIT'
            reasoning = data.get('reasoning', '')[:150]
            suggested_rrr = data.get('suggested_rrr')
            if suggested_rrr:
                suggested_rrr = max(self.MIN_RRR, min(self.MAX_RRR, float(suggested_rrr)))
                suggested_rrr = round(suggested_rrr, 1)
            else: suggested_rrr = signal_data.get('rrr', self.DEFAULT_RRR)

            tdi_level = signal_data.get('tdi_level', 50)
            tdi_zone = signal_data.get('tdi_zone', 'NEUTRAL')
            signal_strength, risk_multiplier = self._determine_signal_strength(tdi_level, tdi_zone)
            total_score = signal_data.get('total_score', 0)
            component_scores = signal_data.get('component_scores', {})

            # NEW v3.3.0: Extract feature analysis from response
            feature_analysis = data.get('feature_analysis', '')

            if signal_strength == "HARD": self.metrics["hard_signals"] += 1
            else: self.metrics["soft_signals"] += 1
            if signal_data.get('ltf_confirmed'): self.metrics["ltf_analyzed"] += 1
            if total_score > 0:
                self.metrics["score_analyzed"] += 1
                if total_score >= self.HIGH_SCORE: self.metrics["high_score_signals"] += 1
                elif total_score >= self.MEDIUM_SCORE: self.metrics["medium_score_signals"] += 1
                else: self.metrics["low_score_signals"] += 1

            if decision == 'APPROVE':
                self.metrics["signals_approved"] += 1
                self.metrics["decision_breakdown"]["approved"] += 1
                grade = self._get_score_grade(total_score)
                if grade == 'B': self.metrics["grade_b_performance_tracked"] += 1
            elif decision == 'REJECT':
                self.metrics["signals_rejected"] += 1
                self.metrics["decision_breakdown"]["rejected"] += 1
            else:
                self.metrics["signals_waited"] += 1
                self.metrics["decision_breakdown"]["waited"] += 1

            volatility = 0.03
            profile = "AGGRESSIVE" if signal_strength == "HARD" else "MODERATE"
            risk_per_trade = getattr(config.risk, 'risk_per_trade_percent', 0.5) / 100
            leverage = LeverageCalculator.calculate_optimal_leverage(
                symbol=signal_data.get('symbol', 'BTCUSDT'),
                volatility=volatility, risk_per_trade=risk_per_trade,
                max_drawdown=0.10, profile=profile,
                signal_quality=float(data.get('signal_quality', 0.5)),
                signal_strength=signal_strength, total_score=total_score,
                position_multiplier=position_multiplier,
                feature_bonus_total=feature_bonus_total
            )

            return AIAnalysisResult(
                symbol=signal_data.get('symbol', 'UNKNOWN'), decision=decision,
                confidence=min(1.0, max(0.0, float(data.get('confidence', 0.5)))),
                risk_level=data.get('risk_level', 'MEDIUM'), reasoning=reasoning,
                market_analysis=data.get('market_analysis', ''),
                technical_factors=data.get('technical_factors', []),
                risk_factors=data.get('risk_factors', []),
                recommendation=data.get('recommendation', ''),
                signal_quality=float(data.get('signal_quality', 0.5)),
                market_alignment=float(data.get('market_alignment', 0.5)),
                probability_success=float(data.get('probability_success', 0.5)),
                expected_profitability=float(data.get('expected_profitability', 0.5)),
                suggested_rrr=suggested_rrr, leverage_recommendation=leverage,
                raw_response=response, ai_validated=True,
                has_conflict=False, conflict_reason="",
                tokens_used=len(response.split()) + len(response) // 4,
                signal_strength=signal_strength, risk_multiplier=risk_multiplier,
                total_score=total_score, component_scores=component_scores,
                score_grade=self._get_score_grade(total_score),
                bb_position=signal_data.get('bb_position', 0.5),
                volume_ratio=signal_data.get('volume_ratio', 1.0),
                position_multiplier=position_multiplier,
                performance_win_rate=performance_win_rate,
                auto_rejected=False, rejection_category="",
                priority_score=priority_score,
                signal_limit_rejected=False, cluster_rejected=False,
                # NEW v3.3.0
                divergence_detected=signal_data.get('divergence_detected', False),
                divergence_strength=signal_data.get('divergence_strength', 0.0),
                divergence_type=signal_data.get('divergence_type', ''),
                candle_pattern=signal_data.get('candle_pattern', 'NONE'),
                candle_pattern_confidence=signal_data.get('candle_pattern_confidence', 0.0),
                candle_pattern_direction=signal_data.get('candle_pattern_direction', 'NONE'),
                sr_confirmed=signal_data.get('sr_confirmed', False),
                sr_position=signal_data.get('sr_position', 'UNKNOWN'),
                nearest_support=signal_data.get('nearest_support', 0),
                nearest_resistance=signal_data.get('nearest_resistance', 0),
                bb_squeeze=signal_data.get('bb_squeeze', False),
                bb_squeeze_strength=signal_data.get('bb_squeeze_strength', 0.0),
                session=signal_data.get('session', 'UNKNOWN'),
                session_multiplier=signal_data.get('session_multiplier', 1.0),
                feature_bonus_total=feature_bonus_total,
            )
        except Exception as e:
            ai_logger.error(f"{EMOJI['ERROR']} AI_PARSE: {e}")
            return None

    async def analyze_signal(self, signal_data: Dict[str, Any]) -> Optional[AIAnalysisResult]:
        """Analyze signal with v3.3.0 features."""
        symbol = signal_data.get('symbol', 'UNKNOWN')
        total_score = signal_data.get('total_score', 0)
        signal_strength = signal_data.get('signal_strength', 'SOFT')
        grade = self._get_score_grade(total_score)

        log_ai_operation("ANALYZE", "START",
                        {"symbol": symbol, "score": total_score, "grade": grade,
                         "strength": signal_strength,
                         "slots_left": self.signal_limiter.get_remaining_slots(),
                         "divergence": signal_data.get('divergence_detected', False),
                         "pattern": signal_data.get('candle_pattern', 'NONE'),
                         "session": signal_data.get('session', 'UNKNOWN')},
                        emoji=EMOJI['ANALYZE'])

        if not self.enabled:
            return None

        try:
            # Apply all performance + reduction filters
            pre_decision, position_multiplier, pre_reason, priority_score = self._apply_performance_filters(signal_data)

            # Calculate feature bonus total
            feature_bonus_total = 0.0
            if signal_data.get('divergence_detected', False):
                feature_bonus_total += 0.15
            if signal_data.get('candle_pattern', 'NONE') != 'NONE':
                feature_bonus_total += 0.10
            if signal_data.get('sr_confirmed', False):
                feature_bonus_total += 0.10
            if signal_data.get('bb_squeeze', False):
                feature_bonus_total += 0.05
            if signal_data.get('session', 'UNKNOWN') != 'NY':
                feature_bonus_total -= 0.10

            if pre_decision == 'REJECT':
                ai_logger.info(f"{EMOJI['FILTER']} REJECT {symbol}: {pre_reason}")
                self.metrics["signals_rejected"] += 1
                self.metrics["decision_breakdown"]["rejected"] += 1
                return AIAnalysisResult(
                    symbol=symbol, decision='REJECT', confidence=0.95,
                    risk_level='HIGH', reasoning=pre_reason[:150],
                    signal_quality=0.0, market_alignment=0.0, probability_success=0.0,
                    suggested_rrr=self.DEFAULT_RRR, ai_validated=True,
                    signal_strength=signal_strength,
                    risk_multiplier=2.0 if signal_strength == 'HARD' else 1.0,
                    total_score=total_score,
                    component_scores=signal_data.get('component_scores', {}),
                    score_grade=grade,
                    position_multiplier=position_multiplier,
                    auto_rejected=True, rejection_category=pre_reason[:50],
                    priority_score=priority_score,
                    feature_bonus_total=feature_bonus_total,
                )

            if pre_decision == 'WAIT':
                ai_logger.info(f"{EMOJI['LIMIT']} WAIT {symbol}: {pre_reason}")
                self.metrics["signals_waited"] += 1
                self.metrics["decision_breakdown"]["waited"] += 1
                return AIAnalysisResult(
                    symbol=symbol, decision='WAIT', confidence=0.5,
                    risk_level='MEDIUM', reasoning=pre_reason[:150],
                    signal_quality=0.5, market_alignment=0.5, probability_success=0.3,
                    suggested_rrr=self.DEFAULT_RRR, ai_validated=True,
                    signal_strength=signal_strength,
                    risk_multiplier=1.0, total_score=total_score,
                    component_scores=signal_data.get('component_scores', {}),
                    score_grade=grade,
                    position_multiplier=position_multiplier,
                    signal_limit_rejected=True,
                    priority_score=priority_score,
                    feature_bonus_total=feature_bonus_total,
                )

            # Check cache
            cache_key = self._generate_cache_key(signal_data)
            cached = self.cache.get(cache_key)
            if cached:
                ai_logger.debug(f"{EMOJI['CACHE']} Cache hit: {symbol}")
                self.metrics["cache_hits"] += 1
                result = AIAnalysisResult(**cached)
                result.ai_validated = True
                result.position_multiplier = position_multiplier
                result.feature_bonus_total = feature_bonus_total
                return result

            # Call AI
            prompt = self._build_analysis_prompt(signal_data)
            response = await self._call_groq(prompt, symbol)

            if not response:
                ai_logger.warning(f"{EMOJI['WARNING']} No response: {symbol}")
                self.metrics["signals_rejected"] += 1
                self.metrics["decision_breakdown"]["rejected"] += 1
                return None

            performance_win_rate = 0.0
            if 75 <= total_score <= 84: performance_win_rate = 0.78
            elif total_score >= 70: performance_win_rate = 0.43

            result = self._parse_ai_response(
                response, signal_data,
                position_multiplier=position_multiplier,
                performance_win_rate=performance_win_rate,
                priority_score=priority_score,
                feature_bonus_total=feature_bonus_total
            )

            if result:
                self.cache.set(cache_key, result.to_dict())
                if result.decision == 'APPROVE':
                    self._update_symbol_cooldown(symbol)
                    self.signal_limiter.record_signal(symbol)

                log_ai_operation("ANALYZE", "SUCCESS",
                                {"symbol": symbol, "decision": result.decision,
                                 "grade": result.score_grade,
                                 "priority": priority_score,
                                 "slots_left": self.signal_limiter.get_remaining_slots(),
                                 "features": f"DIV:{result.divergence_detected}/PAT:{result.candle_pattern}/SR:{result.sr_confirmed}"},
                                emoji=EMOJI['SUCCESS'])

            return result

        except Exception as e:
            log_ai_operation("ANALYZE", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            ai_logger.error(f"{EMOJI['ERROR']} AI_ANALYZE: {e}", exc_info=True)
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get stats with v3.3.0 metrics."""
        return {
            **self.metrics,
            "enabled": self.enabled, "version": "3.3.0",
            "cache_stats": self.cache.get_stats(),
            "signal_limiter": self.signal_limiter.get_stats(),
            "daily_tokens_used": self.daily_tokens_used,
            "tokens_remaining": max(0, self.max_daily_tokens - self.daily_tokens_used),
            "success_rate": (
                self.metrics["successful_requests"] / self.metrics["total_requests"]
                if self.metrics["total_requests"] > 0 else 0
            ),
            "signal_reduction": {
                "max_per_day": SIGNAL_REDUCTION_RULES["max_signals_per_day"],
                "min_between_signals": SIGNAL_REDUCTION_RULES["min_minutes_between_signals"],
                "min_score": self.MINIMUM_SIGNAL_SCORE,
                "grade_b_range": [self.SCORE_GRADE_B_MIN, self.SCORE_GRADE_B_MAX],
            },
            # NEW v3.3.0
            "feature_stats": {
                "divergence_signals": self.metrics["divergence_signals"],
                "pattern_signals": self.metrics["pattern_signals"],
                "sr_signals": self.metrics["sr_signals"],
                "squeeze_signals": self.metrics["squeeze_signals"],
                "session_adjusted": self.metrics["session_adjusted"],
            }
        }

    def clear_cache(self):
        self.cache.clear()
        ai_logger.info(f"{EMOJI['SUCCESS']} AI_CACHE: Cleared")


# Create singleton instance
ai_analyzer = AIAnalyzer(enabled=config.groq.enabled)

__all__ = [
    "ai_analyzer", "AIAnalyzer", "AIAnalysisResult", "LeverageCalculator", "SignalLimiter",
]
