"""
Configuration management for the AI Trading Bot.
Version: 3.4.0 - ENHANCED: Added v3.4.0 signal engine config
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
    timeframe: str = "15m"
    htf_timeframe: str = "1h"
    ltf_timeframe: str = "5m"
    ultra_ltf_timeframe: str = "1m"
    ultra_htf_timeframe: str = "4h"
    polling_interval_seconds: int = 15


@dataclass
class StrategyConfig:
    """v3.4.0 Strategy Configuration."""

    # === Signal Engine v3.4.0 ===
    min_setup_score: int = 70
    min_trigger_score: int = 70
    counter_trend_min_score: int = 82
    max_signals_per_hour: int = 2

    # === Setup Expiry ===
    setup_expiry_seconds: int = 300  # 5 minutes
    trigger_expiry_seconds: int = 120  # 2 minutes

    # === Entry Protection ===
    max_entry_distance_atr: float = 0.25

    # === ATR Risk ===
    atr_period: int = 14
    sl_multiplier: float = 1.5
    tp_multiplier: float = 3.0

    # === TDI Levels ===
    tdi_oversold: float = 25.0
    tdi_soft_buy: float = 35.0
    tdi_soft_sell: float = 65.0
    tdi_overbought: float = 75.0

    # === Scoring Weights ===
    score_weights: Dict[str, float] = field(default_factory=lambda: {
        'htf_regime': 20,
        'location': 20,
        'momentum': 20,
        'trigger': 25,
        'volume': 15,
    })

    # === Grade Thresholds ===
    grade_a_plus_threshold: int = 90
    grade_a_threshold: int = 82
    grade_b_plus_threshold: int = 75
    grade_b_threshold: int = 70
    grade_c_threshold: int = 60

    # === Signal Lifecycle ===
    symbol_cooldown_minutes: int = 30
    break_even_threshold_minutes: int = 480  # 8 hours
    min_bars_before_check: int = 2

    # === Features ===
    enable_divergence: bool = True
    enable_candle_patterns: bool = True
    enable_support_resistance: bool = True
    enable_bb_squeeze: bool = True
    enable_session_filtering: bool = True
    enable_htf_regime: bool = True
    enable_structure_analysis: bool = True
    enable_volume_gate: bool = True
    enable_ltf_confirmation: bool = True

    # === Multi-Timeframe Settings ===
    require_ltf_confirmation: bool = True
    ltf_min_confirmation: float = 0.65
    require_htf_alignment: bool = True

    # === Risk ===
    default_rrr: float = 2.0
    min_rrr: float = 1.5
    max_rrr: float = 4.0
    risk_per_trade_percent: float = 0.5
    max_daily_trades: int = 5

    # === AI ===
    ai_enabled: bool = True
    ai_min_interval_seconds: int = 120
    ai_cache_ttl: int = 600

    # === Fee ===
    fee_impact: float = 0.0011

    # === Signal Settings ===
    min_quality_score: int = 50
    min_signal_score: int = 70
    signal_cooldown_minutes: int = 30
    max_signals_per_cycle: int = 3

    # === Leverage ===
    default_leverage: int = 5
    min_leverage: int = 1
    max_leverage: int = 20
    use_futures: bool = True

    # === Session Multipliers ===
    session_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "ASIAN": 0.7,
        "LONDON": 1.0,
        "NY": 1.2,
        "LATE": 0.8,
    })


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
    api_key: str = ""
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.3
    enabled: bool = False


@dataclass
class TelegramConfig:
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


# ------------------- Main Config Class -------------------

class Config:
    """Complete configuration with v3.4.0 support."""

    VERSION = "3.4.0"

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

        logger.info(f"Config initialized v{self.VERSION}")
        logger.info(f"✅ v3.4.0 Features enabled:")
        logger.info(f"  - Min Setup Score: {self.strategy.min_setup_score}")
        logger.info(f"  - Min Trigger Score: {self.strategy.min_trigger_score}")
        logger.info(f"  - Counter-Trend Min: {self.strategy.counter_trend_min_score}")
        logger.info(f"  - Max Entry Distance: {self.strategy.max_entry_distance_atr} ATR")
        logger.info(f"  - Grade A: {self.strategy.grade_a_threshold}+")
        logger.info(f"  - Grade A+: {self.strategy.grade_a_plus_threshold}+")

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
        default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
        self.market = MarketConfig(
            quote_asset=os.getenv("QUOTE_ASSET", "USDT"),
            symbols=safe_list_env("SYMBOLS", default_symbols),
            timeframe=os.getenv("TIMEFRAME", "15m"),
            htf_timeframe=os.getenv("HTF_TIMEFRAME", "1h"),
            ltf_timeframe=os.getenv("LTF_TIMEFRAME", "5m"),
            ultra_ltf_timeframe=os.getenv("ULTRA_LTF_TIMEFRAME", "1m"),
            ultra_htf_timeframe=os.getenv("ULTRA_HTF_TIMEFRAME", "4h"),
            polling_interval_seconds=safe_int_env("POLLING_INTERVAL_SECONDS", 15, min_val=1, max_val=60),
        )

        # ====== STRATEGY v3.4.0 ======
        self.strategy = StrategyConfig(
            min_setup_score=safe_int_env("MIN_SETUP_SCORE", 70, min_val=50, max_val=90),
            min_trigger_score=safe_int_env("MIN_TRIGGER_SCORE", 70, min_val=50, max_val=90),
            counter_trend_min_score=safe_int_env("COUNTER_TREND_MIN_SCORE", 82, min_val=70, max_val=95),
            max_signals_per_hour=safe_int_env("MAX_SIGNALS_PER_HOUR", 2, min_val=1, max_val=10),
            setup_expiry_seconds=safe_int_env("SETUP_EXPIRY_SECONDS", 300, min_val=60, max_val=600),
            trigger_expiry_seconds=safe_int_env("TRIGGER_EXPIRY_SECONDS", 120, min_val=30, max_val=300),
            max_entry_distance_atr=safe_float_env("MAX_ENTRY_DISTANCE_ATR", 0.25, min_val=0.05, max_val=0.75),
            atr_period=safe_int_env("ATR_PERIOD", 14, min_val=5, max_val=30),
            sl_multiplier=safe_float_env("SL_MULTIPLIER", 1.5, min_val=0.5, max_val=3.0),
            tp_multiplier=safe_float_env("TP_MULTIPLIER", 3.0, min_val=1.0, max_val=5.0),
            tdi_oversold=safe_float_env("TDI_OVERSOLD", 25.0, min_val=15, max_val=35),
            tdi_soft_buy=safe_float_env("TDI_SOFT_BUY", 35.0, min_val=25, max_val=45),
            tdi_soft_sell=safe_float_env("TDI_SOFT_SELL", 65.0, min_val=55, max_val=75),
            tdi_overbought=safe_float_env("TDI_OVERBOUGHT", 75.0, min_val=65, max_val=85),
            grade_a_plus_threshold=safe_int_env("GRADE_A_PLUS_THRESHOLD", 90, min_val=80, max_val=98),
            grade_a_threshold=safe_int_env("GRADE_A_THRESHOLD", 82, min_val=70, max_val=95),
            grade_b_plus_threshold=safe_int_env("GRADE_B_PLUS_THRESHOLD", 75, min_val=65, max_val=85),
            grade_b_threshold=safe_int_env("GRADE_B_THRESHOLD", 70, min_val=60, max_val=80),
            grade_c_threshold=safe_int_env("GRADE_C_THRESHOLD", 60, min_val=50, max_val=75),
            symbol_cooldown_minutes=safe_int_env("SYMBOL_COOLDOWN_MINUTES", 30, min_val=5, max_val=120),
            break_even_threshold_minutes=safe_int_env("BREAK_EVEN_THRESHOLD_MINUTES", 480, min_val=30, max_val=720),
            min_bars_before_check=safe_int_env("MIN_BARS_BEFORE_CHECK", 2, min_val=1, max_val=5),
            enable_divergence=safe_bool_env("ENABLE_DIVERGENCE", True),
            enable_candle_patterns=safe_bool_env("ENABLE_CANDLE_PATTERNS", True),
            enable_support_resistance=safe_bool_env("ENABLE_SR", True),
            enable_bb_squeeze=safe_bool_env("ENABLE_BB_SQUEEZE", True),
            enable_session_filtering=safe_bool_env("ENABLE_SESSION_FILTERING", True),
            enable_htf_regime=safe_bool_env("ENABLE_HTF_REGIME", True),
            enable_structure_analysis=safe_bool_env("ENABLE_STRUCTURE_ANALYSIS", True),
            enable_volume_gate=safe_bool_env("ENABLE_VOLUME_GATE", True),
            enable_ltf_confirmation=safe_bool_env("ENABLE_LTF_CONFIRMATION", True),
            require_ltf_confirmation=safe_bool_env("REQUIRE_LTF_CONFIRMATION", True),
            ltf_min_confirmation=safe_float_env("LTF_MIN_CONFIRMATION", 0.65, min_val=0.4, max_val=0.9),
            require_htf_alignment=safe_bool_env("REQUIRE_HTF_ALIGNMENT", True),
            default_rrr=safe_float_env("DEFAULT_RRR", 2.0, min_val=1.0, max_val=5.0),
            min_rrr=safe_float_env("MIN_RRR", 1.5, min_val=1.0, max_val=3.0),
            max_rrr=safe_float_env("MAX_RRR", 4.0, min_val=2.0, max_val=6.0),
            risk_per_trade_percent=safe_float_env("RISK_PER_TRADE_PERCENT", 0.5, min_val=0.01, max_val=5.0),
            max_daily_trades=safe_int_env("MAX_DAILY_TRADES", 5, min_val=1, max_val=30),
            ai_enabled=safe_bool_env("AI_ENABLED", True),
            ai_min_interval_seconds=safe_int_env("AI_MIN_INTERVAL_SECONDS", 120, min_val=30, max_val=600),
            ai_cache_ttl=safe_int_env("AI_CACHE_TTL", 600, min_val=60, max_val=3600),
            fee_impact=safe_float_env("FEE_IMPACT", 0.0011, min_val=0.0005, max_val=0.005),
            min_quality_score=safe_int_env("MIN_QUALITY_SCORE", 50, min_val=30, max_val=90),
            min_signal_score=safe_int_env("MIN_SIGNAL_SCORE", 70, min_val=40, max_val=95),
            signal_cooldown_minutes=safe_int_env("SIGNAL_COOLDOWN_MINUTES", 30, min_val=1, max_val=60),
            max_signals_per_cycle=safe_int_env("MAX_SIGNALS_PER_CYCLE", 3, min_val=1, max_val=10),
            default_leverage=safe_int_env("DEFAULT_LEVERAGE", 5, min_val=1, max_val=50),
            min_leverage=safe_int_env("MIN_LEVERAGE", 1, min_val=1, max_val=10),
            max_leverage=safe_int_env("MAX_LEVERAGE", 20, min_val=1, max_val=100),
            use_futures=safe_bool_env("USE_FUTURES", True),
            session_multipliers={
                "ASIAN": safe_float_env("SESSION_ASIAN_MULTIPLIER", 0.7, min_val=0.3, max_val=1.0),
                "LONDON": safe_float_env("SESSION_LONDON_MULTIPLIER", 1.0, min_val=0.5, max_val=1.5),
                "NY": safe_float_env("SESSION_NY_MULTIPLIER", 1.2, min_val=0.5, max_val=1.5),
                "LATE": safe_float_env("SESSION_LATE_MULTIPLIER", 0.8, min_val=0.3, max_val=1.0),
            }
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
        self.logging = LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO").upper(),
            file=os.getenv("LOG_FILE", "logs/trading_bot.log"),
            format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )

        # ====== DEPLOYMENT ======
        env_str = os.getenv("ENVIRONMENT", "development").lower().strip()
        try:
            environment = Environment(env_str)
        except ValueError:
            environment = Environment.DEVELOPMENT

        run_mode_str = os.getenv("RUN_MODE", "DEMO").upper().strip()
        try:
            run_mode = RunMode(run_mode_str)
        except ValueError:
            run_mode = RunMode.DEMO

        self.deployment = DeploymentConfig(
            environment=environment,
            run_mode=run_mode,
            debug=safe_bool_env("DEBUG", False),
            port=safe_int_env("PORT", 8080, min_val=1024, max_val=65535),
            host=os.getenv("HOST", "0.0.0.0"),
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

        # Validate grade thresholds
        if self.strategy.grade_b_threshold >= self.strategy.grade_a_threshold:
            warnings.append(f"GRADE_B_THRESHOLD ({self.strategy.grade_b_threshold}) should be below GRADE_A_THRESHOLD ({self.strategy.grade_a_threshold})")
        if self.strategy.grade_c_threshold >= self.strategy.grade_b_threshold:
            warnings.append(f"GRADE_C_THRESHOLD ({self.strategy.grade_c_threshold}) should be below GRADE_B_THRESHOLD ({self.strategy.grade_b_threshold})")

        if self.strategy.min_signal_score > self.strategy.grade_b_threshold:
            warnings.append(f"MIN_SIGNAL_SCORE ({self.strategy.min_signal_score}) is above GRADE_B_THRESHOLD ({self.strategy.grade_b_threshold})")

        if self.strategy.min_rrr < 1.0:
            warnings.append(f"MIN_RRR ({self.strategy.min_rrr}) below 1.0")

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

    def get_grade(self, score: int) -> str:
        """Get grade based on v3.4.0 thresholds."""
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
