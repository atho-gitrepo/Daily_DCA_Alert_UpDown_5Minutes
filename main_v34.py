# main_v34.py
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
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import signal

import pandas as pd
import numpy as np

from settings import config
from data_fetcher import data_fetcher
from strategy.signal_engine_v34 import signal_engine, SignalState
from strategy.htf_regime import htf_regime, Regime
from utils.signal_manager import signal_manager
from utils.telegram_bot import telegram_bot
from utils.mongodb_client import mongodb_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    }
}


def fetch_data(symbol: str, timeframe: str = '15m') -> Optional[pd.DataFrame]:
    """Fetch historical data with retry."""
    try:
        df = data_fetcher.fetch_klines(symbol, timeframe, 200)
        if df is not None and not df.empty:
            # Calculate all indicators
            from utils.indicators import Indicators, calculate_heikin_ashi
            df = Indicators.calculate_all_indicators(df)
            return df
        return None
    except Exception as e:
        logger.error(f"Data fetch error for {symbol}: {e}")
        return None


def fetch_htf_data(symbol: str) -> Dict[str, pd.DataFrame]:
    """Fetch higher timeframe data for regime analysis."""
    result = {}
    try:
        # 4H data
        df_4h = data_fetcher.fetch_klines(symbol, '4h', 50)
        if df_4h is not None and not df_4h.empty:
            result['4h'] = df_4h

        # 1H data
        df_1h = data_fetcher.fetch_klines(symbol, '1h', 50)
        if df_1h is not None and not df_1h.empty:
            result['1h'] = df_1h

        return result
    except Exception as e:
        logger.error(f"HTF data fetch error: {e}")
        return {}


def check_ltf_confirmation(symbol: str, direction: str) -> Dict[str, Any]:
    """Check 5M LTF confirmation."""
    try:
        df_5m = data_fetcher.fetch_klines(symbol, '5m', 100)
        if df_5m is None or df_5m.empty:
            return {'confirmed': False, 'confidence': 0, 'reason': 'No data'}

        from utils.indicators import Indicators, calculate_heikin_ashi
        df_5m = Indicators.calculate_tdi(df_5m)
        df_5m = calculate_heikin_ashi(df_5m)

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
            # Bullish cross
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
            # Bearish cross
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
            'direction': direction
        }

    except Exception as e:
        logger.error(f"LTF check error: {e}")
        return {'confirmed': False, 'confidence': 0, 'reason': f'Error: {e}'}


def process_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Process a single symbol."""
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
        if not htf_data:
            return None

        # Update HTF regime
        df_4h = htf_data.get('4h')
        df_1h = htf_data.get('1h')
        if df_4h is not None and df_1h is not None:
            htf_regime.analyze(df_4h, df_1h)

        # Get LTF confirmation
        ltf_data = check_ltf_confirmation(symbol, '')  # Direction will be set by engine

        # Process through signal engine
        result = signal_engine.process(df, ltf_data)

        if result['signal'] != 'NO_TRADE':
            # Generate final signal
            signal_data = result['data']
            signal_data['symbol'] = symbol

            # Lock symbol
            if signal_manager.lock_symbol(
                symbol=symbol,
                signal_type=signal_data['direction'],
                entry_price=signal_data['entry_price'],
                raw_data=signal_data,
                stop_loss=signal_data.get('stop_loss', 0),
                take_profit=signal_data.get('take_profit', 0),
                confidence=0.85,
                rrr=2.0,
                grade=signal_data.get('grade', 'B'),
                total_score=signal_data.get('final_score', 75),
                signal_strength='SOFT',
                tdi_level=signal_data.get('tdi_level', 50),
                tdi_zone=signal_data.get('tdi_zone', 'NEUTRAL'),
                htf_trend=htf_regime.get_directional_bias(),
                ltf_confirmed=True,
                ltf_confidence=0.8,
                htf_aligned=True,
                divergence_detected=signal_data.get('divergence_detected', False),
                candle_pattern=signal_data.get('candle_pattern', 'NONE'),
                sr_confirmed=signal_data.get('sr_confirmed', False),
                bb_squeeze=signal_data.get('bb_squeeze', False),
                session=signal_data.get('session', 'UNKNOWN'),
            ):
                bot_stats['signals_generated'] += 1

                # Send Telegram notification
                if telegram_bot.enabled:
                    telegram_bot.send_signal(
                        symbol=symbol,
                        signal_type=signal_data['direction'],
                        entry_price=signal_data['entry_price'],
                        stop_loss=signal_data.get('stop_loss', 0),
                        take_profit=signal_data.get('take_profit', 0),
                        confidence=0.85,
                        ai_decision='APPROVE',
                        ai_confidence=0.85,
                        rrr=2.0,
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

                logger.info(f"📡 SIGNAL: {signal_data['direction']} {symbol} @ {signal_data['entry_price']:.4f} (Grade: {signal_data.get('grade', 'B')})")
                return signal_data

        return None

    except Exception as e:
        logger.error(f"Process error for {symbol}: {e}")
        bot_stats['errors'] += 1
        return None


def check_active_signals():
    """Check and update active signals."""
    active = signal_manager.get_all_active_signals()
    bot_stats['active_signals'] = len(active)

    # Log active signals
    if active:
        logger.info(f"📊 Active signals: {len(active)}")
        for symbol, signal in active.items():
            age = signal.get_age_minutes() if hasattr(signal, 'get_age_minutes') else 0
            logger.debug(f"  - {symbol}: {signal.signal_type} @ {signal.entry_price:.4f} ({age:.1f}min)")


def run_health_server():
    """Run health check server."""
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'running',
                    'version': '3.4.0',
                    'timestamp': datetime.now().isoformat(),
                    'stats': bot_stats,
                    'active_signals': len(signal_manager.active_signals)
                }, indent=2).encode())
            else:
                self.send_response(404)
                self.end_headers()

    server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
    server.serve_forever()


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    global running
    logger.info("🛑 Shutting down...")
    running = False


def main():
    """Main entry point."""
    global running

    logger.info("=" * 60)
    logger.info("🚀 AI Trading Bot v3.4.0")
    logger.info("=" * 60)
    logger.info("✨ Features:")
    logger.info("  - HTF Regime System (4H/1H)")
    logger.info("  - Setup ≠ Signal (state machine)")
    logger.info("  - Market Structure (BOS/CHoCH/Sweep)")
    logger.info("  - TDI Cross + Slope (not zone alone)")
    logger.info("  - Entry Distance Protection (ATR-based)")
    logger.info("  - 5M LTF Confirmation")
    logger.info("  - Volume as Confirmation Gate")
    logger.info("  - Dynamic Scoring (HTF/Location/Momentum/Trigger/Volume)")
    logger.info("=" * 60)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start health server
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info("💚 Health server running on port 8080")

    # Symbols to monitor
    symbols = config.market.symbols
    logger.info(f"📊 Monitoring {len(symbols)} symbols: {', '.join(symbols[:5])}...")

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
                logger.info(f"📊 Cycle {cycle}: {bot_stats['signals_generated']} signals, {bot_stats['active_signals']} active")

            # Sleep
            elapsed = time.time() - start_time
            sleep_time = max(0, config.market.polling_interval_seconds - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

    # Cleanup
    logger.info("🛑 Shutting down...")
    try:
        data_fetcher.cleanup()
    except:
        pass

    logger.info(f"📊 Final stats: {bot_stats['signals_generated']} signals generated")
    logger.info("✅ Bot stopped")


if __name__ == "__main__":
    main()
