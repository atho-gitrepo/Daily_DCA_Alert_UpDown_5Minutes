"""
Market data fetcher for Binance cryptocurrency exchange - SUPER TDI + SUPER BB STRATEGY.
Simplified for Super TDI + Super Bollinger Bands strategy with multi-timeframe support.
Version: 3.4.0 - ALIGNED: Super TDI + Super BB strategy
"""

import pandas as pd
import numpy as np
import logging
import time
import hashlib
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

# Local imports
from settings import config

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

# Binance imports - try both new and old
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


# ------------------- Simple Cache Manager -------------------

class CacheManager:
    """
    Simple in-memory caching manager.
    """

    def __init__(self, enabled: bool = True, ttl_seconds: int = 60, max_size: int = 500):
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache = {}
        self._timestamps = {}
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None

        if key in self._cache:
            if time.time() - self._timestamps[key] < self.ttl_seconds:
                self._hit_count += 1
                return self._cache[key]
            else:
                del self._cache[key]
                del self._timestamps[key]

        self._miss_count += 1
        return None

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return

        if len(self._cache) >= self.max_size:
            oldest_key = min(self._timestamps, key=self._timestamps.get)
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]

        self._cache[key] = value
        self._timestamps[key] = time.time()

    def clear(self) -> None:
        self._cache.clear()
        self._timestamps.clear()
        self._hit_count = 0
        self._miss_count = 0

    def get_stats(self) -> Dict[str, int]:
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0
        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "total": total,
            "hit_rate": f"{hit_rate:.2%}",
            "size": len(self._cache),
        }


# ------------------- Data Fetcher -------------------

class DataFetcher:
    """
    Handles connection to Binance and fetches market data.
    Simplified for Super TDI + Super Bollinger Bands strategy.
    """

    # Required columns
    REQUIRED_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

    # Version
    CACHE_VERSION = "3.4.0"

    def __init__(self, demo_mode: Optional[bool] = None):
        data_logger.info(f"{EMOJI['START']} DATA_INIT: Starting DataFetcher v{self.CACHE_VERSION}")

        # Determine demo mode
        run_mode = os.getenv("RUN_MODE", "DEMO").upper().strip()
        is_production_mode = run_mode == "PRODUCTION"

        if demo_mode is not None:
            self.demo_mode = demo_mode
        elif is_production_mode:
            self.demo_mode = False
            data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: PRODUCTION MODE - using REAL data")
        else:
            self.demo_mode = config.is_demo() if hasattr(config, 'is_demo') else True

        self.is_production_mode = is_production_mode and not self.demo_mode

        # Initialize cache
        self.cache = CacheManager(
            enabled=getattr(config.performance, 'cache_enabled', True),
            ttl_seconds=60 if self.is_production_mode else getattr(config.performance, 'cache_ttl_seconds', 300),
            max_size=getattr(config.performance, 'cache_max_size', 500)
        )

        # Initialize Binance client
        self.client = None
        self.um_client = None
        self._init_binance_client()

        # Metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "demo_mode": self.demo_mode,
            "production_mode": self.is_production_mode,
            "version": self.CACHE_VERSION,
        }

        mode_label = "🔴 PRODUCTION" if self.is_production_mode else "🎮 DEMO"
        data_logger.info(f"{EMOJI['SUCCESS']} DATA_INIT: DataFetcher ready ({mode_label})")

    def _init_binance_client(self):
        """Initialize Binance client."""
        if self.is_production_mode:
            data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: Initializing Binance client for PRODUCTION...")

        # Try UMFutures first
        if BINANCE_UM_AVAILABLE:
            try:
                api_key = config.binance.api_key if hasattr(config, 'binance') else os.getenv("BINANCE_API_KEY", "")
                api_secret = config.binance.api_secret if hasattr(config, 'binance') else os.getenv("BINANCE_API_SECRET", "")
                testnet = config.binance.testnet if hasattr(config, 'binance') else True
                base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"

                if api_key and api_secret:
                    self.um_client = UMFutures(key=api_key, secret=api_secret, base_url=base_url)
                else:
                    if self.is_production_mode:
                        data_logger.error(f"{EMOJI['PRODUCTION']} DATA_INIT: No API credentials for PRODUCTION!")
                    self.um_client = UMFutures(base_url=base_url)

                self.um_client.time()
                data_logger.info(f"{EMOJI['SUCCESS']} DATA_INIT: Binance UMFutures client initialized")

                if self.is_production_mode:
                    data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: PRODUCTION client ready")
                    return

            except Exception as e:
                data_logger.warning(f"{EMOJI['WARNING']} DATA_INIT: UMFutures init failed: {e}")

        # Fallback to legacy client
        if not self.um_client and BINANCE_AVAILABLE:
            try:
                api_key = config.binance.api_key if hasattr(config, 'binance') else os.getenv("BINANCE_API_KEY", "")
                api_secret = config.binance.api_secret if hasattr(config, 'binance') else os.getenv("BINANCE_API_SECRET", "")
                testnet = config.binance.testnet if hasattr(config, 'binance') else True

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
                    requests_params={'timeout': 30}
                )

                self.client.ping()
                data_logger.info(f"{EMOJI['SUCCESS']} DATA_INIT: Binance client initialized (testnet: {testnet})")

                if self.is_production_mode:
                    data_logger.info(f"{EMOJI['PRODUCTION']} DATA_INIT: PRODUCTION client ready")

            except Exception as e:
                data_logger.error(f"{EMOJI['ERROR']} DATA_INIT: Failed to initialize Binance client: {e}")
                if self.is_production_mode:
                    raise
                self.demo_mode = True
        else:
            if self.is_production_mode:
                data_logger.error(f"{EMOJI['ERROR']} DATA_INIT: No Binance library available for PRODUCTION!")
                raise RuntimeError("Cannot run in PRODUCTION mode without Binance library")
            data_logger.warning(f"{EMOJI['WARNING']} DATA_INIT: Binance library not available. Running in DEMO mode.")
            self.demo_mode = True

    def _is_demo_mode(self) -> bool:
        """Check if running in demo mode."""
        return self.demo_mode or not (self.client or self.um_client)

    def _generate_cache_key(self, symbol: str, interval: str, limit: int) -> str:
        """Generate cache key."""
        key_data = f"{self.CACHE_VERSION}_{symbol}_{interval}_{limit}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def fetch_klines(self, symbol: str, interval: str = '5m', limit: int = 200,
                     heikin_ashi: bool = True) -> Optional[pd.DataFrame]:
        """
        Fetches historical kline data with caching.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)
            limit: Number of candles to fetch
            heikin_ashi: Whether to calculate Heikin Ashi candles

        Returns:
            DataFrame with OHLCV data, or None if fetch failed
        """
        start_time = time.time()
        cache_key = self._generate_cache_key(symbol, interval, limit)

        data_logger.debug(f"{EMOJI['FETCH']} DATA_FETCH: Fetching {symbol} {interval} (limit: {limit})")

        # Check cache
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            self.metrics["cache_hits"] += 1
            data_logger.debug(f"{EMOJI['CACHE']} DATA_FETCH: Cache hit for {symbol}")
            return cached_data

        self.metrics["cache_misses"] += 1

        try:
            # Fetch data
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

            # Calculate Heikin Ashi
            if heikin_ashi:
                df = calculate_heikin_ashi(df)

            # Cache
            self.cache.set(cache_key, df)

            elapsed_time = time.time() - start_time
            self.metrics["successful_requests"] += 1
            self.metrics["total_time"] += elapsed_time

            data_logger.debug(f"{EMOJI['SUCCESS']} DATA_FETCH: Fetched {len(df)} candles for {symbol} ({elapsed_time*1000:.0f}ms)")

            return df

        except Exception as e:
            self.metrics["failed_requests"] += 1
            data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Failed to fetch {symbol}: {e}")
            if self.is_production_mode:
                raise
            return None
        finally:
            self.metrics["total_requests"] += 1

    def _fetch_live_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Fetch live klines from Binance API."""
        if not (self.client or self.um_client):
            return None

        max_retries = 3 if self.is_production_mode else 2

        for attempt in range(max_retries):
            try:
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
                    return None

                return self._convert_klines_to_dataframe(raw_klines)

            except Exception as e:
                if "API-key" in str(e) or "Invalid" in str(e):
                    data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: API key error for {symbol}")
                    if self.is_production_mode:
                        raise
                    self.client = None
                    self.um_client = None
                    return None

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    data_logger.debug(f"{EMOJI['RETRY']} DATA_FETCH: Retry {attempt+1}/{max_retries} for {symbol} in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    data_logger.error(f"{EMOJI['ERROR']} DATA_FETCH: Max retries for {symbol}: {e}")
                    if self.is_production_mode:
                        raise
                    return None

        return None

    def _fetch_demo_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Generate synthetic demo data."""
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

            # Generate price data
            returns = np.random.normal(0.0002, 0.01, limit)
            if np.random.random() > 0.6:
                trend = np.random.uniform(0.001, 0.003) * np.random.choice([-1, 1])
                returns += trend * np.linspace(0, 1, limit)

            price = base_price * np.exp(np.cumsum(returns))
            volatility = 0.015 * (1 + 0.5 * np.random.random())

            df = pd.DataFrame({
                'open': price * (1 + np.random.uniform(-volatility, volatility, limit)),
                'high': price * (1 + np.abs(np.random.uniform(0, volatility * 1.5, limit))),
                'low': price * (1 - np.abs(np.random.uniform(0, volatility * 1.5, limit))),
                'close': price,
                'volume': np.random.exponential(100, limit) * base_price / 10000
            }, index=timestamps)

            df['high'] = df[['open', 'high', 'close']].max(axis=1)
            df['low'] = df[['open', 'low', 'close']].min(axis=1)

            data_logger.debug(f"{EMOJI['DEMO']} DATA_DEMO: Generated {len(df)} candles for {symbol}")
            return df

        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} DATA_DEMO: Failed to generate demo data: {e}")
            return None

    def _convert_klines_to_dataframe(self, raw_klines: List) -> pd.DataFrame:
        """Convert raw klines to DataFrame."""
        if not raw_klines:
            return pd.DataFrame()

        df = pd.DataFrame(raw_klines)

        if len(df.columns) >= 12:
            df.columns = [
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ]
        elif len(df.columns) >= 6:
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        else:
            return pd.DataFrame()

        keep_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        df = df[[col for col in keep_cols if col in df.columns]].copy()

        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'open_time' in df.columns:
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
        """Get base price for demo data."""
        base_prices = {
            'BTCUSDT': 65000.0,
            'ETHUSDT': 3500.0,
            'BNBUSDT': 600.0,
            'SOLUSDT': 150.0,
            'XRPUSDT': 0.60,
            'ADAUSDT': 0.40,
            'DOGEUSDT': 0.12,
            'AVAXUSDT': 40.0,
            'DOTUSDT': 7.0,
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

    def fetch_multiple_timeframes(self, symbol: str, intervals: List[str],
                                  limit: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetch multiple timeframes for a symbol."""
        results = {}
        for interval in intervals:
            df = self.fetch_klines(symbol, interval, limit, heikin_ashi=True)
            if df is not None and not df.empty:
                results[interval] = df
        return results

    def fetch_multiple_symbols(self, symbols: List[str], interval: str = '5m',
                               limit: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols in parallel."""
        results = {}
        failed_symbols = []

        with ThreadPoolExecutor(max_workers=min(len(symbols), 5)) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_klines, symbol, interval, limit): symbol
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
            data_logger.warning(f"{EMOJI['WARNING']} DATA_FETCH: Failed {len(failed_symbols)} symbols")

        return results

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price."""
        if self._is_demo_mode() or not (self.client or self.um_client):
            return self._get_demo_price(symbol)

        try:
            if self.um_client:
                ticker = self.um_client.ticker_price(symbol=symbol)
            elif self.client:
                ticker = self.client.get_symbol_ticker(symbol=symbol)
            else:
                return None
            return float(ticker['price'])
        except Exception as e:
            data_logger.debug(f"Price fetch error for {symbol}: {e}")
            return None

    def _get_demo_price(self, symbol: str) -> float:
        """Get demo price."""
        base_price = self._get_base_price_for_symbol(symbol)
        variation = 1 + np.random.normal(0, 0.001)
        return base_price * variation

    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics."""
        return {
            **self.metrics,
            "cache_stats": self.cache.get_stats(),
            "demo_mode": self.demo_mode,
            "production_mode": self.is_production_mode,
            "client_connected": self.client is not None or self.um_client is not None,
        }

    def cleanup(self):
        """Clean up resources."""
        data_logger.info(f"{EMOJI['INFO']} DATA_CLEANUP: Cleaning up resources")
        self.cache.clear()
        data_logger.info(f"{EMOJI['SUCCESS']} DATA_CLEANUP: Cleanup complete")

    def __del__(self):
        try:
            self.cleanup()
        except:
            pass


# Create singleton instance
data_fetcher = DataFetcher()

__all__ = [
    "data_fetcher",
    "DataFetcher",
    "CacheManager",
    "calculate_heikin_ashi",
]
