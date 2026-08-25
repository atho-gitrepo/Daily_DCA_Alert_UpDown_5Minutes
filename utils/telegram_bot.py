"""
Telegram Bot for Trading Signals - SUPER TDI + MACD + SUPER BOLLINGER BANDS
ALIGNED: Super TDI + MACD + Super BB Strategy with Cheat Sheet & AI Insights
Version: 3.4.2 - ADDED: MACD confirmation display
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from settings import config

logger = logging.getLogger(__name__)
telegram_logger = logging.getLogger("telegram_bot")

EMOJI = {
    "BUY": "🟢",
    "SELL": "🔴",
    "SIGNAL": "📡",
    "PROFIT": "💰",
    "LOSS": "💸",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "SUCCESS": "✅",
    "SNIPER": "🎯",
    "CLOCK": "🕐",
    "CHART": "📊",
    "ROCKET": "🚀",
    "LTF": "⏱️",
    "HEALTH": "💚",
    "RRR": "📈",
    "AI": "🤖",
    "HTF": "📊",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "BREAK": "⏹️",
    "EXPIRED": "⌛",
    "HARD": "🔴",
    "SOFT": "🟡",
    "TDI": "📈",
    "BB": "📊",
    "MACD": "📊",
    "ZONE": "🎯",
    "CROSSOVER": "🔀",
    "SCORE": "🎯",
    "STAR": "⭐",
    "REJECT": "🚫",
    "REPORT": "📋",
    "LEVERAGE": "⚡",
    "GRADE_A": "🏆",
    "GRADE_B": "🥈",
    "GRADE_C": "🥉",
    "DIVERGENCE": "↩️",
    "PATTERN": "🕯️",
    "S_R": "📊",
    "SESSION": "🌍",
    "CHEAT": "📋",
    "CONDITION": "✅",
    "CANDLE": "🕯️",
    "REVERSAL": "↩️",
}


class TelegramBot:
    """
    Telegram bot for Super TDI + MACD + Super Bollinger Bands strategy.
    Displays cheat sheet, conditions, MACD confirmation, and AI insights.
    """

    def __init__(self):
        self.token = config.telegram.bot_token
        self.chat_id = config.telegram.chat_id
        self.enabled = bool(self.token and self.token != "your_telegram_bot_token")
        self.bot = None
        self.last_message_time = 0
        self.min_interval = 1

        self.session = None
        self._init_session()

        self.TRADING_FEE = config.strategy.fee_impact if hasattr(config.strategy, 'fee_impact') else 0.0011

        # TDI Levels (Super TDI)
        self.OVERSOLD = config.strategy.tdi_oversold if hasattr(config.strategy, 'tdi_oversold') else 25.0
        self.SOFT_BUY = config.strategy.tdi_soft_buy if hasattr(config.strategy, 'tdi_soft_buy') else 35.0
        self.CENTER_LINE = config.strategy.tdi_center_line if hasattr(config.strategy, 'tdi_center_line') else 50.0
        self.SOFT_SELL = config.strategy.tdi_soft_sell if hasattr(config.strategy, 'tdi_soft_sell') else 65.0
        self.OVERBOUGHT = config.strategy.tdi_overbought if hasattr(config.strategy, 'tdi_overbought') else 75.0

        # MACD Settings
        self.MACD_FAST = getattr(config.strategy, 'macd_fast', 12)
        self.MACD_SLOW = getattr(config.strategy, 'macd_slow', 26)
        self.MACD_SIGNAL = getattr(config.strategy, 'macd_signal', 9)
        self.REQUIRE_MACD = getattr(config.strategy, 'require_macd_confirmation', True)

        # Grade thresholds (lowered for more signals)
        self.GRADE_A_THRESHOLD = getattr(config.strategy, 'grade_a_threshold', 80)
        self.GRADE_B_THRESHOLD = getattr(config.strategy, 'grade_b_threshold', 60)
        self.GRADE_C_THRESHOLD = getattr(config.strategy, 'grade_c_threshold', 50)

        self.HIGH_SCORE = self.GRADE_A_THRESHOLD
        self.MEDIUM_SCORE = self.GRADE_B_THRESHOLD
        self.MIN_SCORE = self.GRADE_C_THRESHOLD

        self._last_health_check = 0
        self._health_check_interval = 60
        self._is_healthy = True

        if self.enabled:
            logger.info(f"{EMOJI['SUCCESS']} TELEGRAM_BOT v3.4.2: Initialized with chat_id: {self.chat_id}")
            logger.info(f"  Strategy: Super TDI + MACD + Super Bollinger Bands")
            logger.info(f"  MACD: Fast={self.MACD_FAST}, Slow={self.MACD_SLOW}, Signal={self.MACD_SIGNAL}")
            self._test_connection()
        else:
            logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Disabled - No API token provided")

    def _init_session(self):
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3, backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.timeout = 10

    def _test_connection(self) -> bool:
        if not self.enabled: return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    bot_info = data.get('result', {})
                    logger.info(f"{EMOJI['SUCCESS']} TELEGRAM_BOT: Connected as @{bot_info.get('username', 'unknown')}")
                    self._is_healthy = True
                    return True
            logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Connection test failed: {response.status_code}")
            self._is_healthy = False
            return False
        except requests.exceptions.Timeout:
            logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Connection test timed out")
            self._is_healthy = False
            return False
        except Exception as e:
            logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Connection test failed: {e}")
            self._is_healthy = False
            return False

    def _check_health(self):
        now = time.time()
        if now - self._last_health_check > self._health_check_interval:
            self._last_health_check = now
            if not self._test_connection():
                self._init_session()
                self._test_connection()

    def send_message(self, message: str) -> bool:
        if not self.enabled or not self.token: return False
        self._check_health()
        if not self._is_healthy:
            self._test_connection()
            if not self._is_healthy:
                telegram_logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Skipping message - connection unhealthy")
                return False
        try:
            now = time.time()
            if now - self.last_message_time < self.min_interval:
                time.sleep(self.min_interval - (now - self.last_message_time))
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            if len(message) > 4096:
                parts = [message[i:i+4096] for i in range(0, len(message), 4096)]
                return all(self._send_single_message(url, part) for part in parts)
            return self._send_single_message(url, message)
        except requests.exceptions.Timeout:
            telegram_logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Send timeout")
            self._is_healthy = False
            return False
        except Exception as e:
            telegram_logger.error(f"{EMOJI['ERROR']} TELEGRAM_BOT: Failed to send message: {e}")
            self._is_healthy = False
            return False

    def _send_single_message(self, url: str, message: str) -> bool:
        try:
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
            response = self.session.post(url, json=payload, timeout=10)
            self.last_message_time = time.time()
            if response.status_code == 200:
                telegram_logger.debug(f"{EMOJI['SUCCESS']} TELEGRAM_BOT: Message sent successfully")
                self._is_healthy = True
                return True
            else:
                telegram_logger.error(f"{EMOJI['ERROR']} TELEGRAM_BOT: Failed: {response.status_code}")
                self._is_healthy = False
                return False
        except requests.exceptions.Timeout:
            telegram_logger.warning(f"{EMOJI['WARNING']} TELEGRAM_BOT: Request timeout")
            self._is_healthy = False
            return False
        except Exception as e:
            telegram_logger.error(f"{EMOJI['ERROR']} TELEGRAM_BOT: Error: {e}")
            self._is_healthy = False
            return False

    # ========== SCORE HELPERS ==========

    def _get_score_stars(self, score: int) -> str:
        if score >= 90: return "⭐⭐⭐⭐⭐"
        elif score >= self.GRADE_A_THRESHOLD: return "⭐⭐⭐⭐"
        elif score >= self.GRADE_B_THRESHOLD: return "⭐⭐⭐"
        elif score >= self.GRADE_C_THRESHOLD: return "⭐⭐"
        else: return "⭐"

    def _get_score_grade(self, score: int) -> str:
        if score >= 90: return "A+"
        elif score >= self.GRADE_A_THRESHOLD: return "A"
        elif score >= self.GRADE_B_THRESHOLD: return "B"
        elif score >= self.GRADE_C_THRESHOLD: return "C"
        else: return "D"

    def _get_grade_emoji(self, score: int) -> str:
        grade = self._get_score_grade(score)
        if grade in ["A+", "A"]: return EMOJI["GRADE_A"]
        elif grade == "B": return EMOJI["GRADE_B"]
        elif grade == "C": return EMOJI["GRADE_C"]
        else: return "📊"

    def _get_score_emoji(self, score: int) -> str:
        if score >= self.GRADE_A_THRESHOLD: return "🟢"
        elif score >= self.GRADE_B_THRESHOLD: return "🟡"
        elif score >= self.GRADE_C_THRESHOLD: return "🟠"
        else: return "🔴"

    # ========== SUPER TDI + MACD + SUPER BB HELPERS ==========

    def _get_tdi_zone_emoji(self, tdi_level: float) -> str:
        if tdi_level <= self.OVERSOLD:
            return "🔴 HARD BUY (2x risk)"
        elif tdi_level <= self.SOFT_BUY:
            return "🟠 SOFT BUY (1x risk)"
        elif tdi_level < self.CENTER_LINE:
            return "🟢 BUY ZONE"
        elif tdi_level < self.SOFT_SELL:
            return "⚪ NO TRADE (WAIT!)"
        elif tdi_level < self.OVERBOUGHT:
            return "🟠 SOFT SELL (1x risk)"
        else:
            return "🔴 HARD SELL (2x risk)"

    def _get_macd_status(self, signal_data: Dict[str, Any]) -> str:
        """Get MACD status for display."""
        macd_bullish = signal_data.get('macd_bullish', False)
        macd_bearish = signal_data.get('macd_bearish', False)
        macd_histogram = signal_data.get('macd_histogram', 0.0)
        macd_above_signal = signal_data.get('macd_above_signal', False)

        if macd_bullish:
            return f"🟢 BULLISH (Hist: {macd_histogram:.4f})"
        elif macd_bearish:
            return f"🔴 BEARISH (Hist: {macd_histogram:.4f})"
        elif macd_above_signal:
            return f"🟡 BULLISH (below signal) (Hist: {macd_histogram:.4f})"
        else:
            return f"⚪ NEUTRAL (Hist: {macd_histogram:.4f})"

    def _format_conditions(self, signal_data: Dict[str, Any]) -> str:
        """Format the 5 conditions checklist."""
        conditions = [
            ('tdi_zone', "TDI in buyer/seller zone"),
            ('tdi_cross', "Green crossed above/below Red"),
            ('bb_touch', "Price touched Bollinger Band"),
            ('candles_shrinking', "Candles getting SMALLER"),
            ('reversal_confirm', "Price moving BACK inside band"),
        ]

        condition_keys = [
            'condition_1_tdi_zone',
            'condition_2_tdi_cross',
            'condition_3_bb_touch',
            'condition_4_candles_shrinking',
            'condition_5_reversal_confirm'
        ]

        lines = []
        for i, (key, desc) in enumerate(conditions):
            status = signal_data.get(condition_keys[i], False)
            emoji = "✅" if status else "⬜"
            lines.append(f"  {emoji} {desc}")

        conditions_met = sum(1 for k in condition_keys if signal_data.get(k, False))
        conditions_total = len(condition_keys)

        result = "\n".join(lines)
        result += f"\n\n📊 <b>Conditions Met: {conditions_met}/{conditions_total}</b>"

        return result

    def _format_cheat_sheet(self, signal_data: Dict[str, Any]) -> str:
        """Format cheat sheet from signal data."""
        cheat_sheet = signal_data.get('cheat_sheet', '')
        if cheat_sheet:
            return cheat_sheet

        direction = signal_data.get('direction', 'UNKNOWN')
        symbol = signal_data.get('symbol', 'UNKNOWN')
        tdi_level = signal_data.get('tdi_level', 50)
        tdi_zone = self._get_tdi_zone_emoji(tdi_level)

        # MACD status
        macd_status = self._get_macd_status(signal_data)
        macd_required = self.REQUIRE_MACD

        lines = []
        lines.append(f"{'🟢' if direction == 'BUY' else '🔴'} <b>{direction} SIGNAL</b> - {symbol}")
        lines.append("📋 <b>Cheat Sheet:</b>")
        lines.append("")

        if direction == 'BUY':
            lines.append(f"1. TDI says: \"{tdi_zone}\" (TDI: {tdi_level:.1f})")
            lines.append(f"2. {'✅' if signal_data.get('condition_2_tdi_cross', False) else '⬜'} Green line {'crossed ABOVE' if signal_data.get('tdi_bullish_cross', False) else 'is ABOVE'} Red line (Bulls taking over)")
            lines.append(f"3. {'✅' if signal_data.get('condition_3_bb_touch', False) else '⬜'} Price {'touched' if signal_data.get('touch_lower', False) else 'near'} the LOWER Bollinger Band (Oversold)")
            lines.append(f"4. {'✅' if signal_data.get('condition_4_candles_shrinking', False) else '⬜'} Candles are getting SMALLER (People giving up)")
            lines.append(f"5. {'✅' if signal_data.get('condition_5_reversal_confirm', False) else '⬜'} Price started moving BACK inside the band (Reversal happening)")
            lines.append(f"6. {'✅' if signal_data.get('macd_bullish', False) else ('❌' if macd_required else '⬜')} MACD is {'BULLISH ✅' if signal_data.get('macd_bullish', False) else ('NEUTRAL' if not macd_required else 'NOT BULLISH ❌')}")
            lines.append("")
            lines.append(f"📊 MACD Status: {macd_status}")
            lines.append("")
            lines.append("✅ ALL 5 (plus MACD if required) = ENTER BUY TRADE")
        elif direction == 'SELL':
            lines.append(f"1. TDI says: \"{tdi_zone}\" (TDI: {tdi_level:.1f})")
            lines.append(f"2. {'✅' if signal_data.get('condition_2_tdi_cross', False) else '⬜'} Green line {'crossed BELOW' if signal_data.get('tdi_bearish_cross', False) else 'is BELOW'} Red line (Bears taking over)")
            lines.append(f"3. {'✅' if signal_data.get('condition_3_bb_touch', False) else '⬜'} Price {'touched' if signal_data.get('touch_upper', False) else 'near'} the UPPER Bollinger Band (Overbought)")
            lines.append(f"4. {'✅' if signal_data.get('condition_4_candles_shrinking', False) else '⬜'} Candles are getting SMALLER (People giving up)")
            lines.append(f"5. {'✅' if signal_data.get('condition_5_reversal_confirm', False) else '⬜'} Price started moving BACK inside the band (Reversal happening)")
            lines.append(f"6. {'✅' if signal_data.get('macd_bearish', False) else ('❌' if macd_required else '⬜')} MACD is {'BEARISH ✅' if signal_data.get('macd_bearish', False) else ('NEUTRAL' if not macd_required else 'NOT BEARISH ❌')}")
            lines.append("")
            lines.append(f"📊 MACD Status: {macd_status}")
            lines.append("")
            lines.append("✅ ALL 5 (plus MACD if required) = ENTER SELL TRADE")

        return "\n".join(lines)

    def _format_features(self, signal_data: Dict[str, Any]) -> str:
        """Format features for display."""
        features = []

        # Divergence
        if signal_data.get('divergence_detected', False):
            div_type = signal_data.get('divergence_type', '').upper()
            features.append(f"{EMOJI['DIVERGENCE']} Divergence: <b>{div_type}</b>")

        # Candle Pattern
        pattern = signal_data.get('candle_pattern', 'NONE')
        if pattern and pattern != 'NONE':
            features.append(f"{EMOJI['PATTERN']} Pattern: <b>{pattern}</b>")

        # S/R
        if signal_data.get('sr_confirmed', False):
            support = signal_data.get('nearest_support', 0)
            resistance = signal_data.get('nearest_resistance', 0)
            features.append(f"{EMOJI['S_R']} S/R Confirmed (S:${support:.4f} R:${resistance:.4f})")

        # BB Squeeze
        if signal_data.get('bb_squeeze', False):
            features.append(f"{EMOJI['BB']} BB Squeeze detected")

        # Session
        session = signal_data.get('session', 'UNKNOWN')
        if session != 'UNKNOWN':
            session_emoji = {"NY": "🇺🇸", "LONDON": "🇬🇧", "ASIAN": "🌏", "LATE": "🌙"}.get(session, "🌍")
            features.append(f"{session_emoji} Session: <b>{session}</b>")

        if not features:
            return ""

        return "\n📊 <b>Signal Features</b>\n" + "\n".join(f"• {f}" for f in features)

    # ==================== SEND SIGNAL - SUPER TDI + MACD + SUPER BB ====================

    def send_signal(self, **kwargs) -> bool:
        """
        Send signal with Super TDI + MACD + Super BB cheat sheet and AI insights.
        """
        if not self.enabled: return False
        try:
            symbol = kwargs.get('symbol', 'UNKNOWN')
            signal_type = kwargs.get('signal_type', 'UNKNOWN')
            entry_price = kwargs.get('entry_price', 0)
            stop_loss = kwargs.get('stop_loss', 0)
            take_profit = kwargs.get('take_profit', 0)
            confidence = kwargs.get('confidence', 0)
            ai_decision = kwargs.get('ai_decision', 'APPROVE')
            ai_confidence = kwargs.get('ai_confidence', 0)
            rrr = kwargs.get('rrr', 0)
            quality_score = kwargs.get('quality_score', 50)
            tdi_level = kwargs.get('tdi_level', 50)
            tdi_zone = kwargs.get('tdi_zone', 'NEUTRAL')
            signal_strength = kwargs.get('signal_strength', 'SOFT')
            risk_multiplier = kwargs.get('risk_multiplier', 1.0)
            conditions_met = kwargs.get('conditions_met', 0)
            conditions_total = kwargs.get('conditions_total', 5)

            # MACD fields
            macd_bullish = kwargs.get('macd_bullish', False)
            macd_bearish = kwargs.get('macd_bearish', False)
            macd_histogram = kwargs.get('macd_histogram', 0.0)

            total_score = kwargs.get('total_score', 0)
            grade = kwargs.get('grade', self._get_score_grade(total_score))

            # Get cheat sheet
            cheat_sheet = kwargs.get('cheat_sheet', '')
            if not cheat_sheet:
                cheat_sheet = self._format_cheat_sheet(kwargs)

            # Calculate percentages
            if signal_type == "BUY":
                tp_pct = ((take_profit - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                sl_pct = ((entry_price - stop_loss) / entry_price) * 100 if entry_price > 0 else 0
            else:
                tp_pct = ((entry_price - take_profit) / entry_price) * 100 if entry_price > 0 else 0
                sl_pct = ((stop_loss - entry_price) / entry_price) * 100 if entry_price > 0 else 0

            fee = self.TRADING_FEE
            entry_fee = entry_price * fee
            exit_fee = entry_price * fee
            total_fee = entry_fee + exit_fee
            fee_pct = fee * 2 * 100
            net_tp_pct = tp_pct - fee_pct
            net_sl_pct = sl_pct + fee_pct

            # AI reasoning
            ai_reasoning = kwargs.get('ai_reasoning', '')
            if not ai_reasoning or ai_reasoning.strip() == '':
                ai_reasoning = f"Signal validated by AI. {conditions_met}/{conditions_total} conditions met."

            # Grade display
            grade_emoji = self._get_grade_emoji(total_score)
            grade_display = f"{grade_emoji} Grade {grade}"

            # MACD status
            macd_status = self._get_macd_status(kwargs)
            macd_emoji = "🟢" if macd_bullish else ("🔴" if macd_bearish else "⚪")
            macd_required = self.REQUIRE_MACD

            # Signal emoji
            signal_emoji = "🟢" if signal_type == "BUY" else "🔴"

            # Build message with cheat sheet as primary content
            message = f"""
{signal_emoji} <b>{signal_type} SIGNAL</b> | <b>{symbol}</b> {grade_emoji}

{cheat_sheet}

📊 <b>Trade Parameters</b>
• Entry: <code>${entry_price:.6f}</code>
• SL: <code>${stop_loss:.6f}</code> (<b>-{sl_pct:.2f}%</b>)
• TP: <code>${take_profit:.6f}</code> (<b>+{tp_pct:.2f}%</b>)
• RRR: <b>{rrr:.1f}</b>
• Confidence: <b>{confidence*100:.1f}%</b>
• Strength: <b>{'🔴 HARD' if signal_strength == 'HARD' else '🟡 SOFT'}</b> ({risk_multiplier}x risk)

📈 <b>TDI Analysis</b>
• Level: <b>{tdi_level:.1f}</b>
• Zone: <b>{self._get_tdi_zone_emoji(tdi_level)}</b>

📊 <b>MACD Analysis</b>
• Status: <b>{macd_status}</b>
• Required: <b>{'✅' if macd_required else '❌'} {macd_required}</b>
• Histogram: <b>{macd_histogram:.4f}</b>

💰 <b>Fee Impact</b>
• Entry Fee: <code>${entry_fee:.4f}</code>
• Exit Fee: <code>${exit_fee:.4f}</code>
• Total Fee: <code>${total_fee:.4f}</code> ({fee_pct:.2f}%)
• <b>Net TP: +{net_tp_pct:.2f}%</b>
• <b>Net SL: -{net_sl_pct:.2f}%</b>

{self._format_features(kwargs)}

🤖 <b>AI Analysis</b>
• Decision: <b>{ai_decision}</b>
• Confidence: <b>{ai_confidence*100:.1f}%</b>
• Reasoning: {ai_reasoning}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

            # Truncate if too long
            if len(message) > 4000:
                message = message[:4000] + "\n\n... (truncated)"

            return self.send_message(message)

        except Exception as e:
            telegram_logger.error(f"{EMOJI['ERROR']} Failed to send signal: {e}")
            return False

    # ==================== SEND RESULT ====================

    def send_result(self, **kwargs) -> bool:
        """
        Send trade result with Super TDI + MACD + Super BB details.
        """
        if not self.enabled: return False
        try:
            symbol = kwargs.get('symbol', 'UNKNOWN')
            signal_type = kwargs.get('signal_type', 'UNKNOWN')
            entry_price = kwargs.get('entry_price', 0)
            exit_price = kwargs.get('exit_price', 0)
            pnl = kwargs.get('pnl', 0)
            pnl_percent = kwargs.get('pnl_percent', 0)
            status = kwargs.get('status', 'UNKNOWN')
            bars_held = kwargs.get('bars_held', 0)
            fees = kwargs.get('fees', 0)
            confidence = kwargs.get('confidence', 0)
            tdi_level = kwargs.get('tdi_level', 0)
            rrr = kwargs.get('rrr', 0)
            signal_strength = kwargs.get('signal_strength', 'SOFT')
            risk_multiplier = kwargs.get('risk_multiplier', 1.0)
            total_score = kwargs.get('total_score', 0)
            grade = kwargs.get('grade', self._get_score_grade(total_score))
            conditions_met = kwargs.get('conditions_met', 0)
            conditions_total = kwargs.get('conditions_total', 5)

            entry_time = kwargs.get('entry_time')
            exit_time = kwargs.get('exit_time')

            status_str = str(status).upper()
            if 'PROFIT' in status_str:
                emoji, status_text = EMOJI['PROFIT'], "✅ PROFIT"
            elif 'LOSS' in status_str:
                emoji, status_text = EMOJI['LOSS'], "❌ LOSS"
            elif 'BREAK' in status_str:
                emoji, status_text = "⚖️", "⏹️ BREAK EVEN"
            elif 'EXPIRED' in status_str:
                emoji, status_text = "⌛", "⏰ EXPIRED"
            else:
                emoji, status_text = "📊", f"STATUS: {status}"

            duration = "Unknown"
            if entry_time and exit_time:
                duration = self._format_duration(str(entry_time), str(exit_time))
            elif entry_time:
                duration = self._format_duration(str(entry_time), datetime.now().isoformat())
                duration = f"~{duration}"

            entry_display = self._format_time(str(entry_time)) if entry_time else "Unknown"
            exit_display = self._format_time(str(exit_time)) if exit_time else datetime.now().strftime('%H:%M:%S')
            entry_date = self._format_date(str(entry_time)) if entry_time else ""
            exit_date = self._format_date(str(exit_time)) if exit_time else ""

            pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
            strength_emoji = "🔴" if signal_strength == "HARD" else "🟡"
            strength_text = "HARD" if signal_strength == "HARD" else "SOFT"
            grade_emoji = self._get_grade_emoji(total_score)

            score_line = ""
            if total_score > 0:
                stars = self._get_score_stars(total_score)
                score_line = f"\n• Signal Score: <b>{stars} {total_score}/100 ({grade_emoji} Grade {grade})</b>"

            message = f"""
{emoji} <b>Trade Result</b> | <b>{symbol}</b> {grade_emoji}

📊 <b>Signal Info</b>
• Type: <b>{signal_type}</b>
• Entry: <code>${entry_price:.6f}</code> ({entry_display}{entry_date})
• Exit: <code>${exit_price:.6f}</code> ({exit_display}{exit_date})
• Status: <b>{status_text}</b>
• Duration: <b>{duration}</b>
• Bars Held: <b>{bars_held}</b>
• Strength: <b>{strength_emoji} {strength_text}</b> ({risk_multiplier}x risk)
• Conditions: <b>{conditions_met}/{conditions_total}</b>{score_line}

💰 <b>PnL</b>
• PnL: {pnl_emoji} <b>${pnl:.2f}</b> ({pnl_percent:+.2f}%)
• Fees: <code>${fees:.4f}</code>

📊 <b>Signal Quality</b>
• Confidence: <b>{confidence*100:.1f}%</b>
• TDI Level: <b>{tdi_level:.1f}</b>
• RRR: <b>{rrr:.1f}</b>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"{EMOJI['ERROR']} Failed to send result: {e}")
            return False

    # ========== DURATION FORMATTING ==========

    def _format_duration(self, entry_time: str, exit_time: str) -> str:
        if not entry_time or not exit_time:
            return "Unknown"
        try:
            for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S']:
                try:
                    entry_dt = datetime.strptime(str(entry_time).replace('Z', '').split('+')[0].split('.')[0] if '.' not in str(entry_time) else str(entry_time).replace('Z', '').split('+')[0], fmt)
                    break
                except: continue
            else:
                entry_dt = datetime.fromisoformat(str(entry_time).replace('Z', '+00:00').split('+')[0])

            for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S']:
                try:
                    exit_dt = datetime.strptime(str(exit_time).replace('Z', '').split('+')[0].split('.')[0] if '.' not in str(exit_time) else str(exit_time).replace('Z', '').split('+')[0], fmt)
                    break
                except: continue
            else:
                exit_dt = datetime.fromisoformat(str(exit_time).replace('Z', '+00:00').split('+')[0])

            duration = exit_dt - entry_dt
            total_seconds = abs(duration.total_seconds())

            if total_seconds < 60: return f"{int(total_seconds)}s"
            elif total_seconds < 3600:
                return f"{int(total_seconds // 60)}m {int(total_seconds % 60)}s"
            elif total_seconds < 86400:
                hours = int(total_seconds // 3600); minutes = int((total_seconds % 3600) // 60)
                return f"{hours}h {minutes}m"
            else:
                days = int(total_seconds // 86400); hours = int((total_seconds % 86400) // 3600)
                return f"{days}d {hours}h"
        except Exception as e:
            telegram_logger.debug(f"Duration format error: {e}")
            return "Unknown"

    def _format_time(self, time_str: str) -> str:
        if not time_str: return "Unknown"
        try:
            dt = datetime.fromisoformat(str(time_str).replace('Z', '+00:00').split('+')[0])
            return dt.strftime('%H:%M:%S')
        except:
            try:
                dt = datetime.strptime(str(time_str)[:19], '%Y-%m-%dT%H:%M:%S')
                return dt.strftime('%H:%M:%S')
            except:
                return str(time_str)[:19] if len(str(time_str)) > 10 else "Unknown"

    def _format_date(self, time_str: str) -> str:
        if not time_str: return ""
        try:
            dt = datetime.fromisoformat(str(time_str).replace('Z', '+00:00').split('+')[0])
            return dt.strftime(' (%Y-%m-%d %H:%M)')
        except:
            try:
                dt = datetime.strptime(str(time_str)[:19], '%Y-%m-%dT%H:%M:%S')
                return dt.strftime(' (%Y-%m-%d %H:%M)')
            except: return ""

    # ==================== STARTUP / SHUTDOWN / HEARTBEAT ====================

    def send_startup_message(self, symbols: List[str], config_info: Dict) -> bool:
        if not self.enabled: return False
        try:
            macd_fast = config_info.get('macd_settings', {}).get('fast', 12)
            macd_slow = config_info.get('macd_settings', {}).get('slow', 26)
            macd_signal = config_info.get('macd_settings', {}).get('signal', 9)
            macd_required = config_info.get('macd_required', True)

            message = f"""
🚀 <b>Trading Bot Started</b> - Super TDI + MACD + Super BB v3.4.2

<b>Strategy</b>: Super TDI + MACD + Super Bollinger Bands
<b>Environment</b>: {config_info.get('environment', 'production')}
<b>Symbols</b>: {len(symbols)}
<b>Timeframe</b>: {config_info.get('timeframe', '5m')}
<b>LTF</b>: {config_info.get('ltf_timeframe', '1m')} | <b>HTF</b>: {config_info.get('htf_timeframe', '1h')} (Context Only)
<b>AI</b>: {'✅' if config_info.get('ai_enabled', True) else '❌'}
<b>Min Conditions</b>: {config_info.get('min_conditions', 3)}/5
<b>RRR Range</b>: {config_info.get('rrr_range', '1.5-4.0')}

<b>MACD Settings:</b>
• Fast: {macd_fast}
• Slow: {macd_slow}
• Signal: {macd_signal}
• Required: {'✅' if macd_required else '❌'}

<b>Super TDI Levels:</b>
• Hard Buy: ≤25 (2x risk)
• Soft Buy: 25-35 (1x risk)
• NO TRADE: 50-65 (WAIT!)
• Soft Sell: 65-75 (1x risk)
• Hard Sell: ≥75 (2x risk)

<b>Super BB:</b>
• Period: {config_info.get('bb_period', 34)}
• Deviation: {config_info.get('bb_deviation', 1.75)}

Bot is now monitoring...
"""
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"Startup message error: {e}")
            return False

    def send_shutdown_message(self, stats: Dict) -> bool:
        if not self.enabled: return False
        try:
            signals = stats.get('signals_generated', 0)
            approved = stats.get('ai_approved', 0)
            rejected = stats.get('ai_rejected', 0)
            pnl = stats.get('total_pnl', 0)
            avg_rrr = stats.get('avg_rrr', 0)

            message = f"""
⚠️ <b>Trading Bot Stopped</b> - Super TDI + MACD + Super BB v3.4.2

<b>Summary</b>
• Signals: {signals}
• AI Approved: {approved}
• AI Rejected: {rejected}
• PnL: ${pnl:.2f}
• Avg RRR: {avg_rrr:.1f}
"""
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"Shutdown message error: {e}")
            return False

    def send_heartbeat(self, stats: Dict) -> bool:
        if not self.enabled: return False
        try:
            active = stats.get('active_signals', 0)
            pnl = stats.get('total_pnl', 0)
            signals = stats.get('signals_generated', 0)

            message = f"""
💚 <b>Bot Heartbeat</b> - Super TDI + MACD + Super BB
Active: {active} | Signals: {signals} | PnL: ${pnl:.2f}
"""
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"Heartbeat error: {e}")
            return False

    def send_error(self, error: str, details: Optional[Dict] = None) -> bool:
        if not self.enabled: return False
        try:
            message = f"❌ <b>Error</b>\n{error}"
            if details:
                message += f"\n\n<code>{json.dumps(details, indent=2)[:500]}</code>"
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"Error message error: {e}")
            return False

    def send_condition_report(self, symbol: str, conditions: Dict, conditions_met: int) -> bool:
        """Send a report of which conditions are met."""
        if not self.enabled: return False
        try:
            lines = []
            lines.append(f"📋 <b>Condition Report</b> - {symbol}")
            lines.append("")

            condition_names = [
                "1. TDI in buyer/seller zone",
                "2. Green crossed above/below Red",
                "3. Price touched Bollinger Band",
                "4. Candles getting SMALLER",
                "5. Price moving BACK inside band"
            ]

            for i, name in enumerate(condition_names):
                key = f"condition_{i+1}"
                status = conditions.get(key, False)
                emoji = "✅" if status else "⬜"
                lines.append(f"{emoji} {name}")

            lines.append("")
            lines.append(f"<b>Conditions Met: {conditions_met}/5</b>")

            if conditions_met >= 4:
                lines.append("🎯 <b>STRONG SIGNAL - Ready to trade!</b>")
            elif conditions_met >= 3:
                lines.append("📊 <b>Good Signal - Consider entry</b>")
            else:
                lines.append("⏳ <b>Not enough conditions - WAIT</b>")

            return self.send_message("\n".join(lines))
        except Exception as e:
            telegram_logger.error(f"Condition report error: {e}")
            return False

    def send_macd_report(self, symbol: str, macd_data: Dict) -> bool:
        """Send MACD status report."""
        if not self.enabled: return False
        try:
            macd = macd_data.get('macd', 0)
            signal = macd_data.get('signal', 0)
            histogram = macd_data.get('histogram', 0)
            bullish = macd_data.get('bullish', False)
            bearish = macd_data.get('bearish', False)
            above_signal = macd_data.get('above_signal', False)

            status = "🟢 BULLISH" if bullish else "🔴 BEARISH" if bearish else "⚪ NEUTRAL"

            message = f"""
📊 <b>MACD Report</b> - {symbol}

• MACD Line: <b>{macd:.4f}</b>
• Signal Line: <b>{signal:.4f}</b>
• Histogram: <b>{histogram:.4f}</b>
• Status: <b>{status}</b>
• Above Signal: <b>{'✅' if above_signal else '❌'}</b>

<b>Interpretation:</b>
{f'🟢 MACD above Signal - BULLISH momentum' if above_signal else '🔴 MACD below Signal - BEARISH momentum'}
{f'📈 Histogram rising - Momentum increasing' if histogram > 0 else '📉 Histogram falling - Momentum decreasing'}
"""
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"MACD report error: {e}")
            return False


# Singleton
telegram_bot = TelegramBot()

def send_telegram_message_sync(message: str) -> bool:
    return telegram_bot.send_message(message)

__all__ = ["telegram_bot", "send_telegram_message_sync"]
