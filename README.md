# README.md

```markdown
# 🤖 AI Trading Bot v3.4.0

**Advanced Multi-Timeframe Trading Bot with Signal State Machine**

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Binance](https://img.shields.io/badge/Binance-Futures-yellow.svg)](https://www.binance.com/)
[![Version](https://img.shields.io/badge/Version-3.4.0-green.svg)]()

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Running the Bot](#-running-the-bot)
- [Signal Flow](#-signal-flow)
- [Monitoring](#-monitoring)
- [Troubleshooting](#-troubleshooting)
- [Version History](#-version-history)

---

## 🚀 Overview

The AI Trading Bot v3.4.0 is a sophisticated algorithmic trading system designed for Binance Futures. It implements a **multi-timeframe strategy** with a **state machine architecture** that separates setup detection from signal execution, ensuring high-quality entries with proper confirmation.

### Core Philosophy

> **"A setup is not a signal. A signal requires a setup + trigger + confirmation + timely entry."**

---

## ✨ Key Features

### v3.4.0 Major Improvements

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Setup ≠ Signal** | Separates setup detection from entry trigger - prevents premature entries |
| 2 | **HTF Regime Filter** | 4H/1H controls directional bias - reduces counter-trend losses |
| 3 | **TDI Cross + Slope** | Uses Fast/Slow cross and slope, not zone alone - better timing |
| 4 | **Market Structure** | BOS/CHoCH/reclaim/sweep logic - confirms actual reversal |
| 5 | **5M Entry Trigger** | Requires 5M confirmation candle - more precise entries |
| 6 | **Volume Gate** | Volume as confirmation/validation - reduces weak reversals |
| 7 | **Signal State Machine** | SETUP → ARMED → TRIGGER → CONFIRMED - prevents inconsistent signals |
| 8 | **Entry Freshness** | Expires stale setups/signals - prevents late entries |
| 9 | **Entry Distance** | Rejects entries too far from ideal price - prevents chasing |
| 10 | **ATR Risk Model** | ATR-based SL/TP and entry distance - adapts to volatility |

### Technical Indicators

- **TDI** (Traders Dynamic Index) - Fast/Slow MA crossover with slope detection
- **Super Bollinger Bands** - 34-period, 1.750 deviation
- **Heikin Ashi** - Smoothed candle patterns
- **Divergence Detection** - Bullish/Bearish price-TDI divergence
- **Candle Patterns** - Doji, Engulfing, Hammer, Morning/Evening Star
- **Support/Resistance** - Dynamic S/R level detection
- **BB Squeeze** - Low volatility breakout detection
- **VWAP** - Volume Weighted Average Price
- **ADX/DI** - Trend strength measurement

---

## 🏗️ Architecture

### Signal State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                     SIGNAL LIFECYCLE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  NO_SETUP ──▶ SETUP_DETECTED ──▶ ARMED ──▶ TRIGGER_DETECTED    │
│                    │                    │            │          │
│                    ▼                    ▼            ▼          │
│              EXPIRED              INVALIDATED   CONFIRMING     │
│                                                        │       │
│                                                        ▼       │
│                                              SIGNAL_READY      │
│                                                    │          │
│                                                    ▼          │
│                                              ENTRY_VALID       │
│                                                    │          │
│                                                    ▼          │
│                                              ACTIVE            │
│                                                    │          │
│                                    ┌───────────────┼──────────┤
│                                    ▼               ▼          ▼
│                              TP1_HIT         TP2_HIT    SL_HIT │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Timeframe Responsibilities

| Timeframe | Responsibility | Inputs | Must NOT Do |
|-----------|---------------|--------|-------------|
| **4H** | Market Regime | Trend, Structure, ADX | Entry |
| **1H** | Directional Bias | Trend, Structure, VWAP | Entry |
| **15M** | Setup/Location | TDI, BB, S/R, Divergence | Immediate Entry |
| **5M** | Trigger | TDI Cross, Candle, Structure | Determine Macro Trend |
| **1M** | Execution Refinement | Entry Distance, Micro Structure | Override HTF |

### HTF Regime System

| 4H Trend | 1H Trend | Regime | BUY | SELL |
|----------|----------|--------|-----|------|
| BULLISH | BULLISH | STRONG_BULL | ✅ Preferred | ❌ |
| BULLISH | NEUTRAL | BULL | ✅ | ⚠️ |
| NEUTRAL | BULLISH | MILD_BULL | ✅ | ⚠️ |
| NEUTRAL | NEUTRAL | NEUTRAL | ⚠️ | ⚠️ |
| BEARISH | BEARISH | STRONG_BEAR | ❌ | ✅ Preferred |
| BEARISH | NEUTRAL | BEAR | ⚠️ | ✅ |
| BULLISH | BEARISH | CONFLICT | ⚠️ | ⚠️ |
| BEARISH | BULLISH | CONFLICT | ⚠️ | ⚠️ |

---

## 📦 Installation

### Prerequisites

- Python 3.9+
- Binance API Key (Testnet recommended for initial testing)
- MongoDB (Optional - for signal persistence)
- Telegram Bot Token (Optional - for notifications)

### Clone & Install

```bash
# Clone the repository
git clone https://github.com/yourusername/trading-bot.git
cd trading-bot

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### Requirements

```txt
python-binance==1.0.19
pandas==2.0.3
numpy==1.24.3
python-dotenv==1.0.0
groq==0.4.2
python-telegram-bot==20.6
pymongo==4.6.1
requests==2.31.0
aiohttp==3.9.1
scipy>=1.10.0
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# ========== BINANCE API ==========
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_USE_TESTNET=true

# ========== TELEGRAM ==========
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# ========== MONGODB ==========
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/database

# ========== v3.4.0 THRESHOLDS ==========
MIN_SETUP_SCORE=70
MIN_TRIGGER_SCORE=70
COUNTER_TREND_MIN_SCORE=82
MAX_ENTRY_DISTANCE_ATR=0.25
SETUP_EXPIRY_SECONDS=300
TRIGGER_EXPIRY_SECONDS=120

# ========== FEATURES ==========
ENABLE_DIVERGENCE=true
ENABLE_CANDLE_PATTERNS=true
ENABLE_SR=true
ENABLE_BB_SQUEEZE=true
ENABLE_SESSION_FILTERING=true
ENABLE_HTF_REGIME=true
ENABLE_STRUCTURE_ANALYSIS=true
```

### Key Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MIN_SETUP_SCORE` | 70 | Minimum setup score to arm |
| `MIN_TRIGGER_SCORE` | 70 | Minimum trigger score to confirm |
| `COUNTER_TREND_MIN_SCORE` | 82 | Higher threshold for counter-trend signals |
| `MAX_ENTRY_DISTANCE_ATR` | 0.25 | Max distance from ideal entry (ATR units) |
| `SETUP_EXPIRY_SECONDS` | 300 | Setup expires after 5 minutes |
| `TRIGGER_EXPIRY_SECONDS` | 120 | Trigger expires after 2 minutes |
| `GRADE_A_THRESHOLD` | 82 | Score for Grade A |
| `GRADE_B_THRESHOLD` | 70 | Score for Grade B |

---

## 🏃 Running the Bot

### Quick Start

```bash
# Run with default configuration
python main_v34.py

# Run with specific config
python main_v34.py --config production

# Run in demo mode (no real trades)
python main_v34.py --demo
```

### Docker Deployment

```bash
# Build the image
docker build -t trading-bot-v34 .

# Run the container
docker run -d \
  --name trading-bot \
  --env-file .env \
  -p 8080:8080 \
  trading-bot-v34
```

### Railway Deployment

The bot includes `railway.json` and `nixpacks.toml` for one-click deployment:

1. Fork the repository
2. Connect to Railway
3. Set environment variables
4. Deploy

---

## 🔄 Signal Flow

### Step-by-Step Signal Generation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SIGNAL GENERATION FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: DATA VALIDATION                                                    │
│  └─▶ Check data quality, minimum bars, indicator availability              │
│                                                                             │
│  STEP 2: HTF REGIME (4H/1H)                                                │
│  └─▶ Determine directional bias - BULLISH/BEARISH/NEUTRAL                  │
│                                                                             │
│  STEP 3: SETUP DETECTION                                                    │
│  └─▶ TDI Zone + Location + Divergence + Patterns = Setup Score ≥ 70        │
│                                                                             │
│  STEP 4: ARM SETUP                                                          │
│  └─▶ Setup becomes ARMED - waiting for trigger                             │
│                                                                             │
│  STEP 5: TRIGGER DETECTION                                                  │
│  └─▶ TDI Cross + Candle + Structure = Trigger Score ≥ 70                   │
│                                                                             │
│  STEP 6: LTF CONFIRMATION (5M)                                              │
│  └─▶ 5M confirms with TDI cross + HA reversal                              │
│                                                                             │
│  STEP 7: VOLUME VALIDATION                                                  │
│  └─▶ Volume ratio must be ≥ 1.0x (1.3x+ for strong confirmation)           │
│                                                                             │
│  STEP 8: STRUCTURE VALIDATION                                               │
│  └─▶ BOS/CHoCH/reclaim/sweep must confirm direction                        │
│                                                                             │
│  STEP 9: ENTRY VALIDATION                                                   │
│  └─▶ Current price within 0.25 ATR of ideal entry                          │
│                                                                             │
│  STEP 10: FINAL SCORING & GRADING                                           │
│  └─▶ Score: 90-100=A+, 82-89=A, 75-81=B+, 70-74=B                          │
│                                                                             │
│  STEP 11: SIGNAL GENERATION                                                 │
│  └─▶ 🟢 BUY/SELL SIGNAL generated                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Scoring Components

| Component | Weight | Description |
|-----------|--------|-------------|
| HTF Regime | 20% | Directional bias from 4H/1H |
| Location | 20% | S/R proximity, BB position |
| Momentum/TDI | 20% | TDI cross, slope, zone |
| Entry Trigger | 25% | Candle, structure, volume |
| Volume | 15% | Volume confirmation |

### Grade System

| Score | Grade | Action |
|-------|-------|--------|
| 90-100 | **A+** | Highest-priority signal |
| 82-89 | **A** | Execute |
| 75-81 | **B+** | Conditional |
| 70-74 | **B** | Conservative/conditional |
| 60-69 | **C** | Watch only |
| <60 | **D** | Reject |

---

## 📊 Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "running",
  "version": "3.4.0",
  "timestamp": "2026-08-23T16:13:51.360229Z",
  "stats": {
    "signals_generated": 0,
    "active_signals": 0,
    "errors": 0
  },
  "v34_available": true,
  "features": {
    "htf_regime": true,
    "structure_analysis": true,
    "signal_state_machine": true,
    "entry_distance_protection": true,
    "atr_risk_model": true
  }
}
```

### Log Monitoring

```bash
# View live logs
tail -f logs/trading_bot.log

# Filter for signals only
tail -f logs/trading_bot.log | grep "SIGNAL"

# Filter for errors
tail -f logs/trading_bot.log | grep "ERROR"
```

### Metrics Endpoint

```bash
curl http://localhost:8080/metrics
```

Returns Prometheus-style metrics for monitoring.

---

## 🔧 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'data_fetcher'` | Ensure `utils/data_fetcher.py` exists. Check import paths in `main_v34.py` |
| **No signals generated** | This is normal. v3.4.0 is strict by design. Wait for proper market conditions |
| **Binance connection failed** | Check API keys. Use testnet for testing: `BINANCE_USE_TESTNET=true` |
| **MongoDB connection failed** | Check `MONGODB_URI` or set `MONGODB_ENABLED=false` to run in-memory |
| **Telegram not sending messages** | Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` |

### Log Levels

Set `LOG_LEVEL` in `.env`:

| Level | Use Case |
|-------|----------|
| `DEBUG` | Full debugging, indicator values |
| `INFO` | Normal operation (default) |
| `WARNING` | Only warnings and errors |
| `ERROR` | Errors only |

### Signal Debugging

To see why signals are being rejected, add this to `main_v34.py`:

```python
# After result = signal_engine.process(df, ltf_data)
if result['signal'] == 'NO_TRADE':
    reason = result.get('data', {}).get('reason', 'Unknown')
    logger.debug(f"❌ {symbol}: {reason}")
```

---

## 📈 Version History

### v3.4.0 (Current)

- **Setup ≠ Signal** - Separate detection from entry trigger
- **HTF Regime Filter** - 4H/1H directional bias control
- **TDI Cross + Slope** - Not just zone alone
- **Market Structure** - BOS/CHoCH/liquidity sweep/reclaim
- **5M Entry Trigger** - LTF confirmation candle
- **Volume Gate** - Volume as confirmation/validation
- **Signal State Machine** - SETUP → ARMED → TRIGGER → CONFIRMED
- **Entry Freshness** - Stale setups expire
- **Entry Distance Protection** - ATR-normalized distance check
- **ATR Risk Model** - Dynamic SL/TP based on volatility
- **Reversal vs Continuation** - Separate strategies with different scores
- **Dynamic Scoring** - Regime/Location/Momentum/Trigger/Volume
- **Session Handling** - Modified requirements, not just confidence
- **Signal Grading** - A+/A/B/C/D hierarchy
- **Hard Rejection Rules** - Never override hard gates

### v3.3.0 (Previous)

- Divergence Detection (Bullish/Bearish)
- Candle Pattern Recognition
- Support/Resistance Levels
- BB Squeeze Detection
- Session-Based Filtering

---

## 📁 Project Structure

```
trading-bot/
├── main_v34.py              # Main entry point
├── settings.py              # Configuration
├── strategy/
│   ├── __init__.py
│   ├── signal_engine_v34.py # v3.4.0 Signal Engine
│   ├── signal_state.py      # State Machine
│   ├── htf_regime.py        # HTF Regime System
│   └── structure.py         # Market Structure Analysis
├── utils/
│   ├── __init__.py
│   ├── data_fetcher.py      # Binance Data Fetcher
│   ├── indicators.py        # Technical Indicators
│   ├── signal_manager.py    # Signal Lifecycle Manager
│   ├── mongodb_client.py    # MongoDB Persistence
│   ├── telegram_bot.py      # Telegram Notifications
│   └── ai_analyzer.py       # AI Analysis (Optional)
├── .env.example             # Environment variables template
├── requirements.txt         # Python dependencies
├── railway.json             # Railway deployment config
└── nixpacks.toml            # Nixpacks build config
```

---

## 🛡️ Disclaimer

**IMPORTANT:** This bot is for **educational and research purposes only**.

- **Not financial advice** - Do not trade with money you cannot afford to lose
- **No guarantees** - Past performance does not guarantee future results
- **Use at your own risk** - The authors assume no liability for financial losses
- **Test thoroughly** - Always test on testnet before using real funds

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a Pull Request

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/trading-bot/issues)
- **Documentation**: [Wiki](https://github.com/yourusername/trading-bot/wiki)
- **Discord**: [Join our Discord](https://discord.gg/your-invite)

---

## 🙏 Acknowledgments

- Binance for the excellent API
- The open-source community for the libraries
- All contributors and testers

---

*Built with ❤️ and ☕ by the Trading Bot Team*

**Version 3.4.0** | *Last Updated: August 2026*
```
