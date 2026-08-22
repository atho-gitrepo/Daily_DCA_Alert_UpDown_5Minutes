"""
Configuration management for the AI Trading Bot.
HYBRID STRATEGY: Super TDI + Super Bollinger Bands + Multi-Timeframe
Version: 3.3.0 - ADDED: Divergence, Candle Patterns, S/R, Session Filtering config
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
    polling_interval_seconds: int = 15


@dataclass
class StrategyConfig:
    """Strategy configuration with new v3.3.0 features."""

    # === Super Bollinger Bands ===
    bb_period: int = 34
    bb_dev: float = 1.750

    # === Multi-Timeframe Settings ===
    ltf_min_confirmation: float = 0.70
    require_ltf_confirmation: bool = True
    require_htf_alignment: bool = False

    # === Leverage ===
    default_leverage: int = 5
    min_leverage: int = 1
    max_leverage: int = 20

    # === Risk & RRR ===
    rrr_ratio: float = 1.5
    risk_per_trade_percent: float = 0.5
    max_daily_trades: int = 5
    max_risk_percent: float = 0.015

    # === AI ===
    ai_enabled: bool = True
    ai_min_interval_seconds: int = 120
    ai_cache_ttl: int = 600

    # === Fee ===
    fee_impact: float = 0.0011

    # === Signal Settings ===
    min_quality_score: int = 50
    signal_cooldown_minutes: int = 30
    max_signals_per_hour: int = 8
    max_signals_per_cycle: int = 3

    # Grade thresholds
    grade_a_threshold: int = 80
    grade_b_threshold: int = 70
    grade_c_threshold: int = 60

    # Signal scoring
    min_signal_score: int = 70

    # === Signal Lifecycle ===
    symbol_cooldown_minutes: int = 30
    break_even_threshold_minutes: int = 480
    min_bars_before_check: int = 2

    # === Use Futures ===
    use_futures: bool = True

    # ===== NEW v3.3.0: Enhanced Features =====

    # Divergence Detection
    enable_divergence_detection: bool = True
    divergence_lookback: int = 20
    divergence_min_strength: float = 0.3

    # Candle Pattern Recognition
    enable_candle_patterns: bool = True
    min_pattern_confidence: float = 0.5

    # Support/Resistance
    enable_support_resistance: bool = True
    sr_lookback: int = 100
    sr_num_levels: int = 3

    # BB Squeeze
    enable_bb_squeeze: bool = True
    squeeze_threshold: float = 0.6
        # ========== TIMEFRAME CONFIGURATION ==========
    ULTRA_LTF_TIMEFRAME = "1m"    # Ultra-fine entry timing
    LTF_TIMEFRAME = "5m"          # Entry confirmation
    TIMEFRAME = "15m"             # Main decision timeframe
    HTF_TIMEFRAME = "1h"          # Medium trend
    ULTRA_HTF_TIMEFRAME = "4h"    # Major trend

    # ========== HOLD TIME CONFIGURATION ==========
    MAX_HOLD_MINUTES = 60         # Maximum 1 hour
    MIN_HOLD_MINUTES = 15         # Minimum 15 minutes
    EXIT_AT_TIME = True           # Exit at time target
    # Session Filtering
    enable_session_filtering: bool = True
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
class FirebaseConfig:
    """Firebase configuration (kept for backward compatibility)."""
    credentials: Optional[Dict[str, Any]] = None
    credentials_path: Optional[Path] = None
    database_url: str = ""
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
    """Complete configuration with all required attributes."""

    VERSION = "3.3.0"

    def __init__(self):
        # Initialize all config sections
        self.binance = BinanceConfig()
        self.market = MarketConfig()
        self.strategy = StrategyConfig()
        self.performance = PerformanceConfig()
        self.groq = GroqConfig()
        self.telegram = TelegramConfig()
        self.firebase = FirebaseConfig()
        self.mongodb = MongoDBConfig()
        self.logging = LoggingConfig()
        self.deployment = DeploymentConfig()

        self._load_from_env()
        self._validate()
        self._setup_directories()

        logger.info(f"Config initialized (v{self.VERSION}, environment: {self.deployment.environment.value})")
        logger.info(f"✅ Grade thresholds: A={self.strategy.grade_a_threshold}, B={self.strategy.grade_b_threshold}, C={self.strategy.grade_c_threshold}")
        logger.info(f"✅ Min Signal Score: {self.strategy.min_signal_score}/100")
        logger.info(f"✅ Max Daily Trades: {self.strategy.max_daily_trades}")
        logger.info(f"✅ Cache enabled: {self.performance.cache_enabled}")
        logger.info(f"✅ MongoDB enabled: {self.mongodb.enabled}")
        # NEW v3.3.0
        logger.info(f"✅ Divergence Detection: {self.strategy.enable_divergence_detection}")
        logger.info(f"✅ Candle Patterns: {self.strategy.enable_candle_patterns}")
        logger.info(f"✅ Support/Resistance: {self.strategy.enable_support_resistance}")
        logger.info(f"✅ BB Squeeze: {self.strategy.enable_bb_squeeze}")
        logger.info(f"✅ Session Filtering: {self.strategy.enable_session_filtering}")

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
        default_symbols = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
            "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT"
        ]

        self.market = MarketConfig(
            quote_asset=os.getenv("QUOTE_ASSET", "USDT"),
            symbols=safe_list_env("SYMBOLS", default_symbols),
            timeframe=os.getenv("TIMEFRAME", "15m"),
            htf_timeframe=os.getenv("HTF_TIMEFRAME", "1h"),
            ltf_timeframe=os.getenv("LTF_TIMEFRAME", "5m"),
            polling_interval_seconds=safe_int_env("POLLING_INTERVAL_SECONDS", 15, min_val=1, max_val=60),
        )

        # ====== STRATEGY ======
        self.strategy = StrategyConfig(
            bb_period=safe_int_env("BB_PERIOD", 34, min_val=5, max_val=50),
            bb_dev=safe_float_env("BB_DEV", 1.750, min_val=0.5, max_val=4.0),
            ltf_min_confirmation=safe_float_env("LTF_MIN_CONFIRMATION", 0.70, min_val=0.3, max_val=0.9),
            require_ltf_confirmation=safe_bool_env("REQUIRE_LTF_CONFIRMATION", True),
            require_htf_alignment=safe_bool_env("REQUIRE_HTF_ALIGNMENT", False),
            default_leverage=safe_int_env("DEFAULT_LEVERAGE", 5, min_val=1, max_val=50),
            min_leverage=safe_int_env("MIN_LEVERAGE", 1, min_val=1, max_val=10),
            max_leverage=safe_int_env("MAX_LEVERAGE", 20, min_val=1, max_val=100),
            rrr_ratio=safe_float_env("RRR_RATIO", 1.5, min_val=0.5, max_val=5.0),
            risk_per_trade_percent=safe_float_env("RISK_PER_TRADE_PERCENT", 0.5, min_val=0.01, max_val=5.0),
            max_daily_trades=safe_int_env("MAX_DAILY_TRADES", 5, min_val=1, max_val=30),
            max_risk_percent=safe_float_env("MAX_RISK_PERCENT", 0.015, min_val=0.001, max_val=0.05),
            ai_enabled=safe_bool_env("AI_ENABLED", True),
            ai_min_interval_seconds=safe_int_env("AI_MIN_INTERVAL_SECONDS", 120, min_val=30, max_val=600),
            ai_cache_ttl=safe_int_env("AI_CACHE_TTL", 600, min_val=60, max_val=3600),
            fee_impact=safe_float_env("FEE_IMPACT", 0.0011, min_val=0.0005, max_val=0.005),
            min_quality_score=safe_int_env("MIN_QUALITY_SCORE", 50, min_val=30, max_val=90),
            signal_cooldown_minutes=safe_int_env("SIGNAL_COOLDOWN_MINUTES", 30, min_val=1, max_val=60),
            max_signals_per_hour=safe_int_env("MAX_SIGNALS_PER_HOUR", 8, min_val=1, max_val=30),
            max_signals_per_cycle=safe_int_env("MAX_SIGNALS_PER_CYCLE", 3, min_val=1, max_val=10),
            grade_a_threshold=safe_int_env("GRADE_A_THRESHOLD", 80, min_val=70, max_val=95),
            grade_b_threshold=safe_int_env("GRADE_B_THRESHOLD", 70, min_val=60, max_val=85),
            grade_c_threshold=safe_int_env("GRADE_C_THRESHOLD", 60, min_val=50, max_val=75),
            min_signal_score=safe_int_env("MIN_SIGNAL_SCORE", 70, min_val=40, max_val=95),
            symbol_cooldown_minutes=safe_int_env("SYMBOL_COOLDOWN_MINUTES", 30, min_val=5, max_val=120),
            break_even_threshold_minutes=safe_int_env("BREAK_EVEN_THRESHOLD_MINUTES", 480, min_val=30, max_val=720),
            min_bars_before_check=safe_int_env("MIN_BARS_BEFORE_CHECK", 2, min_val=1, max_val=5),
            use_futures=safe_bool_env("USE_FUTURES", True),
            # NEW v3.3.0
            enable_divergence_detection=safe_bool_env("ENABLE_DIVERGENCE", True),
            divergence_lookback=safe_int_env("DIVERGENCE_LOOKBACK", 20, min_val=10, max_val=50),
            divergence_min_strength=safe_float_env("DIVERGENCE_MIN_STRENGTH", 0.3, min_val=0.1, max_val=0.9),
            enable_candle_patterns=safe_bool_env("ENABLE_CANDLE_PATTERNS", True),
            min_pattern_confidence=safe_float_env("MIN_PATTERN_CONFIDENCE", 0.5, min_val=0.3, max_val=0.9),
            enable_support_resistance=safe_bool_env("ENABLE_SR", True),
            sr_lookback=safe_int_env("SR_LOOKBACK", 100, min_val=50, max_val=200),
            sr_num_levels=safe_int_env("SR_NUM_LEVELS", 3, min_val=1, max_val=5),
            enable_bb_squeeze=safe_bool_env("ENABLE_BB_SQUEEZE", True),
            squeeze_threshold=safe_float_env("SQUEEZE_THRESHOLD", 0.6, min_val=0.3, max_val=0.9),
            enable_session_filtering=safe_bool_env("ENABLE_SESSION_FILTERING", True),
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

        # ====== GROQ / AI ======
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

        # ====== FIREBASE ======
        creds = self._parse_firebase_credentials()
        self.firebase = FirebaseConfig(
            credentials=creds,
            credentials_path=Path(os.getenv("FIREBASE_CREDENTIALS_PATH")) if os.getenv("FIREBASE_CREDENTIALS_PATH") else None,
            database_url=os.getenv("FIREBASE_DATABASE_URL", ""),
            enabled=creds is not None,
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
            logger.warning(f"Invalid environment '{env_str}', using DEVELOPMENT")
            environment = Environment.DEVELOPMENT

        run_mode_str = os.getenv("RUN_MODE", "DEMO").upper().strip()
        try:
            run_mode = RunMode(run_mode_str)
        except ValueError:
            logger.warning(f"Invalid run mode '{run_mode_str}', using DEMO")
            run_mode = RunMode.DEMO

        self.deployment = DeploymentConfig(
            environment=environment,
            run_mode=run_mode,
            debug=safe_bool_env("DEBUG", False),
            port=safe_int_env("PORT", 8080, min_val=1024, max_val=65535),
            host=os.getenv("HOST", "0.0.0.0"),
        )

    def _parse_firebase_credentials(self) -> Optional[Dict[str, Any]]:
        """Parse Firebase credentials."""
        json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
        if json_str:
            try:
                json_str = json_str.strip()
                credentials = json.loads(json_str)
                required_fields = ["type", "project_id", "private_key", "client_email"]
                missing_fields = [field for field in required_fields if field not in credentials]
                if missing_fields:
                    logger.error(f"Firebase credentials JSON missing required fields: {missing_fields}")
                    return None
                logger.info("Firebase credentials loaded from JSON string")
                return credentials
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {e}")
                return None
            except Exception as e:
                logger.error(f"Error loading Firebase credentials from JSON: {e}")
                return None

        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path:
            try:
                path = Path(cred_path)
                if path.exists() and path.is_file():
                    with open(path, 'r') as f:
                        credentials = json.load(f)
                    logger.info(f"Firebase credentials loaded from file: {cred_path}")
                    return credentials
                else:
                    logger.warning(f"Firebase credentials file not found: {cred_path}")
            except Exception as e:
                logger.error(f"Error loading Firebase credentials from file: {e}")

        return None

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

        if enabled:
            logger.info("MongoDB configuration loaded from environment")
        else:
            logger.debug("MongoDB not configured - using in-memory only")

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

        if self.strategy.rrr_ratio < 1.0:
            warnings.append(f"RRR_RATIO ({self.strategy.rrr_ratio}) below 1.0")

        if self.strategy.min_leverage > self.strategy.max_leverage:
            warnings.append(f"MIN_LEVERAGE ({self.strategy.min_leverage}) > MAX_LEVERAGE ({self.strategy.max_leverage})")
        if self.strategy.default_leverage > self.strategy.max_leverage:
            warnings.append(f"DEFAULT_LEVERAGE ({self.strategy.default_leverage}) exceeds MAX_LEVERAGE ({self.strategy.max_leverage})")

        # MongoDB validation
        if self.mongodb.enabled:
            if not self.mongodb.uri:
                warnings.append("MongoDB enabled but URI is empty - check MONGODB_URI environment variable")

        # NEW v3.3.0 validation
        if self.strategy.enable_divergence_detection and self.strategy.divergence_lookback < 10:
            warnings.append(f"DIVERGENCE_LOOKBACK ({self.strategy.divergence_lookback}) is very low")

        if self.strategy.enable_session_filtering:
            for session, multiplier in self.strategy.session_multipliers.items():
                if multiplier < 0.3 or multiplier > 1.5:
                    warnings.append(f"SESSION_MULTIPLIER for {session} ({multiplier}) outside recommended range (0.3-1.5)")

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
        if score >= self.strategy.grade_a_threshold:
            return "A"
        elif score >= self.strategy.grade_b_threshold:
            return "B"
        elif score >= self.strategy.grade_c_threshold:
            return "C"
        else:
            return "D"

    def get_timeframes(self) -> Dict[str, str]:
        return {
            "htf": self.market.htf_timeframe,
            "mtf": self.market.timeframe,
            "ltf": self.market.ltf_timeframe,
        }

    def get_rrr_config(self) -> Dict[str, float]:
        return {"rrr": self.strategy.rrr_ratio}

    def get_signal_config(self) -> Dict[str, Any]:
        return {
            "min_quality_score": self.strategy.min_quality_score,
            "min_signal_score": self.strategy.min_signal_score,
            "signal_cooldown_minutes": self.strategy.signal_cooldown_minutes,
            "max_signals_per_hour": self.strategy.max_signals_per_hour,
            "max_signals_per_cycle": self.strategy.max_signals_per_cycle,
            "max_daily_trades": self.strategy.max_daily_trades,
            "require_ltf_confirmation": self.strategy.require_ltf_confirmation,
            "require_htf_alignment": self.strategy.require_htf_alignment,
            "ltf_min_confirmation": self.strategy.ltf_min_confirmation,
            "break_even_threshold_minutes": self.strategy.break_even_threshold_minutes,
            "min_bars_before_check": self.strategy.min_bars_before_check,
            "grade_a_threshold": self.strategy.grade_a_threshold,
            "grade_b_threshold": self.strategy.grade_b_threshold,
            "grade_c_threshold": self.strategy.grade_c_threshold,
            # NEW v3.3.0
            "enable_divergence_detection": self.strategy.enable_divergence_detection,
            "enable_candle_patterns": self.strategy.enable_candle_patterns,
            "enable_support_resistance": self.strategy.enable_support_resistance,
            "enable_bb_squeeze": self.strategy.enable_bb_squeeze,
            "enable_session_filtering": self.strategy.enable_session_filtering,
        }

    def get_leverage_config(self) -> Dict[str, Any]:
        return {
            "default": self.strategy.default_leverage,
            "min": self.strategy.min_leverage,
            "max": self.strategy.max_leverage,
        }

    def get_mongodb_config(self) -> Dict[str, Any]:
        """Get MongoDB configuration as dict."""
        return {
            "uri": self.mongodb.uri,
            "db_name": self.mongodb.db_name,
            "active_collection": self.mongodb.active_collection,
            "resolved_collection": self.mongodb.resolved_collection,
            "archive_collection": self.mongodb.archive_collection,
            "enabled": self.mongodb.enabled,
            "max_pool_size": self.mongodb.max_pool_size,
            "min_pool_size": self.mongodb.min_pool_size,
            "connect_timeout_ms": self.mongodb.connect_timeout_ms,
            "socket_timeout_ms": self.mongodb.socket_timeout_ms,
            "server_selection_timeout_ms": self.mongodb.server_selection_timeout_ms,
        }


# ------------------- Singleton Instance -------------------

config = Config()

# Convenience exports
SYMBOLS = config.market.symbols
TIMEFRAME = config.market.timeframe
HTF_TIMEFRAME = config.market.htf_timeframe
LTF_TIMEFRAME = config.market.ltf_timeframe

ENVIRONMENT = config.deployment.environment.value
RUN_MODE = config.deployment.run_mode.value
DEMO_MODE = config.is_demo()
LOG_LEVEL = config.logging.level

# Strategy exports
BB_PERIOD = config.strategy.bb_period
BB_DEV = config.strategy.bb_dev
LTF_MIN_CONFIRMATION = config.strategy.ltf_min_confirmation
REQUIRE_LTF_CONFIRMATION = config.strategy.require_ltf_confirmation
REQUIRE_HTF_ALIGNMENT = config.strategy.require_htf_alignment

# Leverage exports
DEFAULT_LEVERAGE = config.strategy.default_leverage
MIN_LEVERAGE = config.strategy.min_leverage
MAX_LEVERAGE = config.strategy.max_leverage

# Risk exports
RRR_RATIO = config.strategy.rrr_ratio
RISK_PER_TRADE_PERCENT = config.strategy.risk_per_trade_percent
MAX_DAILY_TRADES = config.strategy.max_daily_trades
MAX_RISK_PERCENT = config.strategy.max_risk_percent

# Grade exports
GRADE_A_THRESHOLD = config.strategy.grade_a_threshold
GRADE_B_THRESHOLD = config.strategy.grade_b_threshold
GRADE_C_THRESHOLD = config.strategy.grade_c_threshold
MIN_SIGNAL_SCORE = config.strategy.min_signal_score

# AI exports
AI_ENABLED = config.strategy.ai_enabled
AI_MIN_INTERVAL_SECONDS = config.strategy.ai_min_interval_seconds
AI_CACHE_TTL = config.strategy.ai_cache_ttl

# Fee export
FEE_IMPACT = config.strategy.fee_impact

# Performance exports
CACHE_ENABLED = config.performance.cache_enabled
CACHE_TTL_SECONDS = config.performance.cache_ttl_seconds
CACHE_MAX_SIZE = config.performance.cache_max_size

# Signal lifecycle exports
BREAK_EVEN_THRESHOLD_MINUTES = config.strategy.break_even_threshold_minutes

# Firebase (kept for backward compatibility)
FIREBASE_ENABLED = config.firebase.enabled

# MongoDB exports
MONGODB_ENABLED = config.mongodb.enabled
MONGODB_URI = config.mongodb.uri
MONGODB_DB = config.mongodb.db_name

# NEW v3.3.0 exports
ENABLE_DIVERGENCE = config.strategy.enable_divergence_detection
ENABLE_CANDLE_PATTERNS = config.strategy.enable_candle_patterns
ENABLE_SR = config.strategy.enable_support_resistance
ENABLE_BB_SQUEEZE = config.strategy.enable_bb_squeeze
ENABLE_SESSION_FILTERING = config.strategy.enable_session_filtering
SESSION_MULTIPLIERS = config.strategy.session_multipliers

__all__ = [
    "config",
    "Config",
    "Environment",
    "RunMode",
    "SYMBOLS",
    "TIMEFRAME",
    "HTF_TIMEFRAME",
    "LTF_TIMEFRAME",
    "ENVIRONMENT",
    "RUN_MODE",
    "DEMO_MODE",
    "LOG_LEVEL",
    "BB_PERIOD",
    "BB_DEV",
    "LTF_MIN_CONFIRMATION",
    "REQUIRE_LTF_CONFIRMATION",
    "REQUIRE_HTF_ALIGNMENT",
    "DEFAULT_LEVERAGE",
    "MIN_LEVERAGE",
    "MAX_LEVERAGE",
    "RRR_RATIO",
    "RISK_PER_TRADE_PERCENT",
    "MAX_DAILY_TRADES",
    "MAX_RISK_PERCENT",
    "GRADE_A_THRESHOLD",
    "GRADE_B_THRESHOLD",
    "GRADE_C_THRESHOLD",
    "MIN_SIGNAL_SCORE",
    "AI_ENABLED",
    "AI_MIN_INTERVAL_SECONDS",
    "AI_CACHE_TTL",
    "FEE_IMPACT",
    "CACHE_ENABLED",
    "CACHE_TTL_SECONDS",
    "CACHE_MAX_SIZE",
    "BREAK_EVEN_THRESHOLD_MINUTES",
    "FIREBASE_ENABLED",
    "MONGODB_ENABLED",
    "MONGODB_URI",
    "MONGODB_DB",
    # NEW v3.3.0
    "ENABLE_DIVERGENCE",
    "ENABLE_CANDLE_PATTERNS",
    "ENABLE_SR",
    "ENABLE_BB_SQUEEZE",
    "ENABLE_SESSION_FILTERING",
    "SESSION_MULTIPLIERS",
]
