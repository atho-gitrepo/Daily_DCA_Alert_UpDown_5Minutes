"""
Market data fetcher for Binance cryptocurrency exchange - HYBRID STRATEGY.
Optimized for fast data fetching with multi-timeframe support (HTF, MTF, LTF).
Version: 3.4.0 - UPDATED: Production support, UMFutures client
"""

import pandas as pd
import numpy as np
import logging
import time
import json
import hashlib
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
from functools import lru_cache
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pickle
import os
import sys

# Redis import - optional with fallback
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Binance imports - support both old and new libraries
BINANCE_AVAILABLE = False
BINANCE_UM_AVAILABLE = False

try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException, BinanceRequestException
    BINANCE_AVAILABLE = True
except ImportError:
    BinanceClient = None
    BinanceAPIException = None
    BinanceRequestException = None

try:
    from binance.um_futures import UMFutures
    BINANCE_UM_AVAILABLE = True
except ImportError:
    UMFutures = None

# Local imports
from settings import config, Config

# Configure logging
logger = logging.getLogger(__name__)
data_logger = logging.getLogger("data_fetcher")

# Emoji indicators for log messages
EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DEBUG": "🔍",
    "CACHE": "💾",
    "WEBSOCKET": "🔌",
    "RATE": "⏱️",
    "DEMO": "🎮",
    "PRODUCTION": "🔴",
    "FETCH": "📊",
    "VALIDATE": "✔️",
    "PERFORMANCE": "⚡",
    "RETRY": "🔄",
    "THREAD": "🧵",
    "HEIKIN": "🕯️",
    "HTF": "📊",
    "LTF": "⏱️",
    "VERSION": "📌",
    "DB": "💾",
}


# Logging helper functions
def log_data_operation(operation: str, status: str, details: Optional[Dict] = None,
                       emoji: str = "", error: Optional[Exception] = None):
    """Log data operations with structured format."""
    timestamp = datetime.now().isoformat()
    log_message = f"[{timestamp}] {emoji} DATA_{operation}: {status}"

    if details:
        safe_details = {}
        sensitive_keys = ["api_key", "api_secret", "password", "token"]
        for k, v in details.items():
            if any(sensitive in k.lower() for sensitive in sensitive_keys):
                safe_details[k] = "***REDACTED***"
            else:
                safe_details[k] = v
        if safe_details:
            log_message += f" | Details: {safe_details}"

    if error:
        log_message += f" | Error: {str(error)}"

    if status == "FAILURE":
        data_logger.error(log_message)
    elif status == "WARNING":
        data_logger.warning(log_message)
    elif status == "START":
        data_logger.debug(log_message)
    else:
        data_logger.info(log_message)


# ------------------- Heikin Ashi Helper -------------------

def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Heikin Ashi candles from standard OHLC.
    """
    if df is None or df.empty or len(df) < 2:
        return df

    df = df.copy()

    # Heikin Ashi formulas
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2

    # Handle first row
    if len(df) > 0:
        df.loc[df.index[0], 'ha_open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2

    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)

    # Heikin Ashi body and color
    df['ha_body'] = abs(df['ha_close'] - df['ha_open'])
    df['ha_upper_wick'] = df['ha_high'] - df[['ha_open', 'ha_close']].max(axis=1)
    df['ha_lower_wick'] = df[['ha_open', 'ha_close']].min(axis=1) - df['ha_low']
    df['ha_color'] = np.where(df['ha_close'] > df['ha_open'], 1, -1)

    return df


# ------------------- Cache Manager -------------------

class CacheManager:
    """
    Caching manager for data fetcher.
    Supports both in-memory and Redis caching.
    """

    def __init__(self, enabled: bool = True, ttl_seconds: int = 300, max_size: int = 1000):
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache = {}
        self._timestamps = {}
        self._access_count = {}
        self._hit_count = 0
        self._miss_count = 0

        # Try Redis connection if available
        self._redis = None
        if REDIS_AVAILABLE:
            try:
                redis_host = os.getenv("REDIS_HOST", "localhost")
                redis_port = int(os.getenv("REDIS_PORT", 6379))
                redis_db = int(os.getenv("REDIS_DB", 0))
                redis_password = os.getenv("REDIS_PASSWORD", None)

                self._redis = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                self._redis.ping()
                data_logger.info(f"{EMOJI['CACHE']} DATA_CACHE: Redis cache connected at {redis_host}:{redis_port}")
            except Exception as e:
                data_logger.debug(f"{EMOJI['INFO']} DATA_CACHE: Redis not available ({e}), using in-memory cache")
                self._redis = None
        else:
            data_logger.debug(f"{EMOJI['INFO']} DATA_CACHE: Redis library not installed, using in-memory cache")

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.enabled:
            return None

        # Try Redis first
        if self._redis:
            try:
                value = self._redis.get(key)
                if value:
                    self._hit_count += 1
                    data_logger.debug(f"{EMOJI['CACHE']} DATA_CACHE: Redis hit for {key[:20]}...")
                    try:
                        return pickle.loads(value) if isinstance(value, bytes) else json.loads(value)
                    except:
                        return value
                else:
                    self._miss_count += 1
                    data_logger.debug(f"{EMOJI['INFO']} DATA_CACHE: Redis miss for {key[:20]}...")
                    return None
            except Exception as e:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_CACHE: Redis get error: {e}")
                # Fall back to memory cache

        # In-memory cache
        if key in self._cache:
            # Check TTL
            if time.time() - self._timestamps[key] < self.ttl_seconds:
                self._hit_count += 1
                self._access_count[key] = self._access_count.get(key, 0) + 1
                data_logger.debug(f"{EMOJI['CACHE']} DATA_CACHE: Memory hit for {key[:20]}...")
                return self._cache[key]
            else:
                # Expired
                del self._cache[key]
                del self._timestamps[key]
                if key in self._access_count:
                    del self._access_count[key]

        self._miss_count += 1
        data_logger.debug(f"{EMOJI['INFO']} DATA_CACHE: Memory miss for {key[:20]}...")
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        if not self.enabled:
            return

        # Check cache size and evict if needed
        if len(self._cache) >= self.max_size:
            # Evict least recently used
            if self._access_count:
                least_used = min(self._access_count, key=self._access_count.get)
                del self._cache[least_used]
                del self._timestamps[least_used]
                del self._access_count[least_used]
                data_logger.debug(f"{EMOJI['CACHE']} DATA_CACHE: Evicted {least_used[:20]}...")

        # Store in Redis if available
        if self._redis:
            try:
                serialized = pickle.dumps(value) if not isinstance(value, (str, int, float, bool)) else json.dumps(value)
                self._redis.setex(key, self.ttl_seconds, serialized)
                data_logger.debug(f"{EMOJI['CACHE']} DATA_CACHE: Redis set for {key[:20]}...")
            except Exception as e:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_CACHE: Redis set error: {e}")

        # Store in memory
        self._cache[key] = value
        self._timestamps[key] = time.time()
        self._access_count[key] = self._access_count.get(key, 0) + 1

        data_logger.debug(f"{EMOJI['CACHE']} DATA_CACHE: Memory set for {key[:20]}...")

    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        self._timestamps.clear()
        self._access_count.clear()
        self._hit_count = 0
        self._miss_count = 0

        # Clear Redis if available
        if self._redis:
            try:
                self._redis.flushdb()
                data_logger.info(f"{EMOJI['CACHE']} DATA_CACHE: Redis cache cleared")
            except Exception as e:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_CACHE: Redis clear error: {e}")

        data_logger.info(f"{EMOJI['CACHE']} DATA_CACHE: Memory cache cleared")

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0

        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "total": total,
            "hit_rate": f"{hit_rate:.2%}",
            "size": len(self._cache),
            "redis_available": self._redis is not None
        }


# ------------------- Rate Limiter -------------------

class RateLimiter:
    """
    Rate limiter for API calls.
    Implements token bucket algorithm.
    """

    def __init__(self, max_requests_per_minute: int = 1200):
        self.max_requests_per_minute = max_requests_per_minute
        self.rate_limit = max_requests_per_minute / 60.0
        self.tokens = self.rate_limit
        self.last_request_time = time.time()
        self._lock = threading.Lock()

        data_logger.info(f"{EMOJI['RATE']} DATA_RATE: Rate limiter initialized: {max_requests_per_minute} req/min")

    def wait(self, tokens: int = 1) -> float:
        """Wait until tokens are available."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_request_time

            self.tokens = min(self.rate_limit, self.tokens + elapsed * self.rate_limit)
            self.last_request_time = now

            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / self.rate_limit
                data_logger.debug(f"{EMOJI['RATE']} DATA_RATE: Rate limit, waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                self.tokens = 0
                self.last_request_time = time.time()
                return wait_time
            else:
                self.tokens -= tokens
                return 0.0


# ------------------- Data Fetcher -------------------

class DataFetcher:
    """
    Handles connection to the exchange (Binance) and fetches/cleans market data.
    Optimized for hybrid strategy with multi-timeframe support.
    Version: 3.4.0 - Production Ready
    """

    # Required columns for indicator validation
    REQUIRED_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

    # Recommended columns for strategy (warn if missing but don't reject)
    RECOMMENDED_COLUMNS = [
        'tdi_slow_ma', 'tdi_fast_ma', 'tdi_zone',
        'bb_middle', 'bb_upper', 'bb_lower', 'bb_position', 'bb_width_percent',
        'ha_color', 'ha_low', 'ha_high', 'ha_close',
        'volume_sma', 'volume_ratio',
        'rsi',
    ]

    # Cache version for invalidation on updates
    CACHE_VERSION = "3.4.0"

    def __init__(self, demo_mode: Optional[bool] = None):
        log_data_operation("INIT", "START",
                          {"version": self.CACHE_VERSION},
                          emoji=EMOJI['START'])

        # ===== PRODUCTION MODE DETECTION =====
        # Check RUN_MODE from environment
        run_mode = os.getenv("RUN_MODE", "DEMO").upper().strip()
        is_production_mode = run_mode == "PRODUCTION"

        # Determine demo mode:
        # - If explicitly passed, use that
        # - Else if PRODUCTION mode, force demo_mode=False
        # - Else use config.is_demo()
        if demo_mode is not None:
            self.demo_mode = demo_mode
        elif is_production_mode:
            self.demo_mode = False
            data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: PRODUCTION MODE detected - using REAL data")
        else:
            self.demo_mode = config.is_demo()

        # Store production mode flag
        self.is_production_mode = is_production_mode and not self.demo_mode

        self._init_cache()
        self._init_rate_limiter()
        self._init_executor()

        # Initialize Binance client
        self.client = None
        self.um_client = None
        self._init_binance_client()

        self.ws_manager = None
        self.ws_thread = None
        self.ws_callbacks = {}
        self.ws_running = False

        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "validation_warnings": 0,
            "api_errors": 0,
            "connection_errors": 0,
            "last_error": None,
            "last_error_time": None,
            "demo_mode": self.demo_mode,
            "production_mode": self.is_production_mode,
        }

        mode_label = "🔴 PRODUCTION" if self.is_production_mode else "🎮 DEMO"
        data_logger.info(f"{EMOJI['SUCCESS']} DATA_INIT: DataFetcher v{self.CACHE_VERSION} initialized ({mode_label})")

    def _init_cache(self):
        """Initialize cache with production-aware TTL."""
        # Shorter cache TTL for production to get fresher data
        if self.is_production_mode:
            ttl = 60  # 1 minute in production
            data_logger.info(f"{EMOJI['PRODUCTION']} DATA_CACHE: Production mode - cache TTL reduced to {ttl}s")
        else:
            ttl = config.performance.cache_ttl_seconds

        self.cache = CacheManager(
            enabled=config.performance.cache_enabled,
            ttl_seconds=ttl,
            max_size=config.performance.cache_max_size
        )
        data_logger.debug(f"{EMOJI['CACHE']} DATA_CACHE: Cache initialized (TTL: {ttl}s)")

    def _init_rate_limiter(self):
        """Initialize rate limiter with production-aware limits."""
        # Lower rate limit for production to avoid being banned
        if self.is_production_mode:
            rate_limit = 600  # 600 req/min in production (half of default)
            data_logger.info(f"{EMOJI['PRODUCTION']} DATA_RATE: Production mode - rate limit reduced to {rate_limit} req/min")
        else:
            rate_limit = config.performance.binance_rate_limit

        self.rate_limiter = RateLimiter(
            max_requests_per_minute=rate_limit
        )
        data_logger.debug(f"{EMOJI['RATE']} DATA_RATE: Rate limiter initialized")

    def _init_executor(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        data_logger.debug(f"{EMOJI['THREAD']} DATA_THREAD: Thread pool executor initialized")

    def _init_binance_client(self):
        """Initialize Binance client with proper error handling."""
        # If in production mode, we MUST have a client
        if self.is_production_mode:
            data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: Initializing Binance client for PRODUCTION...")

        # Try UMFutures first (newer, better for futures)
        if BINANCE_UM_AVAILABLE:
            try:
                api_key = config.binance.api_key
                api_secret = config.binance.api_secret
                testnet = config.binance.testnet
                base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"

                if api_key and api_secret:
                    self.um_client = UMFutures(key=api_key, secret=api_secret, base_url=base_url)
                else:
                    if self.is_production_mode:
                        data_logger.error(f"{EMOJI['PRODUCTION']} DATA_INIT: No API credentials for PRODUCTION!")
                    self.um_client = UMFutures(base_url=base_url)

                # Test connection
                self.um_client.time()

                data_logger.info(f"{EMOJI['SUCCESS']} DATA_INIT: Binance UMFutures client initialized (testnet: {testnet})")

                # If production mode, we're done
                if self.is_production_mode:
                    data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: PRODUCTION client ready")
                    return

            except Exception as e:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_INIT: UMFutures init failed: {e}")

        # Fallback to legacy client
        if not self.um_client and BINANCE_AVAILABLE:
            try:
                api_key = config.binance.api_key
                api_secret = config.binance.api_secret
                testnet = config.binance.testnet

                if not api_key or not api_secret:
                    if self.is_production_mode:
                        data_logger.error(f"{EMOJI['PRODUCTION']} DATA_INIT: No API credentials for PRODUCTION!")
                        self.demo_mode = True
                        self.is_production_mode = False
                        return
                    data_logger.warning(f"{EMOJI['WARNING']} DATA_INIT: Binance API credentials not configured.")
                    self.demo_mode = True
                    return

                self.client = BinanceClient(
                    api_key=api_key,
                    api_secret=api_secret,
                    testnet=testnet,
                    requests_params={'timeout': config.binance.request_timeout}
                )

                # Test connection
                self.client.ping()
                server_time = self.client.get_server_time()

                data_logger.info(f"{EMOJI['SUCCESS']} DATA_INIT: Binance client initialized (testnet: {testnet})")
                data_logger.info(f"{EMOJI['INFO']} DATA_INIT: Server time: {datetime.fromtimestamp(server_time['serverTime']/1000)}")

                if self.is_production_mode:
                    data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: PRODUCTION client ready")

            except Exception as e:
                data_logger.error(f"{EMOJI['ERROR']} DATA_INIT: Failed to initialize Binance client: {e}")
                if self.is_production_mode:
                    data_logger.error(f"{EMOJI['ERROR']} DATA_INIT: PRODUCTION mode requires working Binance client!")
                    raise
                self.demo_mode = True
        else:
            # No client available
            if self.is_production_mode:
                data_logger.error(f"{EMOJI['ERROR']} DATA_INIT: No Binance library available for PRODUCTION!")
                data_logger.error(f"{EMOJI['ERROR']} DATA_INIT: Install: pip install python-binance")
                raise RuntimeError("Cannot run in PRODUCTION mode without Binance library")
            data_logger.warning(f"{EMOJI['WARNING']} DATA_INIT: Binance library not available. Running in DEMO mode.")
            self.demo_mode = True

    def _is_demo_mode(self) -> bool:
        """Check if running in demo mode."""
        return self.demo_mode or not (self.client or self.um_client)

    def _generate_cache_key(self, symbol: str, interval: str, limit: int, params: Optional[Dict] = None) -> str:
        """Include version in cache key for invalidation on updates."""
        key_data = f"{self.CACHE_VERSION}_{symbol}_{interval}_{limit}"
        if params:
            key_data += f"_{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _validate_dataframe(self, df: pd.DataFrame, check_recommended: bool = False) -> bool:
        """
        Validate DataFrame with optional recommended column checks.
        """
        if df is None or df.empty:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_VALIDATE: DataFrame is empty or None")
            return False

        # Check required columns
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_VALIDATE: Missing required columns: {missing_cols}")
            return False

        # Check recommended columns (warn only)
        if check_recommended:
            missing_recommended = [col for col in self.RECOMMENDED_COLUMNS if col not in df.columns]
            if missing_recommended:
                self.metrics["validation_warnings"] += 1
                data_logger.debug(
                    f"{EMOJI['DEBUG']} DATA_VALIDATE: Missing recommended columns: {missing_recommended[:5]}..."
                )

        # Check for NaN values
        if df.isnull().any().any():
            nan_cols = df.columns[df.isnull().any()].tolist()
            critical_nan = [c for c in nan_cols if c in self.REQUIRED_COLUMNS]
            if critical_nan:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_VALIDATE: NaN in critical columns: {critical_nan}")
                return False
            else:
                data_logger.debug(f"{EMOJI['DEBUG']} DATA_VALIDATE: NaN in non-critical columns: {nan_cols[:5]}")

        # Check for infinite values
        if df.isin([np.inf, -np.inf]).any().any():
            data_logger.warning(f"{EMOJI['WARNING']} DATA_VALIDATE: Infinite values detected")
            return False

        return True

    def fetch_klines(self, symbol: str, interval: str, limit: int,
                     use_cache: bool = True, force_refresh: bool = False,
                     heikin_ashi: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetches historical kline data with caching and retry logic.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)
            limit: Number of candles to fetch
            use_cache: Whether to use cache
            force_refresh: Force refresh from API
            heikin_ashi: Whether to calculate Heikin Ashi candles

        Returns:
            DataFrame with OHLCV data, or None if fetch failed
        """
        start_time = time.time()
        cache_key = self._generate_cache_key(symbol, interval, limit)

        log_data_operation("FETCH", "START",
                          {"symbol": symbol, "interval": interval, "limit": limit, "heikin_ashi": heikin_ashi},
                          emoji=EMOJI['FETCH'])

        # In production, reduce cache usage for real-time data
        if self.is_production_mode and interval in ['1m', '5m']:
            # Force refresh for short intervals in production
            use_cache = use_cache and not force_refresh
            if use_cache:
                # But still check cache briefly
                pass

        # Check cache
        if use_cache and not force_refresh:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                self.metrics["cache_hits"] += 1
                data_logger.info(f"{EMOJI['CACHE']} DATA_FETCH: Cache hit for {symbol} ({interval})")
                return cached_data
            else:
                self.metrics["cache_misses"] += 1

        try:
            # Fetch data - use live data if available, else demo
            if self._is_demo_mode() or not (self.client or self.um_client):
                if self.is_production_mode:
                    data_logger.error(f"{EMOJI['PRODUCTION']} DATA_FETCH: No client in PRODUCTION mode!")
                    return None
                df = self._fetch_demo_klines(symbol, interval, limit)
            else:
                df = self._fetch_live_klines(symbol, interval, limit)

            # Validate
            if df is None or df.empty:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_FETCH: No data for {symbol}")
                return None

            if not self._validate_dataframe(df):
                data_logger.warning(f"{EMOJI['WARNING']} DATA_FETCH: Invalid DataFrame for {symbol}")
                return None

            # Calculate Heikin Ashi if requested
            if heikin_ashi and df is not None and not df.empty:
                df = calculate_heikin_ashi(df)
                data_logger.debug(f"{EMOJI['HEIKIN']} DATA_FETCH: Heikin Ashi calculated for {symbol}")

            # Cache
            if use_cache and df is not None and not df.empty:
                self.cache.set(cache_key, df)

            elapsed_time = time.time() - start_time
            self.metrics["successful_requests"] += 1
            self.metrics["total_time"] += elapsed_time

            data_logger.info(f"{EMOJI['SUCCESS']} DATA_FETCH: Fetched {len(df)} candles for {symbol} "
                           f"({elapsed_time*1000:.2f}ms)")

            return df

        except Exception as e:
            self.metrics["failed_requests"] += 1
            self.metrics["last_error"] = str(e)
            self.metrics["last_error_time"] = datetime.now().isoformat()
            log_data_operation("FETCH", "FAILURE",
                              {"symbol": symbol, "error": str(e)},
                              emoji=EMOJI['ERROR'])
            data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Failed to fetch {symbol}: {e}")

            # In production, re-raise for critical errors
            if self.is_production_mode:
                raise

            return None
        finally:
            self.metrics["total_requests"] += 1

    def _fetch_live_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Fetch live klines from Binance API with retry logic."""
        if not (self.client or self.um_client):
            return None

        max_retries = 3 if self.is_production_mode else getattr(config.performance, 'max_retries', 3)
        retry_delay = 3 if self.is_production_mode else getattr(config.performance, 'retry_delay_seconds', 5)

        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait()

                # Try UMFutures first
                if self.um_client:
                    raw_klines = self.um_client.klines(
                        symbol=symbol,
                        interval=interval,
                        limit=limit
                    )
                elif self.client:
                    raw_klines = self.client.get_historical_klines(
                        symbol=symbol,
                        interval=interval,
                        limit=limit
                    )
                else:
                    return None

                if not raw_klines:
                    data_logger.warning(f"{EMOJI['WARNING']} DATA_FETCH: No data returned for {symbol}")
                    return None

                df = self._convert_klines_to_dataframe(raw_klines)
                return df

            except Exception as e:
                error_msg = str(e)
                if "API-key format invalid" in error_msg or "Invalid API-key" in error_msg:
                    data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Invalid API key for {symbol}")
                    if self.is_production_mode:
                        raise
                    self.client = None
                    self.um_client = None
                    return self._fetch_demo_klines(symbol, interval, limit)

                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    data_logger.warning(f"{EMOJI['RETRY']} DATA_FETCH: Retry {attempt+1}/{max_retries} "
                                       f"for {symbol} in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Max retries exceeded for {symbol}: {e}")
                    if self.is_production_mode:
                        raise
                    return None

        return None

    def _fetch_demo_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Generate synthetic demo data."""
        log_data_operation("DEMO", "START",
                          {"symbol": symbol, "interval": interval, "limit": limit},
                          emoji=EMOJI['DEMO'])

        # If in production mode, this should never happen
        if self.is_production_mode:
            data_logger.error(f"{EMOJI['PRODUCTION']} DATA_DEMO: DEMO data requested in PRODUCTION mode!")
            return None

        try:
            base_price = self._get_base_price_for_symbol(symbol)
            np.random.seed(hash(symbol) % 2**32)

            end_time = datetime.now()
            interval_minutes = self._interval_to_minutes(interval)
            timestamps = pd.date_range(
                end=end_time,
                periods=limit,
                freq=f"{interval_minutes}min"
            )

            # Generate price data with realistic properties
            returns = np.random.normal(0.0005, 0.01, limit)
            if np.random.random() > 0.7:
                trend_strength = np.random.uniform(0.001, 0.003)
                trend_direction = 1 if np.random.random() > 0.5 else -1
                returns += trend_direction * trend_strength * np.linspace(0, 1, limit)

            price = base_price * np.exp(np.cumsum(returns))

            # Add realistic volatility
            volatility = 0.015 * (1 + 0.5 * np.random.random())

            df = pd.DataFrame({
                'open_time': timestamps,
                'open': price * (1 + np.random.uniform(-volatility, volatility, limit)),
                'high': price * (1 + np.abs(np.random.uniform(0, volatility * 1.5, limit))),
                'low': price * (1 - np.abs(np.random.uniform(0, volatility * 1.5, limit))),
                'close': price,
                'volume': np.random.exponential(100, limit) * base_price / 10000
            })

            # Ensure high/low are correct
            df['high'] = df[['open', 'high', 'close']].max(axis=1)
            df['low'] = df[['open', 'low', 'close']].min(axis=1)

            # Add some randomness to open/close
            df['open'] = df['open'] * (1 + np.random.uniform(-0.001, 0.001, limit))
            df['close'] = df['close'] * (1 + np.random.uniform(-0.001, 0.001, limit))

            df.set_index('open_time', inplace=True)

            data_logger.info(f"{EMOJI['DEMO']} DATA_DEMO: Generated {len(df)} candles for {symbol}")
            return df

        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} DATA_DEMO: Failed to generate demo data: {e}")
            return None

    def _convert_klines_to_dataframe(self, raw_klines: List) -> pd.DataFrame:
        """Convert raw klines to DataFrame."""
        if not raw_klines:
            return pd.DataFrame()

        df = pd.DataFrame(raw_klines)

        # Handle different response formats
        if len(df.columns) >= 12:
            df.columns = [
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ]
        elif len(df.columns) >= 6:
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        else:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_CONVERT: Unexpected klines format: {len(df.columns)} columns")
            return pd.DataFrame()

        # Keep only needed columns
        keep_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        df = df[[col for col in keep_cols if col in df.columns]].copy()

        # Convert to numeric
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Set index
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        df.sort_index(inplace=True)

        return df

    def _interval_to_minutes(self, interval: str) -> int:
        """Convert interval string to minutes."""
        interval_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360,
            '8h': 480, '12h': 720, '1d': 1440, '3d': 4320, '1w': 10080
        }
        return interval_map.get(interval, 5)

    def _get_base_price_for_symbol(self, symbol: str) -> float:
        """Get base price for demo data generation."""
        base_prices = {
            'BTCUSDT': 45000.0,
            'ETHUSDT': 3000.0,
            'BNBUSDT': 600.0,
            'SOLUSDT': 120.0,
            'XRPUSDT': 0.60,
            'ADAUSDT': 0.40,
            'DOGEUSDT': 0.08,
            'AVAXUSDT': 40.0,
            'DOTUSDT': 8.0,
            'TRXUSDT': 0.08,
            'BCHUSDT': 300.0,
            'LTCUSDT': 80.0,
            'UNIUSDT': 8.0,
            'NEARUSDT': 4.0,
            'ETCUSDT': 25.0,
            'XLMUSDT': 0.12,
            'APTUSDT': 10.0,
            'SUIUSDT': 2.0,
            'IMXUSDT': 2.0,
            'FILUSDT': 5.0,
            'ATOMUSDT': 10.0,
            'VETUSDT': 0.02,
        }
        return base_prices.get(symbol, 100.0)

    def fetch_multiple_timeframes(self, symbol: str, intervals: List[str], limit: int,
                                   heikin_ashi: bool = False) -> Dict[str, pd.DataFrame]:
        """
        Fetch multiple timeframes for a symbol.
        """
        results = {}

        for interval in intervals:
            df = self.fetch_klines(symbol, interval, limit, heikin_ashi=heikin_ashi)
            if df is not None and not df.empty:
                results[interval] = df

        return results

    def fetch_multiple_symbols(self, symbols: List[str], interval: str, limit: int,
                               heikin_ashi: bool = False) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple symbols in parallel.
        """
        log_data_operation("FETCH_MULTIPLE", "START",
                          {"symbols": len(symbols), "interval": interval, "heikin_ashi": heikin_ashi},
                          emoji=EMOJI['THREAD'])

        results = {}
        failed_symbols = []

        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=min(len(symbols), 10)) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_klines, symbol, interval, limit, True, False, heikin_ashi): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result(timeout=30)
                    if result is not None and not result.empty:
                        results[symbol] = result
                    else:
                        failed_symbols.append(symbol)
                except Exception as e:
                    data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Failed to fetch {symbol}: {e}")
                    failed_symbols.append(symbol)

        if failed_symbols:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_FETCH: Failed to fetch {len(failed_symbols)} symbols: {failed_symbols[:5]}...")

        log_data_operation("FETCH_MULTIPLE", "SUCCESS",
                          {"fetched": len(results), "failed": len(failed_symbols)},
                          emoji=EMOJI['SUCCESS'])

        return results

    def start_websocket(self, symbols: List[str], callback: callable, stream_type: str = 'kline_1m'):
        """
        Start WebSocket connection for real-time data.
        """
        log_data_operation("WEBSOCKET", "START",
                          {"symbols": len(symbols), "stream_type": stream_type},
                          emoji=EMOJI['WEBSOCKET'])

        if self.demo_mode:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_WEBSOCKET: WebSocket not available in demo mode")
            return

        if not BINANCE_AVAILABLE or BinanceSocketManager is None:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_WEBSOCKET: Binance WebSocket library not available")
            return

        if not self.client:
            data_logger.warning(f"{EMOJI['WARNING']} DATA_WEBSOCKET: Binance client not initialized")
            return

        try:
            from binance.websockets import BinanceSocketManager
            self.ws_manager = BinanceSocketManager(self.client)
            interval = stream_type.replace('kline_', '')

            for symbol in symbols:
                self.ws_manager.start_kline_socket(
                    symbol.lower(),
                    callback,
                    interval=interval
                )
                data_logger.debug(f"{EMOJI['WEBSOCKET']} DATA_WEBSOCKET: Started stream for {symbol}")

            self.ws_running = True
            data_logger.info(f"{EMOJI['SUCCESS']} DATA_WEBSOCKET: WebSocket connected for {len(symbols)} symbols")

        except Exception as e:
            log_data_operation("WEBSOCKET", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            data_logger.error(f"{EMOJI['ERROR']} DATA_WEBSOCKET: Failed to start WebSocket: {e}")

    def stop_websocket(self):
        """Stop WebSocket connection."""
        if self.ws_manager and self.ws_running:
            try:
                self.ws_manager.stop()
                self.ws_running = False
                data_logger.info(f"{EMOJI['SUCCESS']} DATA_WEBSOCKET: WebSocket stopped")
            except Exception as e:
                data_logger.error(f"{EMOJI['ERROR']} DATA_WEBSOCKET: Failed to stop WebSocket: {e}")

    def get_exchange_info(self) -> Dict[str, Any]:
        """Get exchange information."""
        if self.demo_mode or not self.client:
            return {"status": "demo_mode", "symbols": len(config.market.symbols)}

        try:
            info = self.client.get_exchange_info()
            return info
        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Failed to get exchange info: {e}")
            return {}

    def get_server_time(self) -> Optional[datetime]:
        """Get server time from Binance."""
        if self.demo_mode or not self.client:
            return datetime.now()

        try:
            time_data = self.client.get_server_time()
            return datetime.fromtimestamp(time_data['serverTime'] / 1000)
        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Failed to get server time: {e}")
            return None

    def get_metrics(self) -> Dict[str, Any]:
        """Get data fetcher metrics."""
        return {
            **self.metrics,
            "cache_stats": self.cache.get_stats(),
            "version": self.CACHE_VERSION,
            "demo_mode": self.demo_mode,
            "production_mode": self.is_production_mode,
            "binance_available": BINANCE_AVAILABLE,
            "binance_um_available": BINANCE_UM_AVAILABLE,
            "client_connected": self.client is not None or self.um_client is not None,
            "success_rate": (
                self.metrics["successful_requests"] / self.metrics["total_requests"]
                if self.metrics["total_requests"] > 0 else 0
            ),
            "avg_response_time": (
                self.metrics["total_time"] / self.metrics["successful_requests"]
                if self.metrics["successful_requests"] > 0 else 0
            )
        }

    def cleanup(self):
        """Clean up resources."""
        data_logger.info(f"{EMOJI['INFO']} DATA_CLEANUP: Cleaning up resources")
        self.stop_websocket()
        self.cache.clear()
        self.executor.shutdown(wait=True)
        data_logger.info(f"{EMOJI['SUCCESS']} DATA_CLEANUP: Cleanup complete")

    def __del__(self):
        try:
            self.cleanup()
        except:
            pass


def create_data_fetcher(demo_mode: Optional[bool] = None) -> DataFetcher:
    """Factory function to create DataFetcher instance."""
    return DataFetcher(demo_mode=demo_mode)


# Create singleton instance
data_fetcher = create_data_fetcher()

__all__ = [
    "data_fetcher",
    "DataFetcher",
    "create_data_fetcher",
    "CacheManager",
    "RateLimiter",
    "calculate_heikin_ashi",
]
