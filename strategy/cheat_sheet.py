"""
Signal Cheat Sheet Generator
Provides simple, human-readable explanations for every signal
Version: 3.4.1 - ADDED: MACD confirmation to cheat sheets
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class SignalCheatSheet:
    """
    Generates easy-to-understand cheat sheet explanations for signals.

    Example Output:
    ✅ BUY SIGNAL - BTCUSDT
    📋 Cheat Sheet:
    1. TDI says: "We're in the buyer zone" (TDI: 32.4 below 50)
    2. Green line crossed ABOVE Red line (Bulls taking over)
    3. Price touched the LOWER Bollinger Band (Oversold)
    4. Candles are getting SMALLER (People giving up)
    5. Price started moving BACK inside the band (Reversal happening)
    6. MACD is BULLISH (Histogram rising)

    ✅ ALL 5 + MACD = ENTER BUY TRADE
    """

    def __init__(self):
        self.oversold = 25.0
        self.soft_buy = 35.0
        self.center_line = 50.0
        self.soft_sell = 65.0
        self.overbought = 75.0

        # MACD Settings
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.require_macd = True

    def generate_buy_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate cheat sheet for BUY signal with MACD."""
        lines = []

        # Header
        symbol = data.get('symbol', 'UNKNOWN')
        lines.append(f"✅ BUY SIGNAL - {symbol}")
        lines.append("📋 Cheat Sheet:")
        lines.append("")

        # Step 1: TDI Zone
        tdi = data.get('tdi_level', 50)
        tdi_zone = self._get_tdi_zone(tdi)
        lines.append(f"1. TDI says: \"{tdi_zone}\" (TDI: {tdi:.1f})")

        # Step 2: Crossover
        if data.get('tdi_bullish_cross', False):
            lines.append("2. Green line crossed ABOVE Red line ✅ (Bulls taking over)")
        else:
            lines.append("2. Green line is ABOVE Red line ✅ (Bulls in control)")

        # Step 3: Bollinger Band touch
        bb_position = data.get('bb_position', 0.5)
        if bb_position < 0.15:
            lines.append("3. Price touched the LOWER Bollinger Band ✅ (Oversold)")
        elif bb_position < 0.30:
            lines.append("3. Price near the LOWER Bollinger Band ✅ (Approaching oversold)")
        else:
            lines.append("3. Price inside Bollinger Band ✅ (Ready for reversal)")

        # Step 4: Candles getting smaller
        if data.get('candles_shrinking', False):
            lines.append("4. Candles are getting SMALLER ✅ (People giving up)")
        else:
            lines.append("4. Candles showing reversal signs ✅ (Momentum shifting)")

        # Step 5: Reversal happening
        if data.get('reversal_confirm', False):
            lines.append("5. Price started moving BACK inside the band ✅ (Reversal happening)")
        else:
            lines.append("5. Price showing reversal signs ✅ (Entry confirmed)")

        # Step 6: MACD (NEW)
        macd_bullish = data.get('macd_bullish', False)
        macd_histogram = data.get('macd_histogram', 0.0)
        macd_required = self.require_macd

        if macd_bullish:
            lines.append(f"6. MACD is BULLISH ✅ (Histogram: {macd_histogram:.4f} rising)")
        elif macd_required:
            lines.append(f"6. MACD is NEUTRAL ⚠️ (Histogram: {macd_histogram:.4f})")
            lines.append("   ⚠️ MACD confirmation REQUIRED but not confirmed")
        else:
            lines.append(f"6. MACD is NEUTRAL (Histogram: {macd_histogram:.4f})")

        lines.append("")
        if macd_bullish or not macd_required:
            lines.append("✅ ALL 5 + MACD = ENTER BUY TRADE")
        else:
            lines.append("⏳ Waiting for MACD confirmation...")

        # Add extra info
        lines.append("")
        lines.append("📊 Signal Details:")
        lines.append(f"• Entry Price: ${data.get('entry_price', 0):.4f}")
        lines.append(f"• Stop Loss: ${data.get('stop_loss', 0):.4f}")
        lines.append(f"• Take Profit: ${data.get('take_profit', 0):.4f}")
        lines.append(f"• RRR: {data.get('rrr', 0):.1f}")
        lines.append(f"• Confidence: {data.get('confidence', 0)*100:.0f}%")

        # MACD Details
        lines.append("")
        lines.append("📊 MACD Details:")
        lines.append(f"• MACD Line: {data.get('macd', 0):.4f}")
        lines.append(f"• Signal Line: {data.get('macd_signal_line', 0):.4f}")
        lines.append(f"• Histogram: {data.get('macd_histogram', 0):.4f}")
        lines.append(f"• Bullish: {'✅' if macd_bullish else '❌'}")

        if data.get('divergence_detected', False):
            lines.append("🔄 Divergence detected! (Strong reversal signal)")

        if data.get('candle_pattern') and data.get('candle_pattern') != 'NONE':
            lines.append(f"🕯️ Candle Pattern: {data.get('candle_pattern')}")

        if data.get('sr_confirmed', False):
            lines.append(f"📊 S/R Confirmed: Support ${data.get('nearest_support', 0):.4f}")

        return "\n".join(lines)

    def generate_sell_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate cheat sheet for SELL signal with MACD."""
        lines = []

        # Header
        symbol = data.get('symbol', 'UNKNOWN')
        lines.append(f"🔴 SELL SIGNAL - {symbol}")
        lines.append("📋 Cheat Sheet:")
        lines.append("")

        # Step 1: TDI Zone
        tdi = data.get('tdi_level', 50)
        tdi_zone = self._get_tdi_zone(tdi)
        lines.append(f"1. TDI says: \"{tdi_zone}\" (TDI: {tdi:.1f})")

        # Step 2: Crossover
        if data.get('tdi_bearish_cross', False):
            lines.append("2. Green line crossed BELOW Red line ✅ (Bears taking over)")
        else:
            lines.append("2. Green line is BELOW Red line ✅ (Bears in control)")

        # Step 3: Bollinger Band touch
        bb_position = data.get('bb_position', 0.5)
        if bb_position > 0.85:
            lines.append("3. Price touched the UPPER Bollinger Band ✅ (Overbought)")
        elif bb_position > 0.70:
            lines.append("3. Price near the UPPER Bollinger Band ✅ (Approaching overbought)")
        else:
            lines.append("3. Price inside Bollinger Band ✅ (Ready for reversal)")

        # Step 4: Candles getting smaller
        if data.get('candles_shrinking', False):
            lines.append("4. Candles are getting SMALLER ✅ (People giving up)")
        else:
            lines.append("4. Candles showing reversal signs ✅ (Momentum shifting)")

        # Step 5: Reversal happening
        if data.get('reversal_confirm', False):
            lines.append("5. Price started moving BACK inside the band ✅ (Reversal happening)")
        else:
            lines.append("5. Price showing reversal signs ✅ (Entry confirmed)")

        # Step 6: MACD (NEW)
        macd_bearish = data.get('macd_bearish', False)
        macd_histogram = data.get('macd_histogram', 0.0)
        macd_required = self.require_macd

        if macd_bearish:
            lines.append(f"6. MACD is BEARISH ✅ (Histogram: {macd_histogram:.4f} falling)")
        elif macd_required:
            lines.append(f"6. MACD is NEUTRAL ⚠️ (Histogram: {macd_histogram:.4f})")
            lines.append("   ⚠️ MACD confirmation REQUIRED but not confirmed")
        else:
            lines.append(f"6. MACD is NEUTRAL (Histogram: {macd_histogram:.4f})")

        lines.append("")
        if macd_bearish or not macd_required:
            lines.append("✅ ALL 5 + MACD = ENTER SELL TRADE")
        else:
            lines.append("⏳ Waiting for MACD confirmation...")

        # Add extra info
        lines.append("")
        lines.append("📊 Signal Details:")
        lines.append(f"• Entry Price: ${data.get('entry_price', 0):.4f}")
        lines.append(f"• Stop Loss: ${data.get('stop_loss', 0):.4f}")
        lines.append(f"• Take Profit: ${data.get('take_profit', 0):.4f}")
        lines.append(f"• RRR: {data.get('rrr', 0):.1f}")
        lines.append(f"• Confidence: {data.get('confidence', 0)*100:.0f}%")

        # MACD Details
        lines.append("")
        lines.append("📊 MACD Details:")
        lines.append(f"• MACD Line: {data.get('macd', 0):.4f}")
        lines.append(f"• Signal Line: {data.get('macd_signal_line', 0):.4f}")
        lines.append(f"• Histogram: {data.get('macd_histogram', 0):.4f}")
        lines.append(f"• Bearish: {'✅' if macd_bearish else '❌'}")

        if data.get('divergence_detected', False):
            lines.append("🔄 Divergence detected! (Strong reversal signal)")

        if data.get('candle_pattern') and data.get('candle_pattern') != 'NONE':
            lines.append(f"🕯️ Candle Pattern: {data.get('candle_pattern')}")

        if data.get('sr_confirmed', False):
            lines.append(f"📊 S/R Confirmed: Resistance ${data.get('nearest_resistance', 0):.4f}")

        return "\n".join(lines)

    def generate_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate cheat sheet based on signal direction."""
        direction = data.get('direction', 'NONE')
        if direction == 'BUY':
            return self.generate_buy_cheat_sheet(data)
        elif direction == 'SELL':
            return self.generate_sell_cheat_sheet(data)
        else:
            return self.generate_wait_cheat_sheet(data)

    def generate_wait_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate cheat sheet for WAIT/NO TRADE with MACD."""
        symbol = data.get('symbol', 'UNKNOWN')
        tdi = data.get('tdi_level', 50)
        tdi_zone = self._get_tdi_zone(tdi)
        reason = data.get('reason', 'No trade signal')
        macd_histogram = data.get('macd_histogram', 0.0)

        lines = []
        lines.append(f"⏳ WAIT - {symbol}")
        lines.append("📋 Cheat Sheet:")
        lines.append("")
        lines.append(f"⏸️ No trade signal detected")
        lines.append(f"📊 TDI: {tdi:.1f} ({tdi_zone})")
        lines.append(f"📊 MACD Histogram: {macd_histogram:.4f}")
        lines.append(f"💬 Reason: {reason}")
        lines.append("")
        lines.append("🔍 What to watch for:")
        lines.append("• BUY: TDI below 50, Green above Red, touch lower BB, MACD bullish")
        lines.append("• SELL: TDI above 50, Green below Red, touch upper BB, MACD bearish")
        lines.append("")
        lines.append("📊 MACD Signals:")
        lines.append("• Bullish: MACD line above Signal, Histogram rising")
        lines.append("• Bearish: MACD line below Signal, Histogram falling")

        return "\n".join(lines)

    def generate_condition_report(self, data: Dict[str, Any]) -> str:
        """Generate a detailed condition report."""
        symbol = data.get('symbol', 'UNKNOWN')
        direction = data.get('direction', 'NONE')

        lines = []
        lines.append(f"📋 Condition Report - {symbol} ({direction})")
        lines.append("")

        conditions = [
            ('tdi_zone', 'TDI in buyer/seller zone'),
            ('tdi_cross', 'Green crossed above/below Red'),
            ('bb_touch', 'Price touched Bollinger Band'),
            ('candles_shrinking', 'Candles getting SMALLER'),
            ('reversal_confirm', 'Price moving BACK inside band'),
        ]

        condition_keys = [
            'condition_1_tdi_zone',
            'condition_2_tdi_cross',
            'condition_3_bb_touch',
            'condition_4_candles_shrinking',
            'condition_5_reversal_confirm'
        ]

        # MACD condition
        macd_bullish = data.get('macd_bullish', False)
        macd_bearish = data.get('macd_bearish', False)

        for i, (key, desc) in enumerate(conditions):
            status = data.get(condition_keys[i], False)
            emoji = "✅" if status else "⬜"
            lines.append(f"{emoji} {desc}")

        # MACD condition
        macd_ok = macd_bullish if direction == 'BUY' else (macd_bearish if direction == 'SELL' else False)
        macd_emoji = "✅" if macd_ok else "⬜"
        macd_desc = "MACD confirms direction" if macd_ok else "MACD does not confirm"
        lines.append(f"{macd_emoji} {macd_desc}")

        conditions_met = sum(1 for k in condition_keys if data.get(k, False)) + (1 if macd_ok else 0)
        conditions_total = len(conditions) + 1

        lines.append("")
        lines.append(f"📊 Conditions Met: {conditions_met}/{conditions_total}")

        # Recommendations
        lines.append("")
        if conditions_met >= 5:
            lines.append("🎯 STRONG SIGNAL - Ready to trade!")
        elif conditions_met >= 4:
            lines.append("📊 Good Signal - Consider entry")
        elif conditions_met >= 3:
            lines.append("📊 Fair Signal - Needs confirmation")
        else:
            lines.append("⏳ Not enough conditions - WAIT")

        return "\n".join(lines)

    def generate_macd_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate a MACD-specific cheat sheet."""
        symbol = data.get('symbol', 'UNKNOWN')
        macd = data.get('macd', 0)
        signal = data.get('macd_signal_line', data.get('macd_signal', 0))
        histogram = data.get('macd_histogram', 0)
        bullish = data.get('macd_bullish', False)
        bearish = data.get('macd_bearish', False)

        lines = []
        lines.append(f"📊 MACD Analysis - {symbol}")
        lines.append("")
        lines.append("📊 MACD Values:")
        lines.append(f"• MACD Line: {macd:.4f}")
        lines.append(f"• Signal Line: {signal:.4f}")
        lines.append(f"• Histogram: {histogram:.4f}")
        lines.append("")

        # Signal interpretation
        if bullish:
            lines.append("🟢 MACD is BULLISH")
            lines.append("• MACD line above Signal line")
            if histogram > 0:
                lines.append("• Histogram is rising (momentum increasing) ✅")
            else:
                lines.append("• Histogram is falling (momentum decreasing) ⚠️")
        elif bearish:
            lines.append("🔴 MACD is BEARISH")
            lines.append("• MACD line below Signal line")
            if histogram < 0:
                lines.append("• Histogram is falling (momentum increasing) ✅")
            else:
                lines.append("• Histogram is rising (momentum decreasing) ⚠️")
        else:
            lines.append("⚪ MACD is NEUTRAL")
            lines.append("• MACD line crossing Signal line")
            lines.append("• Wait for confirmation")

        lines.append("")
        lines.append("📊 Recommended Action:")
        if bullish:
            lines.append("• Consider BUY entries")
            lines.append("• Wait for price to confirm")
        elif bearish:
            lines.append("• Consider SELL entries")
            lines.append("• Wait for price to confirm")
        else:
            lines.append("• Wait for MACD crossover")
            lines.append("• Monitor histogram direction")

        return "\n".join(lines)

    def _get_tdi_zone(self, tdi_value: float) -> str:
        """Get TDI zone description."""
        if tdi_value <= self.oversold:
            return "HARD BUY zone! (Below 25)"
        elif tdi_value <= self.soft_buy:
            return "SOFT BUY zone (25-35)"
        elif tdi_value < self.center_line:
            return "BUYER zone (Below 50)"
        elif tdi_value < self.soft_sell:
            return "NO TRADE zone (Around 50 - Wait!)"
        elif tdi_value < self.overbought:
            return "SOFT SELL zone (65-75)"
        else:
            return "HARD SELL zone! (Above 75)"

    def get_signal_instructions(self, direction: str) -> Dict[str, str]:
        """Get trading instructions for direction."""
        if direction == 'BUY':
            return {
                'action': 'Buy (Long)',
                'entry': 'Enter at market price',
                'stop_loss': 'Place below recent swing low',
                'take_profit': 'Target previous resistance or 1:1 RRR',
                'risk': 'Risk 0.25-0.50% of account'
            }
        elif direction == 'SELL':
            return {
                'action': 'Sell (Short)',
                'entry': 'Enter at market price',
                'stop_loss': 'Place above recent swing high',
                'take_profit': 'Target previous support or 1:1 RRR',
                'risk': 'Risk 0.25-0.50% of account'
            }
        else:
            return {
                'action': 'Wait',
                'entry': 'No entry',
                'stop_loss': 'N/A',
                'take_profit': 'N/A',
                'risk': '0%'
            }

    def get_macd_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get MACD status summary."""
        macd = data.get('macd', 0)
        signal = data.get('macd_signal_line', data.get('macd_signal', 0))
        histogram = data.get('macd_histogram', 0)
        bullish = data.get('macd_bullish', False)
        bearish = data.get('macd_bearish', False)

        if bullish:
            status = 'BULLISH'
            action = 'BUY'
            emoji = '🟢'
        elif bearish:
            status = 'BEARISH'
            action = 'SELL'
            emoji = '🔴'
        else:
            status = 'NEUTRAL'
            action = 'WAIT'
            emoji = '⚪'

        return {
            'status': status,
            'action': action,
            'emoji': emoji,
            'macd': macd,
            'signal': signal,
            'histogram': histogram,
            'histogram_rising': histogram > 0,
            'above_signal': macd > signal,
        }
