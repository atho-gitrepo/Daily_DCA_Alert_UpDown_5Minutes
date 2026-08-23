#!/usr/bin/env python3
"""
AI Trading Bot v3.4.0 - Main Entry Point
Compact version with all improvements integrated.
"""

import os
import sys
import time
import logging
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ========== IMPORTS - CORRECTED FOR PROJECT STRUCTURE ==========

# Settings
try:
    from settings import config
except ImportError:
    # Fallback: try relative import
    try:
        from .settings import config
    except ImportError:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from settings import config

# Data Fetcher - FROM utils/data_fetcher.py
try:
    from utils.data_fetcher import data_fetcher
except ImportError:
    try:
        from data_fetcher import data_fetcher
    except ImportError:
        data_fetcher = None
        print("WARNING: data_fetcher not available - using fallback")

# Strategy v3.4.0
try:
    from strategy.signal_engine_v34 import signal_engine, SignalEngineV34
    from strategy.signal_state import SignalStateMachine, SignalState, SetupData, TriggerData
    from strategy.htf_regime import htf_regime, Regime, RegimeData
    from strategy.structure import structure_analyzer, MarketStructureAnalyzer, StructureData
    V34_AVAILABLE = True
    print("✅ v3.4.0 strategy loaded")
except ImportError as e:
    print(f"⚠️ v3.4.0 strategy not available: {e}")
    V34_AVAILABLE = False
    signal_engine = None
    SignalEngineV34 = None
    SignalStateMachine = None
    SignalState = None
    SetupData = None
    TriggerData = None
    htf_regime = None
    Regime = None
    RegimeData = None
    structure_analyzer = None
    MarketStructureAnalyzer = None
    StructureData = None

# Signal Manager
try:
    from utils.signal_manager import signal_manager, SignalData, TradeLifecycle
except ImportError:
    try:
        from signal_manager import signal_manager, SignalData, TradeLifecycle
    except ImportError:
        signal_manager = None
        SignalData = None
        TradeLifecycle = None
        print("WARNING: signal_manager not available")

# Telegram
try:
    from utils.telegram_bot import telegram_bot, send_telegram_message_sync
except ImportError:
    try:
        from telegram_bot import telegram_bot, send_telegram_message_sync
    except ImportError:
        telegram_bot = None
        send_telegram_message_sync = None
        print("WARNING: telegram_bot not available")

# MongoDB
try:
    from utils.mongodb_client import mongodb_client
except ImportError:
    try:
        from mongodb_client import mongodb_client
    except ImportError:
        mongodb_client = None
        print("WARNING: mongodb_client not available")

# Indicators
try:
    from utils.indicators import Indicators, calculate_heikin_ashi, get_trading_session
except ImportError:
    try:
        from indicators import Indicators, calculate_heikin_ashi, get_trading_session
    except ImportError:
        Indicators = None
        calculate_heikin_ashi = None
        get_trading_session = None
        print("WARNING: indicators not available")

# Pandas
try:
    import pandas as pd
except ImportError:
    pd = None
    print("WARNING: pandas not available")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Emoji indicators
EMOJI = {
    "START": "🚀", "STOP": "🛑", "SUCCESS": "✅", "ERROR": "❌",
    "WARNING": "⚠️", "INFO": "ℹ️", "SIGNAL": "📡", "HEALTH": "💚",
    "AI": "🤖", "DB": "💾", "TELEGRAM": "📨", "SYNC": "🔄",
    "PROFIT": "💰", "LOSS": "💸", "REJECT": "🚫", "WAIT": "⏳",
    "LOCK": "🔒", "UNLOCK": "🔓", "MONITOR": "📊", "RESULT": "📈",
    "LTF": "⏱️", "HTF": "📊", "SCORE": "🎯", "GRADE_A": "🏆",
    "GRADE_B": "🥈", "GRADE_C": "🥉", "DIVERGENCE": "↩️",
    "PATTERN": "🕯️", "S_R": "📊", "SESSION": "🌍", "STRUCTURE": "🏗️",
    "REGIME": "📈", "STATE": "🔄", "V34": "⚡", "FETCH": "📊",
}

# Global state
running = True
bot_stats = {
    'status': 'initializing',
    'start_time': datetime.now().isoformat(),
    'signals_generated': 0,
    'active_signals': 0,
    'errors': 0,
    'version': '3.4.0',
    'features': {
        'htf_regime': True,
        'structure_analysis': True,
        'signal_state_machine': True,
        'entry_distance_protection': True,
        'atr_risk_model': True,
    },
    'v34_available': V34_AVAILABLE,
}


# ========== DATA FETCHER WRAPPER ==========

class DataFetcherWrapper:
    """Wrapper for data_fetcher with fallback to direct Binance client."""

    def __init__(self):
        self._fetcher = data_fetcher
        self._binance_client = None
        self._init_binance_client()

        if self._fetcher is not None:
            logger.info(f"{EMOJI['SUCCESS']} Data fetcher loaded from utils.data_fetcher")
        else:
            logger.warning(f"{EMOJI['WARNING']} Data fetcher not available")

    def _init_binance_client(self):
        """Initialize direct Binance client as fallback."""
        try:
            from binance.um_futures import UMFutures

            api_key = getattr(config.binance, 'api_key', '')
            api_secret = getattr(config.binance, 'api_secret', '')
            use_testnet = getattr(config.binance, 'use_testnet', True)
            base_url = "https://testnet.binancefuture.com" if use_testnet else "https://fapi.binance.com"

            if api_key and api_secret:
                self._binance_client = UMFutures(key=api_key, secret=api_secret, base_url=base_url)
            else:
                self._binance_client = UMFutures(base_url=base_url)
            logger.info(f"{EMOJI['SUCCESS']} Binance fallback client created")
        except ImportError:
            logger.debug("binance.um_futures not available")
        except Exception as e:
            logger.debug(f"Binance client init error: {e}")

    def fetch_klines(self, symbol: str, interval: str = '15m', limit: int = 200):
        """Fetch klines data."""
        # Try primary fetcher first
        if self._fetcher is not None:
            try:
                if hasattr(self._fetcher, 'fetch_klines'):
                    df = self._fetcher.fetch_klines(symbol, interval, limit)
                    if df is not None and not df.empty:
                        return df
            except Exception as e:
                logger.debug(f"Primary fetcher error: {e}")

        # Try fallback Binance client
        if self._binance_client is not None:
            try:
                klines = self._binance_client.klines(symbol=symbol, interval=interval, limit=limit)
                if klines:
                    return self._convert_klines(klines)
            except Exception as e:
                logger.debug(f"Binance fallback error: {e}")

        # Try using data_fetcher's demo mode
        if self._fetcher is not None:
            try:
                if hasattr(self._fetcher, '_fetch_demo_klines'):
                    df = self._fetcher._fetch_demo_klines(symbol, interval, limit)
                    if df is not None and not df.empty:
                        return df
            except Exception as e:
                logger.debug(f"Demo fetch error: {e}")

        return None

    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current price."""
        # Try primary fetcher
        if self._fetcher is not None:
            try:
                if hasattr(self._fetcher, 'client') and self._fetcher.client is not None:
                    ticker = self._fetcher.client.get_symbol_ticker(symbol=symbol)
                    if ticker:
                        return float(ticker['price'])
            except Exception as e:
                logger.debug(f"Primary price fetch error: {e}")

        # Try fallback client
        if self._binance_client is not None:
            try:
                ticker = self._binance_client.ticker_price(symbol=symbol)
                return float(ticker['price'])
            except Exception as e:
                logger.debug(f"Binance fallback price error: {e}")

        return None

    def _convert_klines(self, raw_klines: List) -> Optional[pd.DataFrame]:
        """Convert raw klines to DataFrame."""
        if pd is None:
            return None

        if not raw_klines:
            return None

        df = pd.DataFrame(raw_klines)
        if len(df.columns) >= 6:
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])

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


# Create singleton
data_client = DataFetcherWrapper()


# ========== MAIN PROCESSING FUNCTIONS ==========

def fetch_data(symbol: str, timeframe: str = '15m') -> Optional[pd.DataFrame]:
    """Fetch historical data with indicators."""
    if pd is None:
        logger.error(f"{EMOJI['ERROR']} Pandas not available")
        return None

    try:
        df = data_client.fetch_klines(symbol, timeframe, 200)
        if df is None or df.empty:
            return None

        # Calculate all indicators if available
        if Indicators is not None:
            df = Indicators.calculate_all_indicators(df)
        else:
            logger.debug(f"{EMOJI['WARNING']} Indicators not available, using raw data")

        return df

    except Exception as e:
        logger.error(f"Data fetch error for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_htf_data(symbol: str) -> Dict[str, Optional[pd.DataFrame]]:
    """Fetch higher timeframe data."""
    result = {'4h': None, '1h': None}
    try:
        # 4H data
        df_4h = data_client.fetch_klines(symbol, '4h', 50)
        if df_4h is not None and not df_4h.empty:
            result['4h'] = df_4h

        # 1H data
        df_1h = data_client.fetch_klines(symbol, '1h', 50)
        if df_1h is not None and not df_1h.empty:
            result['1h'] = df_1h

        return result
    except Exception as e:
        logger.error(f"HTF data fetch error for {symbol}: {e}")
        return {}


def check_ltf_confirmation(symbol: str, direction: str) -> Dict[str, Any]:
    """Check 5M LTF confirmation."""
    if pd is None:
        return {'confirmed': False, 'confidence': 0, 'reason': 'Pandas not available'}

    try:
        df_5m = data_client.fetch_klines(symbol, '5m', 100)
        if df_5m is None or df_5m.empty:
            return {'confirmed': False, 'confidence': 0, 'reason': 'No data'}

        if Indicators is not None:
            df_5m = Indicators.calculate_tdi(df_5m)
            if calculate_heikin_ashi is not None:
                df_5m = calculate_heikin_ashi(df_5m)
        else:
            return {'confirmed': False, 'confidence': 0, 'reason': 'Indicators not available'}

        last = df_5m.iloc[-1]
        prev = df_5m.iloc[-2] if len(df_5m) > 1 else last

        tdi_fast = last.get('tdi_fast_ma', 50)
        tdi_slow = last.get('tdi_slow_ma', 50)
        tdi_fast_prev = prev.get('tdi_fast_ma', 50)
        tdi_slow_prev = prev.get('tdi_slow_ma', 50)
        ha_color = last.get('ha_color', 0)
        volume_ratio = last.get('volume_ratio', 1.0)

        confidence = 0.5
        confirmed = False

        if direction == 'BUY':
            if tdi_fast > tdi_slow and tdi_fast_prev <= tdi_slow_prev:
                confidence += 0.25
            elif tdi_fast > tdi_slow:
                confidence += 0.10

            if ha_color == 1:
                confidence += 0.10

            if volume_ratio > 1.5:
                confidence += 0.05

            confirmed = confidence >= 0.65

        elif direction == 'SELL':
            if tdi_fast < tdi_slow and tdi_fast_prev >= tdi_slow_prev:
                confidence += 0.25
            elif tdi_fast < tdi_slow:
                confidence += 0.10

            if ha_color == -1:
                confidence += 0.10

            if volume_ratio > 1.5:
                confidence += 0.05

            confirmed = confidence >= 0.65

        return {
            'confirmed': confirmed,
            'confidence': min(0.95, confidence),
            'reason': f'LTF {"confirmed" if confirmed else "not confirmed"} (conf: {confidence:.0%})',
            'direction': direction,
            'tdi_value': tdi_slow
        }

    except Exception as e:
        logger.error(f"LTF check error for {symbol}: {e}")
        return {'confirmed': False, 'confidence': 0, 'reason': f'Error: {e}'}


def process_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Process a single symbol using v3.4.0 engine."""
    if not V34_AVAILABLE:
        logger.warning(f"{EMOJI['WARNING']} v3.4.0 engine not available for {symbol}")
        return None

    if signal_manager is None:
        logger.warning(f"{EMOJI['WARNING']} Signal manager not available for {symbol}")
        return None

    try:
        # Check if symbol is locked
        if signal_manager.is_symbol_locked(symbol):
            return None

        # Fetch data
        df = fetch_data(symbol)
        if df is None:
            return None

        # Fetch HTF data for regime
        htf_data = fetch_htf_data(symbol)
        if htf_data and htf_regime is not None:
            df_4h = htf_data.get('4h')
            df_1h = htf_data.get('1h')
            if df_4h is not None and df_1h is not None:
                htf_regime.analyze(df_4h, df_1h)

        # Get LTF confirmation
        ltf_data = check_ltf_confirmation(symbol, '')  # Direction will be set by engine

        # Process through signal engine
        if signal_engine is None:
            logger.warning(f"{EMOJI['WARNING']} Signal engine not available for {symbol}")
            return None

        result = signal_engine.process(df, ltf_data)

        if result['signal'] != 'NO_TRADE':
            # Generate final signal
            signal_data = result['data']
            signal_data['symbol'] = symbol

            # Get current price
            current_price = data_client.fetch_current_price(symbol)
            if current_price:
                signal_data['entry_price'] = current_price
            elif not df.empty:
                signal_data['entry_price'] = df['close'].iloc[-1]

            # Lock symbol
            if signal_manager.lock_symbol(
                symbol=symbol,
                signal_type=signal_data['direction'],
                entry_price=signal_data.get('entry_price', df['close'].iloc[-1] if not df.empty else 0),
                raw_data=signal_data,
                stop_loss=signal_data.get('stop_loss', 0),
                take_profit=signal_data.get('take_profit', 0),
                confidence=0.85,
                rrr=signal_data.get('rrr', 2.0),
                grade=signal_data.get('grade', 'B'),
                total_score=signal_data.get('final_score', 75),
                signal_strength='SOFT',
                tdi_level=signal_data.get('tdi_level', 50),
                tdi_zone=signal_data.get('tdi_zone', 'NEUTRAL'),
                htf_trend=htf_regime.get_directional_bias() if htf_regime else 'NEUTRAL',
                ltf_confirmed=True,
                ltf_confidence=0.8,
                htf_aligned=True,
                divergence_detected=signal_data.get('divergence_detected', False),
                candle_pattern=signal_data.get('candle_pattern', 'NONE'),
                sr_confirmed=signal_data.get('sr_confirmed', False),
                bb_squeeze=signal_data.get('bb_squeeze', False),
                session=signal_data.get('session', 'UNKNOWN'),
                # v3.4.0 fields
                setup_score=signal_data.get('setup_score', 0),
                trigger_score=signal_data.get('trigger_score', 0),
                final_score=signal_data.get('final_score', 75),
                entry_grade=signal_data.get('grade', 'B'),
                regime=signal_data.get('regime', 'NEUTRAL'),
                structure_direction=signal_data.get('structure_direction', 'NEUTRAL'),
                entry_distance_atr=signal_data.get('entry_distance_atr', 0.0),
                ideal_entry=signal_data.get('ideal_entry', signal_data.get('entry_price', 0)),
                atr=signal_data.get('atr', 0.0),
            ):
                bot_stats['signals_generated'] += 1

                # Send Telegram notification
                if telegram_bot is not None and telegram_bot.enabled:
                    try:
                        telegram_bot.send_signal(
                            symbol=symbol,
                            signal_type=signal_data['direction'],
                            entry_price=signal_data.get('entry_price', 0),
                            stop_loss=signal_data.get('stop_loss', 0),
                            take_profit=signal_data.get('take_profit', 0),
                            confidence=0.85,
                            ai_decision='APPROVE',
                            ai_confidence=0.85,
                            rrr=signal_data.get('rrr', 2.0),
                            total_score=signal_data.get('final_score', 75),
                            grade=signal_data.get('grade', 'B'),
                            signal_strength='SOFT',
                            tdi_level=signal_data.get('tdi_level', 50),
                            tdi_zone=signal_data.get('tdi_zone', 'NEUTRAL'),
                            divergence_detected=signal_data.get('divergence_detected', False),
                            candle_pattern=signal_data.get('candle_pattern', 'NONE'),
                            sr_confirmed=signal_data.get('sr_confirmed', False),
                            bb_squeeze=signal_data.get('bb_squeeze', False),
                            session=signal_data.get('session', 'UNKNOWN'),
                        )
                    except Exception as e:
                        logger.warning(f"Telegram error for {symbol}: {e}")

                logger.info(f"{EMOJI['SIGNAL']} {signal_data['direction']} {symbol} @ {signal_data.get('entry_price', 0):.4f} (Grade: {signal_data.get('grade', 'B')})")
                return signal_data

        return None

    except Exception as e:
        logger.error(f"Process error for {symbol}: {e}")
        bot_stats['errors'] += 1
        import traceback
        traceback.print_exc()
        return None


def check_active_signals():
    """Check and update active signals."""
    if signal_manager is None:
        return

    active = signal_manager.get_all_active_signals()
    bot_stats['active_signals'] = len(active)

    # Monitor each active signal
    for symbol, signal in active.items():
        try:
            current_price = data_client.fetch_current_price(symbol)
            if current_price is None:
                continue

            # Check signal
            status, diff, updated = signal_manager.check_active_signal(
                symbol, current_price, {}
            )

            if status != "ACTIVE" and updated:
                logger.info(f"{EMOJI['RESULT']} {symbol}: {status} | PnL: ${updated.pnl:.2f}")

        except Exception as e:
            logger.error(f"Active signal check error for {symbol}: {e}")


# ========== HEALTH SERVER ==========

def run_health_server():
    """Run health check server."""
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                status_data = {
                    'status': 'running' if running else 'stopped',
                    'version': '3.4.0',
                    'timestamp': datetime.now().isoformat(),
                    'stats': bot_stats,
                    'active_signals': len(signal_manager.active_signals) if signal_manager else 0,
                    'v34_available': V34_AVAILABLE,
                    'features': bot_stats['features']
                }
                self.wfile.write(json.dumps(status_data, indent=2).encode())
            else:
                self.send_response(404)
                self.end_headers()

    try:
        port = getattr(config.deployment, 'port', 8080) if hasattr(config, 'deployment') else 8080
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"{EMOJI['HEALTH']} Health server running on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    global running
    logger.info(f"{EMOJI['STOP']} Shutting down...")
    running = False


# ========== MAIN ==========

def main():
    """Main entry point."""
    global running

    logger.info("=" * 70)
    logger.info(f"{EMOJI['START']} AI TRADING BOT v3.4.0")
    logger.info("=" * 70)
    logger.info(f"{EMOJI['V34']} Features:")
    logger.info("  - HTF Regime System (4H/1H)")
    logger.info("  - Setup ≠ Signal (state machine)")
    logger.info("  - Market Structure (BOS/CHoCH/Sweep)")
    logger.info("  - TDI Cross + Slope (not zone alone)")
    logger.info("  - Entry Distance Protection (ATR-based)")
    logger.info("  - 5M LTF Confirmation")
    logger.info("  - Volume as Confirmation Gate")
    logger.info("  - Dynamic Scoring (HTF/Location/Momentum/Trigger/Volume)")
    logger.info(f"  - v3.4.0 Engine: {'✅' if V34_AVAILABLE else '❌'}")
    logger.info(f"  - Data Fetcher: {'✅' if data_client._fetcher is not None else '❌'}")
    logger.info("=" * 70)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start health server
    threading.Thread(target=run_health_server, daemon=True).start()

    # Symbols to monitor
    if hasattr(config, 'market') and hasattr(config.market, 'symbols'):
        symbols = config.market.symbols
    else:
        symbols = ["BTCUSDT", "ETHUSDT"]

    logger.info(f"{EMOJI['MONITOR']} Monitoring {len(symbols)} symbols: {', '.join(symbols[:5])}...")

    if not V34_AVAILABLE:
        logger.warning(f"{EMOJI['WARNING']} v3.4.0 engine not available - using fallback mode")

    # Main loop
    cycle = 0
    while running:
        try:
            cycle += 1
            start_time = time.time()

            # Process each symbol
            for symbol in symbols:
                if not running:
                    break
                try:
                    process_symbol(symbol)
                except Exception as e:
                    logger.error(f"Symbol {symbol} error: {e}")

            # Check active signals
            check_active_signals()

            # Log status every 10 cycles
            if cycle % 10 == 0:
                logger.info(
                    f"{EMOJI['MONITOR']} Cycle {cycle}: "
                    f"{bot_stats['signals_generated']} signals, "
                    f"{bot_stats['active_signals']} active, "
                    f"{bot_stats['errors']} errors"
                )

            # Sleep
            elapsed = time.time() - start_time
            polling_interval = 15
            if hasattr(config, 'market') and hasattr(config.market, 'polling_interval_seconds'):
                polling_interval = config.market.polling_interval_seconds
            sleep_time = max(0, polling_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)

    # Cleanup
    logger.info(f"{EMOJI['STOP']} Shutting down...")
    try:
        if mongodb_client is not None:
            mongodb_client.cleanup()
        if data_client._fetcher is not None:
            data_client._fetcher.cleanup()
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")

    logger.info(f"{EMOJI['RESULT']} Final stats: {bot_stats['signals_generated']} signals generated")
    logger.info(f"{EMOJI['SUCCESS']} Bot stopped")


if __name__ == "__main__":
    main()
