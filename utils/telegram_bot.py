"""
Telegram Bot for Trading Signals - HYBRID STRATEGY.
UPDATED v3.3.0: Added Divergence, Candle Patterns, S/R, Session Filtering display
Version: 3.3.0 - ENHANCED: New feature display in signal messages
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
    "MSS": "🔄",
    "FVG": "📉",
    "LIQUIDITY": "💧",
    "HEALTH": "💚",
    "RRR": "📈",
    "AI": "🤖",
    "CONFLICT": "⚔️",
    "HTF": "📊",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "BREAK": "⏹️",
    "EXPIRED": "⌛",
    "HARD": "🔴",
    "SOFT": "🟡",
    "TDI": "📈",
    "BB": "📊",
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
    # NEW v3.3.0
    "DIVERGENCE": "↩️",
    "PATTERN": "🕯️",
    "S_R": "📊",
    "SESSION": "🌍",
}


class TelegramBot:
    """
    Telegram bot with v3.3.0 feature display.
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

        self.TRADING_FEE = 0.0011

        self.OVERSOLD = 25.0
        self.SOFT_BUY = 35.0
        self.CENTER_LINE = 50.0
        self.SOFT_SELL = 65.0
        self.OVERBOUGHT = 75.0

        self.GRADE_A_THRESHOLD = 80
        self.GRADE_B_THRESHOLD = 70
        self.GRADE_C_THRESHOLD = 60

        self.HIGH_SCORE = 80
        self.MEDIUM_SCORE = 70
        self.MIN_SCORE = 50

        self._last_health_check = 0
        self._health_check_interval = 60
        self._is_healthy = True

        if self.enabled:
            logger.info(f"{EMOJI['SUCCESS']} TELEGRAM_BOT v3.3.0: Initialized with chat_id: {self.chat_id}")
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
        if score >= 85: return "⭐⭐⭐⭐⭐"
        elif score >= self.GRADE_A_THRESHOLD: return "⭐⭐⭐⭐"
        elif score >= self.GRADE_B_THRESHOLD: return "⭐⭐⭐"
        elif score >= self.GRADE_C_THRESHOLD: return "⭐⭐"
        else: return "⭐"

    def _get_score_grade(self, score: int) -> str:
        if score >= 85: return "A+"
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

    def _format_component_scores(self, component_scores: Dict) -> str:
        if not component_scores: return ""
        lines = []
        label_map = {
            'ltf': ('⏱️ LTF', 35), 'tdi': ('📈 TDI', 25),
            'bb': ('📊 BB', 15), 'volume': ('📊 Volume', 15), 'reversal': ('🕯️ Reversal', 10),
        }
        for key, (label, weight) in label_map.items():
            if key in component_scores:
                score = component_scores[key]
                bar = self._make_progress_bar(score)
                lines.append(f"{label}: <b>{score:.0f}</b>/100 {bar} (weight: {weight}%)")
        return "\n".join(lines)

    def _make_progress_bar(self, value: float, length: int = 8) -> str:
        filled = int(value / 100 * length)
        filled = max(0, min(length, filled))
        empty = length - filled
        bar_char = "🟩" if value >= 80 else "🟨" if value >= 60 else "🟥"
        return f"[{bar_char * filled}{'⬜' * empty}]"

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

    def _get_tdi_zone_emoji(self, tdi_level: float) -> str:
        if tdi_level <= self.OVERSOLD: return "🔴 OVERSOLD"
        elif tdi_level <= self.SOFT_BUY: return "🟠 SOFT BUY"
        elif tdi_level < self.CENTER_LINE: return "🟢 BUY ZONE"
        elif tdi_level < self.SOFT_SELL: return "⚪ NO TRADE"
        elif tdi_level < self.OVERBOUGHT: return "🟠 SOFT SELL"
        else: return "🔴 OVERBOUGHT"

    # ========== NEW v3.3.0: Feature Formatting ==========

    def _format_features(self, signal_data: Dict[str, Any]) -> str:
        """Format v3.3.0 features for display."""
        features = []

        # Divergence
        if signal_data.get('divergence_detected', False):
            div_type = signal_data.get('divergence_type', '').upper()
            div_strength = signal_data.get('divergence_strength', 0.0)
            features.append(f"{EMOJI['DIVERGENCE']} Divergence: <b>{div_type}</b> ({(div_strength*100):.0f}%)")

        # Candle Pattern
        pattern = signal_data.get('candle_pattern', 'NONE')
        if pattern and pattern != 'NONE':
            pattern_conf = signal_data.get('candle_pattern_confidence', 0.0)
            pattern_dir = signal_data.get('candle_pattern_direction', '')
            dir_emoji = "🟢" if pattern_dir == "BUY" else "🔴" if pattern_dir == "SELL" else "⚪"
            features.append(f"{EMOJI['PATTERN']} Pattern: <b>{pattern}</b> {dir_emoji} ({(pattern_conf*100):.0f}%)")

        # S/R
        if signal_data.get('sr_confirmed', False):
            sr_pos = signal_data.get('sr_position', '')
            support = signal_data.get('nearest_support', 0)
            resistance = signal_data.get('nearest_resistance', 0)
            features.append(f"{EMOJI['S_R']} S/R: {sr_pos} (S:${support:.4f} R:${resistance:.4f})")

        # BB Squeeze
        if signal_data.get('bb_squeeze', False):
            squeeze_strength = signal_data.get('bb_squeeze_strength', 0.0)
            squeeze_dir = signal_data.get('bb_squeeze_direction', 'NEUTRAL')
            features.append(f"{EMOJI['BB']} BB Squeeze: <b>{squeeze_dir}</b> ({(squeeze_strength*100):.0f}%)")

        # Session
        session = signal_data.get('session', 'UNKNOWN')
        session_mult = signal_data.get('session_multiplier', 1.0)
        session_emoji = {
            "NY": "🇺🇸",
            "LONDON": "🇬🇧",
            "ASIAN": "🌏",
            "LATE": "🌙",
        }.get(session, "🌍")
        features.append(f"{session_emoji} Session: <b>{session}</b> ({session_mult:.1f}x)")

        if not features:
            return ""

        return "\n\n📊 <b>Signal Features (v3.3.0)</b>\n" + "\n".join(f"• {f}" for f in features)

    # ==================== SEND SIGNAL - UPDATED v3.3.0 ====================

    def send_signal(self, **kwargs) -> bool:
        """
        Send signal with v3.3.0 feature display.
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
            tdi_level = kwargs.get('tdi_level', 0)
            tdi_zone = kwargs.get('tdi_zone', 'NEUTRAL')
            signal_strength = kwargs.get('signal_strength', 'SOFT')
            risk_multiplier = kwargs.get('risk_multiplier', 1.0)

            total_score = kwargs.get('total_score', 0)
            grade = kwargs.get('grade', self._get_score_grade(total_score))
            component_scores = kwargs.get('component_scores', {})
            leverage_data = kwargs.get('leverage_recommendation', {})

            # NEW v3.3.0: Feature data
            divergence_detected = kwargs.get('divergence_detected', False)
            divergence_type = kwargs.get('divergence_type', '')
            candle_pattern = kwargs.get('candle_pattern', 'NONE')
            sr_confirmed = kwargs.get('sr_confirmed', False)
            bb_squeeze = kwargs.get('bb_squeeze', False)
            session = kwargs.get('session', 'UNKNOWN')
            session_multiplier = kwargs.get('session_multiplier', 1.0)

            signal_data = kwargs.get('signal_data', {})
            if signal_data:
                total_score = signal_data.get('total_score', total_score)
                grade = signal_data.get('grade', grade)
                component_scores = signal_data.get('component_scores', component_scores)
                leverage_data = signal_data.get('leverage_recommendation', leverage_data)
                # NEW v3.3.0
                divergence_detected = signal_data.get('divergence_detected', divergence_detected)
                divergence_type = signal_data.get('divergence_type', divergence_type)
                candle_pattern = signal_data.get('candle_pattern', candle_pattern)
                sr_confirmed = signal_data.get('sr_confirmed', sr_confirmed)
                bb_squeeze = signal_data.get('bb_squeeze', bb_squeeze)
                session = signal_data.get('session', session)
                session_multiplier = signal_data.get('session_multiplier', session_multiplier)

            ltf_confirmed = kwargs.get('ltf_confirmed', False)
            ltf_confidence = kwargs.get('ltf_confidence', 0)
            htf_trend = kwargs.get('htf_trend', 'NEUTRAL')
            htf_aligned = kwargs.get('htf_aligned', False)

            # Calculate percentages
            if signal_type == "BUY":
                tp_pct = ((take_profit - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                sl_pct = ((entry_price - stop_loss) / entry_price) * 100 if entry_price > 0 else 0
            else:
                tp_pct = ((entry_price - take_profit) / entry_price) * 100 if entry_price > 0 else 0
                sl_pct = ((stop_loss - entry_price) / entry_price) * 100 if entry_price > 0 else 0

            fee = self.TRADING_FEE
            entry_fee = entry_price * fee; exit_fee = entry_price * fee
            total_fee = entry_fee + exit_fee; fee_pct = fee * 2 * 100
            net_tp_pct = tp_pct - fee_pct; net_sl_pct = sl_pct + fee_pct

            # AI reasoning
            ai_reasoning = kwargs.get('ai_reasoning', '')
            if not ai_reasoning or ai_reasoning == 'No analysis available' or ai_reasoning.strip() == '':
                ltf_status = "confirmed" if ltf_confirmed else "not confirmed"
                htf_status = "aligned" if htf_aligned else "not aligned"
                ai_reasoning = (
                    f"Signal generated with TDI at {tdi_level:.1f} ({tdi_zone}). "
                    f"LTF {ltf_status} ({ltf_confidence*100:.0f}% confidence). "
                    f"HTF {htf_status}. "
                    f"Quality: {quality_score}/100"
                )
                if total_score > 0:
                    ai_reasoning += f", Score: {total_score}/100 (Grade {grade})"
                ai_reasoning += "."

            # Grade display
            grade_emoji = self._get_grade_emoji(total_score)
            grade_display = f"{grade_emoji} Grade {grade}"

            # Leverage section
            if leverage_data:
                leverage_section = f"""
⚡ <b>Leverage Recommendation</b>
• Recommended: <b>{leverage_data.get('recommended_leverage', config.strategy.default_leverage)}x</b>
• Range: <b>{leverage_data.get('min_leverage', 1)}x - {leverage_data.get('max_leverage', 20)}x</b>
• Risk Level: <b>{leverage_data.get('risk_level', 'MEDIUM')}</b>
• Position Size: <b>{leverage_data.get('position_size_percent', 5.0):.1f}%</b>
"""
            else:
                leverage_section = f"""
⚡ <b>Leverage Recommendation</b>
• Recommended: <b>{config.strategy.default_leverage}x</b>
• Range: <b>{config.strategy.min_leverage}x - {config.strategy.max_leverage}x</b>
• Risk Level: <b>MEDIUM</b>
"""

            # Score section
            if total_score > 0:
                stars = self._get_score_stars(total_score)
                score_emoji = self._get_score_emoji(total_score)
                component_display = self._format_component_scores(component_scores)
                quality_text = 'HIGH' if total_score >= self.GRADE_A_THRESHOLD else 'MEDIUM' if total_score >= self.GRADE_B_THRESHOLD else 'LOW'
                score_section = f"""
🎯 <b>Signal Score: {stars} {total_score}/100 ({grade_display})</b>
{score_emoji} Overall Quality: <b>{quality_text}</b>

<b>Score Breakdown:</b>
{component_display}
"""
            else:
                score_section = f"""
📊 <b>Signal Quality</b>
• Quality Score: <b>{quality_score}/100</b>
• Grade: <b>{grade_display}</b>
"""

            # LTF section
            ltf_emoji = "✅" if ltf_confirmed else "❌"
            ltf_section = f"""
⏱️ <b>LTF (5m) Confirmation</b>
• Status: <b>{ltf_emoji} {'Confirmed' if ltf_confirmed else 'Rejected'}</b>
• Confidence: <b>{ltf_confidence*100:.1f}%</b>
"""

            # HTF section
            htf_emoji = "✅" if htf_aligned else "❌"
            htf_section = f"""
📊 <b>HTF (1h) Alignment</b>
• Trend: <b>{htf_trend}</b>
• Aligned: <b>{htf_emoji} {'Yes' if htf_aligned else 'No'}</b>
"""

            # TDI section
            tdi_zone_emoji = self._get_tdi_zone_emoji(tdi_level)
            tdi_section = f"""
📈 <b>TDI Analysis</b>
• Level: <b>{tdi_level:.1f}</b>
• Zone: <b>{tdi_zone_emoji}</b>
"""

            # Strength section
            strength_emoji = "🔴" if signal_strength == "HARD" else "🟡"
            strength_text = "HARD (2x Risk)" if signal_strength == "HARD" else "SOFT (1x Risk)"
            strength_section = f"""
🎯 <b>Signal Strength</b>
• Strength: <b>{strength_emoji} {strength_text}</b>
"""

            # NEW v3.3.0: Feature section
            feature_section = self._format_features({
                'divergence_detected': divergence_detected,
                'divergence_type': divergence_type,
                'candle_pattern': candle_pattern,
                'sr_confirmed': sr_confirmed,
                'bb_squeeze': bb_squeeze,
                'session': session,
                'session_multiplier': session_multiplier,
            })

            signal_emoji = EMOJI['BUY'] if signal_type == "BUY" else EMOJI['SELL']

            # Version badge
            version_badge = "🤖 v3.3.0"

            message = f"""
{signal_emoji} <b>{signal_type} SIGNAL</b> | <b>{symbol}</b> {grade_emoji} {version_badge}

📊 <b>Signal Details</b>
• Action: <b>{signal_type}</b>
• Entry: <code>${entry_price:.6f}</code>
• SL: <code>${stop_loss:.6f}</code> (<b>-{sl_pct:.2f}%</b>)
• TP: <code>${take_profit:.6f}</code> (<b>+{tp_pct:.2f}%</b>)
• RRR: <b>{rrr:.1f}</b>
• Confidence: <b>{confidence*100:.1f}%</b>

💰 <b>Fee Impact</b>
• Entry Fee: <code>${entry_fee:.4f}</code>
• Exit Fee: <code>${exit_fee:.4f}</code>
• Total Fee: <code>${total_fee:.4f}</code> ({fee_pct:.2f}%)
• <b>Net TP: +{net_tp_pct:.2f}%</b>
• <b>Net SL: -{net_sl_pct:.2f}%</b>

{score_section}
{tdi_section}
{strength_section}
{feature_section if feature_section else ""}
{leverage_section}
{htf_section}
{ltf_section}

🤖 <b>AI Analysis</b>
• Decision: <b>{ai_decision}</b>
• Confidence: <b>{ai_confidence*100:.1f}%</b>
• Reasoning:
{ai_reasoning}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            return self.send_message(message)
        except Exception as e:
            telegram_logger.error(f"{EMOJI['ERROR']} Failed to send signal: {e}")
            return False

    # ==================== SEND RESULT - UPDATED v3.3.0 ====================

    def send_result(self, **kwargs) -> bool:
        """
        Send trade result with v3.3.0 feature display.
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

            # NEW v3.3.0
            divergence_detected = kwargs.get('divergence_detected', False)
            candle_pattern = kwargs.get('candle_pattern', 'NONE')
            sr_confirmed = kwargs.get('sr_confirmed', False)
            session = kwargs.get('session', 'UNKNOWN')

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

            # NEW v3.3.0: Feature summary
            feature_parts = []
            if divergence_detected:
                feature_parts.append("DIV")
            if candle_pattern and candle_pattern != 'NONE':
                feature_parts.append(candle_pattern)
            if sr_confirmed:
                feature_parts.append("S/R")
            feature_str = f" | Features: {', '.join(feature_parts)}" if feature_parts else ""

            message = f"""
{emoji} <b>Trade Result</b> | <b>{symbol}</b> {grade_emoji}

📊 <b>Signal Info</b>
• Type: <b>{signal_type}</b>
• Entry: <code>${entry_price:.6f}</code> ({entry_display}{entry_date})
• Exit: <code>${exit_price:.6f}</code> ({exit_display}{exit_date})
• Status: <b>{status_text}</b>
• Duration: <b>{duration}</b>
• Bars Held: <b>{bars_held}</b>
• Strength: <b>{strength_emoji} {strength_text} ({risk_multiplier}x risk)</b>{score_line}{feature_str}

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

    # ==================== STARTUP / SHUTDOWN / HEARTBEAT ====================

    def send_startup_message(self, symbols: List[str], config_info: Dict) -> bool:
        if not self.enabled: return False
        try:
            message = f"""
🚀 <b>Trading Bot Started</b> - Super TDI Strategy v3.3.0

<b>Environment</b>: {config_info.get('environment', 'production')}
<b>Symbols</b>: {len(symbols)}
<b>Timeframe</b>: {config_info.get('timeframe', '15m')}
<b>LTF</b>: {config_info.get('ltf_timeframe', '5m')} | <b>HTF</b>: {config_info.get('htf_timeframe', '1h')}
<b>AI</b>: {'✅' if config_info.get('ai_enabled', True) else '❌'}
<b>RRR Range</b>: {config_info.get('rrr_range', '1.5-4.0')}
<b>Grade A</b>: 80+ | <b>Grade B</b>: 70-79 | <b>Grade C</b>: 60-69 (Rejected)

<b>🆕 v3.3.0 Features:</b>
• Divergence Detection: ✅
• Candle Patterns: ✅
• Support/Resistance: ✅
• BB Squeeze: ✅
• Session Filtering: ✅

Bot is now monitoring...
"""
            return self.send_message(message)
        except Exception as e: return False

    def send_shutdown_message(self, stats: Dict) -> bool:
        if not self.enabled: return False
        try:
            score_approved = stats.get('score_approved', 0); score_rejected = stats.get('score_rejected', 0)
            grade_a = stats.get('grade_a_signals', 0); grade_b = stats.get('grade_b_signals', 0)
            grade_c_rejected = stats.get('grade_c_rejected', 0)
            divergence = stats.get('divergence_signals', 0)
            patterns = stats.get('pattern_signals', 0)
            sr = stats.get('sr_signals', 0)

            message = f"""
⚠️ <b>Trading Bot Stopped</b> - v3.3.0

<b>Signals</b>: {stats.get('signals_generated', 0)} generated, {stats.get('sniper_signals', 0)} executed
<b>PnL</b>: ${stats.get('total_pnl', 0):.2f} | <b>Avg RRR</b>: {stats.get('avg_rrr', 0):.1f}
<b>Grades</b>: A={grade_a}, B={grade_b}, C={grade_c_rejected} (Rejected)
<b>Score</b>: Approved={score_approved}, Rejected={score_rejected}

<b>🆕 v3.3.0 Features:</b>
• Divergence: {divergence}
• Patterns: {patterns}
• S/R: {sr}
"""
            return self.send_message(message)
        except: return False

    def send_heartbeat(self, stats: Dict) -> bool:
        if not self.enabled: return False
        try:
            message = f"""💚 <b>Bot Heartbeat</b> - v3.3.0
Active: {stats.get('active_signals', 0)} | PnL: ${stats.get('total_pnl', 0):.2f}
DIV: {stats.get('divergence_signals', 0)} | PAT: {stats.get('pattern_signals', 0)} | S/R: {stats.get('sr_signals', 0)}"""
            return self.send_message(message)
        except: return False

    def send_error(self, error: str, details: Optional[Dict] = None) -> bool:
        if not self.enabled: return False
        try:
            message = f"❌ <b>Error</b>\n{error}"
            return self.send_message(message)
        except: return False

    def send_conflict_alert(self, symbol: str, conflict_reason: str, quality_score: int, ltf_confirmed: bool, signal_strength: str = "SOFT", total_score: int = 0) -> bool:
        if not self.enabled: return False
        try:
            grade = self._get_score_grade(total_score) if total_score > 0 else "N/A"
            message = f"⚔️ <b>Conflict</b> | {symbol}\n{conflict_reason}\nQuality: {quality_score}/100 | Grade: {grade}"
            return self.send_message(message)
        except: return False

    def send_rejection_report(self, rejection_report: Dict) -> bool:
        if not self.enabled: return False
        try:
            acceptance_rate = rejection_report.get('acceptance_rate', 0)
            total_rejections = rejection_report.get('total_rejections', 0)
            message = f"📋 <b>Rejection Report</b>\nAcceptance Rate: {acceptance_rate}%\nTotal Rejections: {total_rejections}"
            return self.send_message(message)
        except: return False


# Singleton
telegram_bot = TelegramBot()

def send_telegram_message_sync(message: str) -> bool:
    return telegram_bot.send_message(message)

__all__ = ["telegram_bot", "send_telegram_message_sync"]
