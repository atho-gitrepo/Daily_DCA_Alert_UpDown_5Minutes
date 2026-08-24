"""
Signal Cheat Sheet Generator
Provides simple, human-readable explanations for every signal
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

    ✅ ALL 5 HAPPEN = ENTER BUY TRADE
    """

    def __init__(self):
        self.oversold = 25.0
        self.soft_buy = 35.0
        self.center_line = 50.0
        self.soft_sell = 65.0
        self.overbought = 75.0

    def generate_buy_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate cheat sheet for BUY signal."""
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

        lines.append("")
        lines.append("✅ ALL 5 HAPPEN = ENTER BUY TRADE")

        # Add extra info
        lines.append("")
        lines.append("📊 Signal Details:")
        lines.append(f"• Entry Price: ${data.get('entry_price', 0):.4f}")
        lines.append(f"• Stop Loss: ${data.get('stop_loss', 0):.4f}")
        lines.append(f"• Take Profit: ${data.get('take_profit', 0):.4f}")
        lines.append(f"• RRR: {data.get('rrr', 0):.1f}")
        lines.append(f"• Confidence: {data.get('confidence', 0)*100:.0f}%")

        if data.get('divergence_detected', False):
            lines.append("🔄 Divergence detected! (Strong reversal signal)")

        if data.get('candle_pattern') and data.get('candle_pattern') != 'NONE':
            lines.append(f"🕯️ Candle Pattern: {data.get('candle_pattern')}")

        return "\n".join(lines)

    def generate_sell_cheat_sheet(self, data: Dict[str, Any]) -> str:
        """Generate cheat sheet for SELL signal."""
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

        lines.append("")
        lines.append("✅ ALL 5 HAPPEN = ENTER SELL TRADE")

        # Add extra info
        lines.append("")
        lines.append("📊 Signal Details:")
        lines.append(f"• Entry Price: ${data.get('entry_price', 0):.4f}")
        lines.append(f"• Stop Loss: ${data.get('stop_loss', 0):.4f}")
        lines.append(f"• Take Profit: ${data.get('take_profit', 0):.4f}")
        lines.append(f"• RRR: {data.get('rrr', 0):.1f}")
        lines.append(f"• Confidence: {data.get('confidence', 0)*100:.0f}%")

        if data.get('divergence_detected', False):
            lines.append("🔄 Divergence detected! (Strong reversal signal)")

        if data.get('candle_pattern') and data.get('candle_pattern') != 'NONE':
            lines.append(f"🕯️ Candle Pattern: {data.get('candle_pattern')}")

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
        """Generate cheat sheet for WAIT/NO TRADE."""
        symbol = data.get('symbol', 'UNKNOWN')
        tdi = data.get('tdi_level', 50)
        tdi_zone = self._get_tdi_zone(tdi)
        reason = data.get('reason', 'No trade signal')

        lines = []
        lines.append(f"⏳ WAIT - {symbol}")
        lines.append("📋 Cheat Sheet:")
        lines.append("")
        lines.append(f"⏸️ No trade signal detected")
        lines.append(f"📊 TDI: {tdi:.1f} ({tdi_zone})")
        lines.append(f"💬 Reason: {reason}")
        lines.append("")
        lines.append("🔍 What to watch for:")
        lines.append("• BUY: TDI below 50, Green above Red, touch lower BB")
        lines.append("• SELL: TDI above 50, Green below Red, touch upper BB")

        return "\n".join(lines)

    def _get_tdi_zone(self, tdi_value: float) -> str:
        """Get TDI zone description."""
        if tdi_value <= self.oversold:
            return "We're in the HARD BUY zone! (Below 25)"
        elif tdi_value <= self.soft_buy:
            return "We're in the SOFT BUY zone (25-35)"
        elif tdi_value < self.center_line:
            return "We're in the BUYER zone (Below 50)"
        elif tdi_value < self.soft_sell:
            return "We're in the NO TRADE zone (Around 50 - Wait!)"
        elif tdi_value < self.overbought:
            return "We're in the SOFT SELL zone (65-75)"
        else:
            return "We're in the HARD SELL zone! (Above 75)"

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
