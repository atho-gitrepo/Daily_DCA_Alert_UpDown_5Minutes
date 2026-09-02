from unittest.mock import MagicMock, patch

import main
from utils.signal_manager import SignalData, SignalManager, TradeLifecycle


def test_market_timeframe_stack_uses_ltf_check_htf_order():
    main.config.market.ltf_timeframe = '1m'
    main.config.market.timeframe = '5m'
    main.config.market.htf_timeframe = '1h'

    timeframe_stack = main.get_timeframe_stack()

    assert timeframe_stack == {'ltf': '1m', 'check': '5m', 'htf': '1h'}


def test_unlock_symbol_sends_telegram_result():
    manager = SignalManager()
    signal = SignalData(
        symbol="BTCUSDT",
        signal_type="BUY",
        entry_price=100.0,
        entry_time="2026-08-31T12:00:00",
        stop_loss=95.0,
        take_profit=110.0,
        confidence=0.8,
        tdi_level=60.0,
        rrr=1.5,
        signal_strength="HARD",
        risk_multiplier=2.0,
        total_score=80,
        grade="A",
        conditions_met=4,
        conditions_total=5,
    )
    manager.active_signals[signal.symbol] = signal

    fake_bot = MagicMock()
    fake_bot.enabled = True
    fake_bot.send_result.return_value = True

    with patch("utils.telegram_bot.telegram_bot", fake_bot):
        updated = manager._unlock_symbol(signal.symbol, TradeLifecycle.PROFIT, 105.0)

    assert updated is signal
    assert fake_bot.send_result.called
    assert fake_bot.send_result.call_args.kwargs["symbol"] == "BTCUSDT"
    assert fake_bot.send_result.call_args.kwargs["status"] == "PROFIT"
