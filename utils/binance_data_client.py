#!/usr/bin/env python3
"""
Binance Data Client - Simple market data fetching
Version: 3.4.6 - FIXED: Simplified, clean code, proper fallbacks
"""

import pandas as pd
import numpy as np
import logging
import time
from typing import Optional, Dict, List, Any
from datetime import datetime
import threading

from settings import config

logging.basicConfig(
    level=getattr(logging, 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try imports
try:
    from binance.um_futures import UMFutures
    HAS_FUTURES = True
except ImportError:
    HAS_FUTURES = False

try:
    from binance.client import Client as BinanceSpotClient
    HAS_SPOT = True
except ImportError:
    HAS_SPOT = False


# ========== HEIKIN ASHI ==========
def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Heikin Ashi candles."""
    if df is None or df.empty or len(df) < 2:
        return df
    
    df = df.copy()
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df.loc[df.index[0], 'ha_open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)
    df['ha_color'] = np.where(df['ha_close'] > df['ha_open'], 1, -1)
    return df


# ========== BINANCE CLIENT ==========
class BinanceDataClient:
    def __init__(self):
        self.api_key = config.binance.api_key
        self.api_secret = config.binance.api_secret
        self.is_testnet = config.binance.testnet
        
        self.futures_client = None
        self.spot_client = None
        self.client_type = "None"
        
        self._init_client()
        
        # Symbol info
        self.price_precisions: Dict[str, int] = {}
        self._load_symbol_info()
        
        # Simple cache
        self.cache = {}
        self.cache_ttl = 60  # 1 minute
        
        logger.info(f"✅ BinanceDataClient initialized. Type: {self.client_type}, Testnet: {self.is_testnet}")
    
    def _init_client(self):
        """Initialize client with fallback."""
        base_url = "https://testnet.binancefuture.com" if self.is_testnet else "https://fapi.binance.com"
        
        # Try futures
        if HAS_FUTURES:
            try:
                if self.api_key and self.api_secret:
                    self.futures_client = UMFutures(
                        key=self.api_key,
                        secret=self.api_secret,
                        base_url=base_url,
                        requests_params={'timeout': 10}
                    )
                else:
                    self.futures_client = UMFutures(
                        base_url=base_url,
                        requests_params={'timeout': 10}
                    )
                self.client_type = "Futures"
                logger.info("✅ Binance Futures client initialized")
                return
            except Exception as e:
                logger.warning(f"Futures init failed: {e}")
        
        # Try spot
        if HAS_SPOT:
            try:
                if self.api_key and self.api_secret:
                    self.spot_client = BinanceSpotClient(
                        api_key=self.api_key,
                        api_secret=self.api_secret,
                        testnet=self.is_testnet,
                        requests_params={'timeout': 10}
                    )
                else:
                    self.spot_client = BinanceSpotClient(
                        requests_params={'timeout': 10}
                    )
                self.client_type = "Spot"
                logger.info("✅ Binance Spot client initialized")
                return
            except Exception as e:
                logger.warning(f"Spot init failed: {e}")
        
        self.client_type = "None"
        logger.warning("⚠️ No Binance client available")
    
    def _load_symbol_info(self):
        """Load price precisions for symbols."""
        symbols = [s for s in config.market.symbols if s.endswith(config.market.quote_asset)]
        
        for symbol in symbols:
            self.price_precisions[symbol] = 2
        
        # Try to get actual precision
        try:
            client = self.futures_client or self.spot_client
            if not client:
                return
            
            try:
                if hasattr(client, 'exchange_info'):
                    info = client.exchange_info()
                elif hasattr(client, 'get_exchange_info'):
                    info = client.get_exchange_info()
                else:
                    return
            except:
                return
            
            for symbol in symbols:
                symbol_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
                if symbol_info:
                    price_filter = next(
                        (f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'),
                        None
                    )
                    if price_filter:
                        tick_size = float(price_filter['tickSize'])
                        self.price_precisions[symbol] = len(str(tick_size).split('.')[-1].rstrip('0'))
        except Exception as e:
            logger.debug(f"Could not load symbol info: {e}")
    
    def round_price(self, price: float, symbol: str) -> float:
        precision = self.price_precisions.get(symbol, 2)
        return round(price, precision)
    
    def get_historical_klines(self, symbol: str, interval: str, 
                             limit: int = 200, heikin_ashi: bool = False) -> pd.DataFrame:
        """Fetch klines with caching and timeout."""
        cache_key = f"{symbol}_{interval}_{limit}_{heikin_ashi}"
        
        # Check cache
        if cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if time.time() - cache_time < self.cache_ttl:
                return data.copy()
        
        try:
            client = self.futures_client or self.spot_client
            if not client:
                return pd.DataFrame()
            
            # Get klines
            try:
                if hasattr(client, 'klines'):
                    klines = client.klines(symbol=symbol, interval=interval, limit=limit)
                elif hasattr(client, 'get_klines'):
                    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
                else:
                    return pd.DataFrame()
            except Exception as e:
                logger.error(f"Klines error for {symbol}: {e}")
                return pd.DataFrame()
            
            if not klines:
                return pd.DataFrame()
            
            # Convert to DataFrame
            if len(klines[0]) >= 12:
                df = pd.DataFrame(klines, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
            else:
                df = pd.DataFrame(klines, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume'
                ])
            
            # Keep only needed columns
            keep_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
            df = df[[c for c in keep_cols if c in df.columns]].copy()
            
            # Convert to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Set index
            if 'open_time' in df.columns:
                df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                df.set_index('open_time', inplace=True)
            
            # Heikin Ashi
            if heikin_ashi and not df.empty:
                df = calculate_heikin_ashi(df)
            
            # Cache
            if not df.empty:
                self.cache[cache_key] = (time.time(), df.copy())
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return pd.DataFrame()
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price with caching."""
        cache_key = f"price_{symbol}"
        
        # Check cache (5 second TTL)
        if cache_key in self.cache:
            cache_time, price = self.cache[cache_key]
            if time.time() - cache_time < 5:
                return price
        
        try:
            client = self.futures_client or self.spot_client
            if not client:
                return None
            
            if hasattr(client, 'ticker_price'):
                ticker = client.ticker_price(symbol=symbol)
            elif hasattr(client, 'get_symbol_ticker'):
                ticker = client.get_symbol_ticker(symbol=symbol)
            else:
                return None
            
            price = float(ticker['price'])
            self.cache[cache_key] = (time.time(), price)
            return price
            
        except Exception as e:
            logger.debug(f"Price error for {symbol}: {e}")
            return None
    
    def fetch_multiple_timeframes(self, symbol: str, timeframes: List[str], 
                                  limit: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetch multiple timeframes."""
        result = {}
        for tf in timeframes:
            df = self.get_historical_klines(symbol, tf, limit)
            if not df.empty:
                result[tf] = df
            time.sleep(0.05)  # Small delay between requests
        return result
    
    def get_connection_status(self) -> Dict:
        return {
            'client_type': self.client_type,
            'testnet': self.is_testnet,
            'cache_size': len(self.cache),
        }
    
    def clear_cache(self):
        self.cache.clear()
        logger.debug("Cache cleared")
    
    def cleanup(self):
        self.clear_cache()
        logger.info("Client cleaned up")


# ========== SINGLETON ==========
binance_client = BinanceDataClient()

__all__ = ['binance_client', 'BinanceDataClient', 'calculate_heikin_ashi']
