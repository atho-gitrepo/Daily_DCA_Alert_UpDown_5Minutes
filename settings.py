"""
Configuration management for the AI Trading Bot.
Version: 3.4.2 - ALIGNED: Super TDI + MACD + Super Bollinger Bands Strategy
"""

import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import json

# Configure logging
logger = logging.getLogger(__name__)


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class RunMode(Enum):
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"
    BACKTEST = "BACKTEST"


# ------------------- Safe Conversion Functions -------------------

def safe_float_env(key: str, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    try:
        value = float(os.getenv(key, str(default)))
        if min_val is not None and value < min_val:
            raise ValueError(f"{key}={value} is below minimum {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"{key}={value} exceeds maximum {max_val}")
        return value
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse {key} as float, using default {default}")
        return default


def safe_int_env(key: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    try:
        value = int(os.getenv(key, str(default)))
        if min_val is not None and value < min_val:
            raise ValueError(f"{key}={value} is below minimum {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"{key}={value} exceeds maximum {max_val}")
        return value
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse {key} as integer, using default {default}")
        return default


def safe_bool_env(key: str, default: bool = False) -> bool:
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on", "t")


def safe_list_env(key: str, default: List[str], delimiter: str = ",") -> List[str]:
    value = os.getenv(key)
    if not value:
        return default
    try:
        items = [item.strip().upper() for item in value.split(delimiter) if item.strip()]
        return items if items else default
    except Exception:
        logger.warning(f"Failed to parse {key} as list, using default")
        return default


# ------------------- Configuration Classes -------------------

@dataclass
class BinanceConfig:
    """Binance API configuration."""
    api_key: str = ""
    api_secret: str = ""
    use_testnet: bool = True
    testnet: bool = True
    request_timeout: int = 30
    rate_limit: int = 1200


@dataclass
class MarketConfig:
    quote_asset: str = "USDT"
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    timeframe: str = "5m"  # Super TDI + MACD + Super BB uses 5m for entries
    htf_timeframe: str = "1h"  # Higher timeframe for context ONLY (not a filter)
    ltf_timeframe: str = "1m"  # Ultra LTF for precise entry
    ultra_ltf_timeframe: str = "1m"
    ultra_htf_timeframe: str = "4h"
    polling_interval_seconds: int = 15  # 15 seconds for faster signal capture


@dataclass
class StrategyConfig:
    """
    Super TDI + MACD + Super Bollinger Bands Strategy Configuration.
    ALIGNED WITH YOUR MANUAL STRATEGY: RSI (TDI) primary + MACD secondary + BB entry
    """

    # ===== TDI Levels (Super TDI = Your RSI) =====
    tdi_oversold: float = 25.0      # Hard Buy Zone - 2x risk
    tdi_soft_buy: float = 35.0      # Soft Buy Zone - 1x risk
    tdi_center_line: float = 50.0   # No Trade Zone - Wait!
    tdi_soft_sell: float = 65.0     # Soft Sell Zone - 1x risk
    tdi_overbought: float = 75.0    # Hard Sell Zone - 2x risk
    tdi_no_trade_start: float = 50.0
    tdi_no_trade_end: float = 65.0
    tdi_rsi_period: int = 10
    tdi_fast_ma_period: int = 1
    tdi_slow_ma_period: int = 5

    # ===== MACD Settings (NEW - Your Secondary Indicator) =====
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    require_macd_confirmation: bool = True  # MACD confirmation required

    # ===== Bollinger Bands (Super BB) =====
    bb_period: int = 34
    bb_deviation: float = 1.750
    bb_trend_period: int = 9

    # ===== Strategy Conditions =====
    # Minimum conditions required (out of 5) for a signal
    min_conditions_for_signal: int = 3
    # Strong signal requires at least 4 conditions
    strong_signal_min_conditions: int = 4

    # ===== Signal Strength =====
    hard_signal_min_conditions: int = 4  # HARD signal needs 4+ conditions
    soft_signal_min_conditions: int = 3  # SOFT signal needs 3+ conditions
    weak_signal_min_conditions: int = 2  # WEAK signal needs 2+ conditions

    # ===== Risk Multipliers =====
    hard_signal_risk_multiplier: float = 2.0
    soft_signal_risk_multiplier: float = 1.0
    weak_signal_risk_multiplier: float = 0.5

    # ===== ATR Risk =====
    atr_period: int = 14
    sl_multiplier: float = 1.5
    tp_multiplier: float = 2.5  # Default RRR for Super BB strategy

    # ===== Entry Protection =====
    max_entry_distance_atr: float = 0.25

    # ===== Grade Thresholds (LOWERED for more signals) =====
    grade_a_plus_threshold: int = 90
    grade_a_threshold: int = 80      # Changed from 82
    grade_b_plus_threshold: int = 72 # Changed from 75
    grade_b_threshold: int = 60      # Changed from 70
    grade_c_threshold: int = 50      # Changed from 60

    # ===== Signal Lifecycle =====
    symbol_cooldown_minutes: int = 30
    break_even_threshold_minutes: int = 480  # 8 hours
    min_bars_before_check: int = 2

    # ===== Features =====
    enable_divergence: bool = True
    enable_candle_patterns: bool = True
    enable_support_resistance: bool = True
    enable_bb_squeeze: bool = True
    enable_session_filtering: bool = True
    enable_volume_gate: bool = True

    # ===== Multi-Timeframe Settings =====
    # HTF is for CONTEXT ONLY - NOT a filter for your strategy
    require_htf_alignment: bool = False  # DISABLED - matches your manual strategy
    htf_trend_threshold: int = 1
    htf_ma_periods: List[int] = field(default_factory=lambda: [7, 25, 99])
    require_ltf_confirmation: bool = True
    ltf_min_confirmation: float = 0.65

    # ===== Risk =====
    default_rrr: float = 2.0
    min_rrr: float = 1.5
    max_rrr: float = 4.0
    risk_per_trade_percent: float = 0.5
    max_daily_trades: int = 5

    # ===== AI =====
    ai_enabled: bool = True
    ai_min_interval_seconds: int = 120
    ai_cache_ttl: int = 600

    # ===== Fee =====
    fee_impact: float = 0.0011

    # ===== Signal Settings =====
    min_quality_score: int = 50      # Changed from 70
    min_signal_score: int = 60       # Changed from 70
    signal_cooldown_minutes: int = 30
    max_signals_per_cycle: int = 5

    # ===== Leverage =====
    default_leverage: int = 5
    min_leverage: int = 1
    max_leverage: int = 20
    use_futures: bool = True

    # ===== Session Multipliers =====
    session_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "ASIAN": 0.7,      # Lower confidence in Asian session
        "LONDON": 1.0,     # Normal
        "NY": 1.2,         # Higher confidence during NY session
        "LATE": 0.8,       # Lower confidence late session
    })

    # ===== PRODUCTION-SPECIFIC SETTINGS =====
    production_position_size_multiplier: float = 0.5
    production_max_daily_trades: int = 3
    production_min_setup_score: int = 70
    production_require_extra_confirmation: bool = True


@dataclass
class PerformanceConfig:
    """Performance configuration."""
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    cache_max_size: int = 1000
    rate_limit_enabled: bool = True
    binance_rate_limit: int = 1200
    max_retries: int = 3
    retry_delay_seconds: int = 5
    batch_size: int = 100


@dataclass
class GroqConfig:
    """Groq AI configuration."""
    api_key: str = ""
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.3
    enabled: bool = False


@dataclass
class TelegramConfig:
    """Telegram configuration."""
    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = False


@dataclass
class MongoDBConfig:
    """MongoDB configuration."""
    uri: str = ""
    db_name: str = "trading_bot"
    active_collection: str = "active_signals"
    resolved_collection: str = "resolved_signals"
    archive_collection: str = "archive_signals"
    enabled: bool = False
    host: str = "localhost"
    port: int = 27017
    user: str = ""
    password: str = ""
    auth_source: str = "admin"
    retry_writes: bool = True
    w: str = "majority"
    max_pool_size: int = 50
    min_pool_size: int = 5
    connect_timeout_ms: int = 5000
    socket_timeout_ms: int = 5000
    server_selection_timeout_ms: int = 5000


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/trading_bot.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class DeploymentConfig:
    environment: Environment = Environment.DEVELOPMENT
    run_mode: RunMode = RunMode.DEMO
    debug: bool = False
    port: int = 8080
    host: str = "0.0.0.0"

    # Production-specific
    use_sentry: bool = False
    sentry_dsn: str = ""
    log_level_production: str = "WARNING"


# ------------------- Main Config Class -------------------

class Config:
    """Complete configuration for Super TDI + MACD + Super BB strategy."""

    VERSION = "3.4.2"

    def __init__(self):
        self.binance = BinanceConfig()
        self.market = MarketConfig()
        self.strategy = StrategyConfig()
        self.performance = PerformanceConfig()
        self.groq = GroqConfig()
        self.telegram = TelegramConfig()
        self.mongodb = MongoDBConfig()
        self.logging = LoggingConfig()
        self.deployment = DeploymentConfig()

        self._load_from_env()
        self._validate()
        self._setup_directories()

        # Log configuration mode
        run_mode = self.deployment.run_mode.value
        env = self.deployment.environment.value

        logger.info(f"Config initialized v{self.VERSION}")
        logger.info(f"  - Environment: {env}")
        logger.info(f"  - Run Mode: {run_mode}")
        logger.info(f"  - Strategy: Super TDI + MACD + Super Bollinger Bands")

        if run_mode == "PRODUCTION":
            logger.info(f"🔴 PRODUCTION MODE ACTIVE - Using REAL funds!")
            logger.info(f"  - Position Size: {self.get_position_size_multiplier()*100:.0f}%")
            logger.info(f"  - Max Daily Trades: {self.strategy.max_daily_trades}")
            logger.info(f"  - Min Conditions Required: {self.strategy.min_conditions_for_signal}")
            logger.info(f"  - HTF Alignment Required: {self.strategy.require_htf_alignment} (DISABLED - Context only)")

        logger.info(f"✅ Super TDI + MACD + Super BB Features:")
        logger.info(f"  - TDI Levels: {self.strategy.tdi_oversold}/{self.strategy.tdi_soft_buy}/{self.strategy.tdi_center_line}/{self.strategy.tdi_soft_sell}/{self.strategy.tdi_overbought}")
        logger.info(f"  - MACD: Fast={self.strategy.macd_fast}, Slow={self.strategy.macd_slow}, Signal={self.strategy.macd_signal}")
        logger.info(f"  - MACD Required: {'✅' if self.strategy.require_macd_confirmation else '❌'}")
        logger.info(f"  - BB Period: {self.strategy.bb_period}, Deviation: {self.strategy.bb_deviation}")
        logger.info(f"  - Min Conditions: {self.strategy.min_conditions_for_signal}")
        logger.info(f"  - Hard Signal: {self.strategy.hard_signal_min_conditions}+ conditions (2x risk)")
        logger.info(f"  - Soft Signal: {self.strategy.soft_signal_min_conditions}+ conditions (1x risk)")
        logger.info(f"  - Grade B Threshold: {self.strategy.grade_b_threshold}+")
        logger.info(f"  - Grade C Threshold: {self.strategy.grade_c_threshold}+")
        logger.info(f"  - Min Quality Score: {self.strategy.min_quality_score}")
        logger.info(f"  - Divergence: {self.strategy.enable_divergence}")
        logger.info(f"  - Candle Patterns: {self.strategy.enable_candle_patterns}")
        logger.info(f"  - S/R Levels: {self.strategy.enable_support_resistance}")
        logger.info(f"  - BB Squeeze: {self.strategy.enable_bb_squeeze}")
        logger.info(f"  - Session Filtering: {self.strategy.enable_session_filtering}")
        logger.info(f"  - HTF Trend Filter: ❌ DISABLED (Manual strategy - context only)")

    def _load_from_env(self):
        # ====== BINANCE ======
        use_testnet = safe_bool_env("BINANCE_USE_TESTNET", True)
        self.binance = BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            use_testnet=use_testnet,
            testnet=use_testnet,
            request_timeout=safe_int_env("BINANCE_REQUEST_TIMEOUT", 30, min_val=5, max_val=60),
            rate_limit=safe_int_env("BINANCE_RATE_LIMIT", 1200, min_val=100, max_val=5000),
        )

        # ====== MARKET ======
        default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "AVAXUSDT", "DOTUSDT", "ADAUSDT", "MATICUSDT"]
        self.market = MarketConfig(
            quote_asset=os.getenv("QUOTE_ASSET", "USDT"),
            symbols=safe_list_env("SYMBOLS", default_symbols),
            timeframe=os.getenv("TIMEFRAME", "5m"),
            htf_timeframe=os.getenv("HTF_TIMEFRAME", "1h"),
            ltf_timeframe=os.getenv("LTF_TIMEFRAME", "1m"),
            ultra_ltf_timeframe=os.getenv("ULTRA_LTF_TIMEFRAME", "1m"),
            ultra_htf_timeframe=os.getenv("ULTRA_HTF_TIMEFRAME", "4h"),
            polling_interval_seconds=safe_int_env("POLLING_INTERVAL_SECONDS", 15, min_val=5, max_val=60),
        )

        # ====== STRATEGY ======
        run_mode = os.getenv("RUN_MODE", "DEMO").upper().strip()
        is_production = run_mode == "PRODUCTION"

        self.strategy = StrategyConfig(
            # TDI Levels
            tdi_oversold=safe_float_env("TDI_OVERSOLD", 25.0, min_val=15, max_val=35),
            tdi_soft_buy=safe_float_env("TDI_SOFT_BUY", 35.0, min_val=25, max_val=45),
            tdi_center_line=safe_float_env("TDI_CENTER_LINE", 50.0, min_val=45, max_val=55),
            tdi_soft_sell=safe_float_env("TDI_SOFT_SELL", 65.0, min_val=55, max_val=75),
            tdi_overbought=safe_float_env("TDI_OVERBOUGHT", 75.0, min_val=65, max_val=85),
            tdi_no_trade_start=safe_float_env("TDI_NO_TRADE_START", 50.0, min_val=45, max_val=55),
            tdi_no_trade_end=safe_float_env("TDI_NO_TRADE_END", 65.0, min_val=55, max_val=75),
            tdi_rsi_period=safe_int_env("TDI_RSI_PERIOD", 10, min_val=5, max_val=20),
            tdi_fast_ma_period=safe_int_env("TDI_FAST_MA_PERIOD", 1, min_val=1, max_val=5),
            tdi_slow_ma_period=safe_int_env("TDI_SLOW_MA_PERIOD", 5, min_val=3, max_val=10),

            # MACD Settings (NEW)
            macd_fast=safe_int_env("MACD_FAST", 12, min_val=5, max_val=20),
            macd_slow=safe_int_env("MACD_SLOW", 26, min_val=15, max_val=40),
            macd_signal=safe_int_env("MACD_SIGNAL", 9, min_val=5, max_val=15),
            require_macd_confirmation=safe_bool_env("REQUIRE_MACD_CONFIRMATION", True),

            # Bollinger Bands
            bb_period=safe_int_env("BB_PERIOD", 34, min_val=10, max_val=50),
            bb_deviation=safe_float_env("BB_DEVIATION", 1.750, min_val=1.0, max_val=3.0),
            bb_trend_period=safe_int_env("BB_TREND_PERIOD", 9, min_val=3, max_val=20),

            # Strategy Conditions
            min_conditions_for_signal=safe_int_env("MIN_CONDITIONS_FOR_SIGNAL", 3, min_val=2, max_val=5),
            strong_signal_min_conditions=safe_int_env("STRONG_SIGNAL_MIN_CONDITIONS", 4, min_val=3, max_val=5),

            # Signal Strength
            hard_signal_min_conditions=safe_int_env("HARD_SIGNAL_MIN_CONDITIONS", 4, min_val=3, max_val=5),
            soft_signal_min_conditions=safe_int_env("SOFT_SIGNAL_MIN_CONDITIONS", 3, min_val=2, max_val=4),
            weak_signal_min_conditions=safe_int_env("WEAK_SIGNAL_MIN_CONDITIONS", 2, min_val=1, max_val=3),

            # Risk Multipliers
            hard_signal_risk_multiplier=safe_float_env("HARD_SIGNAL_RISK_MULTIPLIER", 2.0, min_val=1.0, max_val=3.0),
            soft_signal_risk_multiplier=safe_float_env("SOFT_SIGNAL_RISK_MULTIPLIER", 1.0, min_val=0.5, max_val=2.0),
            weak_signal_risk_multiplier=safe_float_env("WEAK_SIGNAL_RISK_MULTIPLIER", 0.5, min_val=0.1, max_val=1.0),

            # ATR Risk
            atr_period=safe_int_env("ATR_PERIOD", 14, min_val=5, max_val=30),
            sl_multiplier=safe_float_env("SL_MULTIPLIER", 1.5, min_val=0.5, max_val=3.0),
            tp_multiplier=safe_float_env("TP_MULTIPLIER", 2.5, min_val=1.0, max_val=5.0),

            # Entry Protection
            max_entry_distance_atr=safe_float_env("MAX_ENTRY_DISTANCE_ATR", 0.25, min_val=0.05, max_val=0.75),

            # Grade Thresholds (LOWERED)
            grade_a_plus_threshold=safe_int_env("GRADE_A_PLUS_THRESHOLD", 90, min_val=80, max_val=98),
            grade_a_threshold=safe_int_env("GRADE_A_THRESHOLD", 80, min_val=70, max_val=95),
            grade_b_plus_threshold=safe_int_env("GRADE_B_PLUS_THRESHOLD", 72, min_val=65, max_val=85),
            grade_b_threshold=safe_int_env("GRADE_B_THRESHOLD", 60, min_val=50, max_val=75),
            grade_c_threshold=safe_int_env("GRADE_C_THRESHOLD", 50, min_val=40, max_val=70),

            # Signal Lifecycle
            symbol_cooldown_minutes=safe_int_env("SYMBOL_COOLDOWN_MINUTES", 30, min_val=5, max_val=120),
            break_even_threshold_minutes=safe_int_env("BREAK_EVEN_THRESHOLD_MINUTES", 480, min_val=30, max_val=720),
            min_bars_before_check=safe_int_env("MIN_BARS_BEFORE_CHECK", 2, min_val=1, max_val=5),

            # Features
            enable_divergence=safe_bool_env("ENABLE_DIVERGENCE", True),
            enable_candle_patterns=safe_bool_env("ENABLE_CANDLE_PATTERNS", True),
            enable_support_resistance=safe_bool_env("ENABLE_SR", True),
            enable_bb_squeeze=safe_bool_env("ENABLE_BB_SQUEEZE", True),
            enable_session_filtering=safe_bool_env("ENABLE_SESSION_FILTERING", True),
            enable_volume_gate=safe_bool_env("ENABLE_VOLUME_GATE", True),

            # Multi-Timeframe (HTF = Context ONLY, NOT a filter)
            require_htf_alignment=safe_bool_env("REQUIRE_HTF_ALIGNMENT", False),  # DISABLED
            htf_trend_threshold=safe_int_env("HTF_TREND_THRESHOLD", 1, min_val=1, max_val=3),
            require_ltf_confirmation=safe_bool_env("REQUIRE_LTF_CONFIRMATION", True),
            ltf_min_confirmation=safe_float_env("LTF_MIN_CONFIRMATION", 0.65, min_val=0.4, max_val=0.9),

            # Risk
            default_rrr=safe_float_env("DEFAULT_RRR", 2.0, min_val=1.0, max_val=5.0),
            min_rrr=safe_float_env("MIN_RRR", 1.5, min_val=1.0, max_val=3.0),
            max_rrr=safe_float_env("MAX_RRR", 4.0, min_val=2.0, max_val=6.0),
            risk_per_trade_percent=safe_float_env("RISK_PER_TRADE_PERCENT", 0.5, min_val=0.01, max_val=5.0),
            max_daily_trades=safe_int_env("MAX_DAILY_TRADES", 3 if is_production else 5, min_val=1, max_val=30),

            # AI
            ai_enabled=safe_bool_env("AI_ENABLED", True),
            ai_min_interval_seconds=safe_int_env("AI_MIN_INTERVAL_SECONDS", 120, min_val=30, max_val=600),
            ai_cache_ttl=safe_int_env("AI_CACHE_TTL", 600, min_val=60, max_val=3600),

            # Fee
            fee_impact=safe_float_env("FEE_IMPACT", 0.0011, min_val=0.0005, max_val=0.005),

            # Signal Settings
            min_quality_score=safe_int_env("MIN_QUALITY_SCORE", 50, min_val=30, max_val=80),
            min_signal_score=safe_int_env("MIN_SIGNAL_SCORE", 60, min_val=40, max_val=85),
            signal_cooldown_minutes=safe_int_env("SIGNAL_COOLDOWN_MINUTES", 30, min_val=1, max_val=60),
            max_signals_per_cycle=safe_int_env("MAX_SIGNALS_PER_CYCLE", 3, min_val=1, max_val=10),

            # Leverage
            default_leverage=safe_int_env("DEFAULT_LEVERAGE", 5, min_val=1, max_val=50),
            min_leverage=safe_int_env("MIN_LEVERAGE", 1, min_val=1, max_val=10),
            max_leverage=safe_int_env("MAX_LEVERAGE", 20, min_val=1, max_val=100),
            use_futures=safe_bool_env("USE_FUTURES", True),

            # Session Multipliers
            session_multipliers={
                "ASIAN": safe_float_env("SESSION_ASIAN_MULTIPLIER", 0.7, min_val=0.3, max_val=1.0),
                "LONDON": safe_float_env("SESSION_LONDON_MULTIPLIER", 1.0, min_val=0.5, max_val=1.5),
                "NY": safe_float_env("SESSION_NY_MULTIPLIER", 1.2, min_val=0.5, max_val=1.5),
                "LATE": safe_float_env("SESSION_LATE_MULTIPLIER", 0.8, min_val=0.3, max_val=1.0),
            },

            # Production settings
            production_position_size_multiplier=safe_float_env("PRODUCTION_POSITION_SIZE_MULTIPLIER", 0.5, min_val=0.1, max_val=1.0),
            production_max_daily_trades=safe_int_env("PRODUCTION_MAX_DAILY_TRADES", 3, min_val=1, max_val=10),
            production_min_setup_score=safe_int_env("PRODUCTION_MIN_SETUP_SCORE", 70, min_val=60, max_val=90),
            production_require_extra_confirmation=safe_bool_env("PRODUCTION_EXTRA_CONFIRMATION", True),
        )

        # ====== PERFORMANCE ======
        self.performance = PerformanceConfig(
            cache_enabled=safe_bool_env("CACHE_ENABLED", True),
            cache_ttl_seconds=safe_int_env("CACHE_TTL_SECONDS", 300, min_val=30, max_val=3600),
            cache_max_size=safe_int_env("CACHE_MAX_SIZE", 1000, min_val=10, max_val=10000),
            rate_limit_enabled=safe_bool_env("RATE_LIMIT_ENABLED", True),
            binance_rate_limit=safe_int_env("BINANCE_RATE_LIMIT", 1200, min_val=100, max_val=5000),
            max_retries=safe_int_env("MAX_RETRIES", 3, min_val=1, max_val=10),
            retry_delay_seconds=safe_int_env("RETRY_DELAY_SECONDS", 5, min_val=1, max_val=30),
            batch_size=safe_int_env("BATCH_SIZE", 100, min_val=10, max_val=1000),
        )

        # ====== GROQ ======
        self.groq = GroqConfig(
            api_key=os.getenv("GROQ_API_KEY", ""),
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=safe_float_env("GROQ_TEMPERATURE", 0.3, min_val=0, max_val=1.0),
            enabled=bool(os.getenv("GROQ_API_KEY", "")),
        )

        # ====== TELEGRAM ======
        self.telegram = TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            enabled=bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        )

        # ====== MONGODB ======
        self.mongodb = self._load_mongodb_config()

        # ====== LOGGING ======
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if is_production:
            log_level = os.getenv("LOG_LEVEL_PRODUCTION", "WARNING").upper()

        self.logging = LoggingConfig(
            level=log_level,
            file=os.getenv("LOG_FILE", "logs/trading_bot.log"),
            format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )

        # ====== DEPLOYMENT ======
        env_str = os.getenv("ENVIRONMENT", "development").lower().strip()
        try:
            environment = Environment(env_str)
        except ValueError:
            environment = Environment.DEVELOPMENT

        try:
            run_mode = RunMode(run_mode)
        except ValueError:
            run_mode = RunMode.DEMO

        self.deployment = DeploymentConfig(
            environment=environment,
            run_mode=run_mode,
            debug=safe_bool_env("DEBUG", False),
            port=safe_int_env("PORT", 8080, min_val=1024, max_val=65535),
            host=os.getenv("HOST", "0.0.0.0"),
            use_sentry=safe_bool_env("USE_SENTRY", False),
            sentry_dsn=os.getenv("SENTRY_DSN", ""),
            log_level_production=os.getenv("LOG_LEVEL_PRODUCTION", "WARNING"),
        )

    def _load_mongodb_config(self) -> MongoDBConfig:
        """Load MongoDB configuration from environment variables."""
        mongodb_uri = os.getenv("MONGODB_URI", os.getenv("MONGODB_URL", ""))

        if not mongodb_uri:
            host = os.getenv("MONGODB_HOST", os.getenv("MONGO_HOST", "localhost"))
            port = safe_int_env("MONGODB_PORT", 27017, min_val=1, max_val=65535)
            user = os.getenv("MONGODB_USER", os.getenv("MONGO_USER", ""))
            password = os.getenv("MONGODB_PASSWORD", os.getenv("MONGO_PASS", ""))
            db_name = os.getenv("MONGODB_DB", os.getenv("MONGO_DB", "trading_bot"))

            if user and password:
                mongodb_uri = f"mongodb://{user}:{password}@{host}:{port}/{db_name}?authSource=admin"
            elif user:
                mongodb_uri = f"mongodb://{user}@{host}:{port}/{db_name}?authSource=admin"
            else:
                mongodb_uri = f"mongodb://{host}:{port}/{db_name}"

        enabled = bool(mongodb_uri)

        return MongoDBConfig(
            uri=mongodb_uri,
            db_name=os.getenv("MONGODB_DB", os.getenv("MONGO_DB", "trading_bot")),
            active_collection=os.getenv("MONGODB_ACTIVE_COLLECTION", "active_signals"),
            resolved_collection=os.getenv("MONGODB_RESOLVED_COLLECTION", "resolved_signals"),
            archive_collection=os.getenv("MONGODB_ARCHIVE_COLLECTION", "archive_signals"),
            enabled=enabled,
            host=os.getenv("MONGODB_HOST", os.getenv("MONGO_HOST", "localhost")),
            port=safe_int_env("MONGODB_PORT", 27017, min_val=1, max_val=65535),
            user=os.getenv("MONGODB_USER", os.getenv("MONGO_USER", "")),
            password=os.getenv("MONGODB_PASSWORD", os.getenv("MONGO_PASS", "")),
            auth_source=os.getenv("MONGODB_AUTH_SOURCE", "admin"),
            retry_writes=safe_bool_env("MONGODB_RETRY_WRITES", True),
            w=os.getenv("MONGODB_W", "majority"),
            max_pool_size=safe_int_env("MONGODB_MAX_POOL_SIZE", 50, min_val=1, max_val=100),
            min_pool_size=safe_int_env("MONGODB_MIN_POOL_SIZE", 5, min_val=0, max_val=50),
            connect_timeout_ms=safe_int_env("MONGODB_CONNECT_TIMEOUT_MS", 5000, min_val=1000, max_val=30000),
            socket_timeout_ms=safe_int_env("MONGODB_SOCKET_TIMEOUT_MS", 5000, min_val=1000, max_val=30000),
            server_selection_timeout_ms=safe_int_env("MONGODB_SERVER_SELECTION_TIMEOUT_MS", 5000, min_val=1000, max_val=30000),
        )

    def _validate(self):
        """Validate configuration."""
        errors = []
        warnings = []

        if self.deployment.environment == Environment.PRODUCTION:
            if not self.binance.api_key:
                errors.append("BINANCE_API_KEY is required in production environment")
            if not self.binance.api_secret:
                errors.append("BINANCE_API_SECRET is required in production environment")
            if not self.telegram.enabled:
                warnings.append("TELEGRAM_BOT_TOKEN not set - notifications will not work")

            if self.deployment.run_mode != RunMode.PRODUCTION:
                warnings.append("PRODUCTION environment but RUN_MODE is not PRODUCTION")

        # Validate grade thresholds
        if self.strategy.grade_b_threshold >= self.strategy.grade_a_threshold:
            warnings.append(f"GRADE_B_THRESHOLD ({self.strategy.grade_b_threshold}) should be below GRADE_A_THRESHOLD ({self.strategy.grade_a_threshold})")
        if self.strategy.grade_c_threshold >= self.strategy.grade_b_threshold:
            warnings.append(f"GRADE_C_THRESHOLD ({self.strategy.grade_c_threshold}) should be below GRADE_B_THRESHOLD ({self.strategy.grade_b_threshold})")

        # Validate MACD settings
        if self.strategy.macd_slow <= self.strategy.macd_fast:
            warnings.append(f"MACD_SLOW ({self.strategy.macd_slow}) should be greater than MACD_FAST ({self.strategy.macd_fast})")

        if self.strategy.min_rrr < 1.0:
            warnings.append(f"MIN_RRR ({self.strategy.min_rrr}) below 1.0")

        # Validate strategy conditions
        if self.strategy.min_conditions_for_signal < 2:
            warnings.append(f"MIN_CONDITIONS_FOR_SIGNAL ({self.strategy.min_conditions_for_signal}) is below 2 (recommended 3)")
        if self.strategy.min_conditions_for_signal > 4:
            warnings.append(f"MIN_CONDITIONS_FOR_SIGNAL ({self.strategy.min_conditions_for_signal}) is high (may miss signals)")

        # Production-specific validation
        if self.deployment.run_mode == RunMode.PRODUCTION:
            if self.strategy.risk_per_trade_percent > 2.0:
                warnings.append(f"RISK_PER_TRADE_PERCENT ({self.strategy.risk_per_trade_percent}%) is high for production (recommended <2%)")

        # HTF alignment warning - DISABLED for manual strategy
        if self.strategy.require_htf_alignment:
            warnings.append("HTF alignment is ENABLED but your manual strategy doesn't use it. Set REQUIRE_HTF_ALIGNMENT=false")

        for warning in warnings:
            logger.warning(f"Configuration warning: {warning}")

        if errors:
            error_msg = "Configuration errors:\n" + "\n".join(f"  - {err}" for err in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _setup_directories(self):
        directories = ["logs", "data", "backups"]
        for directory in directories:
            try:
                Path(directory).mkdir(exist_ok=True)
            except Exception as e:
                logger.warning(f"Failed to create directory {directory}: {e}")

    def is_production(self) -> bool:
        return self.deployment.environment == Environment.PRODUCTION

    def is_demo(self) -> bool:
        return self.deployment.run_mode == RunMode.DEMO

    def is_backtest(self) -> bool:
        return self.deployment.run_mode == RunMode.BACKTEST

    def is_production_mode(self) -> bool:
        return self.deployment.run_mode == RunMode.PRODUCTION

    def get_position_size_multiplier(self) -> float:
        """Get position size multiplier based on run mode."""
        if self.is_production_mode():
            return self.strategy.production_position_size_multiplier
        return 1.0

    def get_grade(self, score: int) -> str:
        """Get grade based on thresholds."""
        if score >= self.strategy.grade_a_plus_threshold:
            return "A+"
        elif score >= self.strategy.grade_a_threshold:
            return "A"
        elif score >= self.strategy.grade_b_plus_threshold:
            return "B+"
        elif score >= self.strategy.grade_b_threshold:
            return "B"
        elif score >= self.strategy.grade_c_threshold:
            return "C"
        else:
            return "D"

    def get_macd_settings(self) -> Dict[str, int]:
        """Get MACD settings."""
        return {
            'fast': self.strategy.macd_fast,
            'slow': self.strategy.macd_slow,
            'signal': self.strategy.macd_signal,
            'required': self.strategy.require_macd_confirmation,
        }


# ------------------- Singleton Instance -------------------

config = Config()

# Convenience exports
SYMBOLS = config.market.symbols
TIMEFRAME = config.market.timeframe
HTF_TIMEFRAME = config.market.htf_timeframe
LTF_TIMEFRAME = config.market.ltf_timeframe

__all__ = [
    "config",
    "Config",
    "Environment",
    "RunMode",
    "SYMBOLS",
    "TIMEFRAME",
    "HTF_TIMEFRAME",
    "LTF_TIMEFRAME",
]
