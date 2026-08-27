"""
Groq AI Analyzer - Intelligent Signal Validation
Provides AI-powered analysis and reasoning for trade signals.
Version: 3.4.1 - ADDED: MACD awareness for enhanced analysis
"""

import json
import logging
import re
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

from settings import config

logger = logging.getLogger(__name__)

# Try importing Groq
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq library not available. AI features disabled.")


@dataclass
class AIAnalysisResult:
    """AI analysis result."""
    decision: str  # "APPROVE", "REJECT", "WAIT"
    confidence: float  # 0-1
    reasoning: str
    signal_strength: str  # "HARD", "SOFT", "WEAK"
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    suggested_rrr: float
    market_analysis: str
    technical_factors: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    ai_validated: bool = False
    response_time_ms: float = 0
    tokens_used: int = 0
    raw_response: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class GroqAIAnalyzer:
    """
    Groq AI Analyzer for trade signal validation with MACD awareness.

    Uses Groq's LLM to analyze market conditions and validate trade signals.
    Provides human-readable reasoning and risk assessment.
    Version: 3.4.2 - Enhanced with MACD analysis
    """

    def __init__(self):
        self.enabled = False
        self.client = None
        self.model = config.groq.model
        self.temperature = config.groq.temperature

        self._init_client()

        self.cache = {}
        self.cache_ttl = 60  # 1 minute cache
        self.last_request_time = 0
        self.min_request_interval = 2  # 2 seconds between requests

        # TDI thresholds
        self.OVERSOLD = getattr(config.strategy, 'tdi_oversold', 25.0)
        self.SOFT_BUY = getattr(config.strategy, 'tdi_soft_buy', 35.0)
        self.CENTER_LINE = getattr(config.strategy, 'tdi_center_line', 50.0)
        self.SOFT_SELL = getattr(config.strategy, 'tdi_soft_sell', 65.0)
        self.OVERBOUGHT = getattr(config.strategy, 'tdi_overbought', 75.0)

        # MACD Settings
        self.MACD_FAST = getattr(config.strategy, 'macd_fast', 12)
        self.MACD_SLOW = getattr(config.strategy, 'macd_slow', 26)
        self.MACD_SIGNAL = getattr(config.strategy, 'macd_signal', 9)
        self.REQUIRE_MACD = getattr(config.strategy, 'require_macd_confirmation', True)

        # Grade thresholds (lowered for more signals)
        self.GRADE_A_THRESHOLD = getattr(config.strategy, 'grade_a_threshold', 80)
        self.GRADE_B_THRESHOLD = getattr(config.strategy, 'grade_b_threshold', 60)
        self.GRADE_C_THRESHOLD = getattr(config.strategy, 'grade_c_threshold', 50)

        logger.info(f"🤖 AI Analyzer v3.4.2 initialized: {'✅ Enabled' if self.enabled else '❌ Disabled'}")
        if self.enabled:
            logger.info(f"   Model: {self.model}")
            logger.info(f"   Temperature: {self.temperature}")
            logger.info(f"   MACD Aware: ✅ (Fast={self.MACD_FAST}, Slow={self.MACD_SLOW}, Signal={self.MACD_SIGNAL})")

    def _init_client(self):
        """Initialize Groq client."""
        if not GROQ_AVAILABLE:
            self.enabled = False
            return

        try:
            if config.groq.api_key:
                self.client = Groq(api_key=config.groq.api_key)
                self.enabled = config.groq.enabled
                logger.info("Groq AI client initialized successfully")
            else:
                logger.warning("Groq API key not configured")
                self.enabled = False
        except Exception as e:
            logger.error(f"Groq client initialization error: {e}")
            self.enabled = False

    def analyze_signal(self, signal_data: Dict[str, Any]) -> AIAnalysisResult:
        """
        Analyze a trade signal using Groq AI with MACD awareness.

        Args:
            signal_data: Signal data from engine

        Returns:
            AIAnalysisResult with decision and reasoning
        """
        # Check if AI is enabled
        if not self.enabled or not self.client:
            return self._fallback_analysis(signal_data, "AI not enabled")

        # Rate limiting
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval - (now - self.last_request_time))
        self.last_request_time = time.time()

        # Build prompt
        prompt = self._build_analysis_prompt(signal_data)

        # Check cache
        cache_key = self._generate_cache_key(signal_data)
        if cache_key in self.cache:
            cache_time, cached_result = self.cache[cache_key]
            if now - cache_time < self.cache_ttl:
                logger.debug("AI analysis cache hit")
                return cached_result

        try:
            start_time = time.time()

            # Call Groq API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=500,
            )

            response_time = (time.time() - start_time) * 1000

            # Parse response
            result = self._parse_response(response.choices[0].message.content, signal_data)
            result.response_time_ms = response_time
            result.raw_response = response.choices[0].message.content
            result.ai_validated = True

            if hasattr(response, 'usage'):
                result.tokens_used = getattr(response.usage, 'total_tokens', 0)

            # Cache result
            self.cache[cache_key] = (time.time(), result)

            logger.info(f"🤖 AI Analysis: {result.decision} | Confidence: {result.confidence:.0%} | {result.response_time_ms:.0f}ms")
            logger.debug(f"   Reasoning: {result.reasoning[:100]}...")

            return result

        except Exception as e:
            logger.error(f"Groq AI analysis error: {e}")
            return self._fallback_analysis(signal_data, f"AI error: {str(e)}")

    def _get_system_prompt(self) -> str:
        """Get system prompt for AI with MACD awareness."""
        return f"""You are a professional crypto trading analyst using the Super TDI + MACD + Super Bollinger Bands strategy.

Your job is to analyze trade signals and provide clear, actionable feedback.

Strategy Rules:
1. BUY Signal Conditions (ALL must be true):
   - TDI in buyer zone (below 50, ideally below 35 for soft buy, below 25 for hard buy)
   - Green line (fast MA) above Red line (slow MA) - bulls in control
   - Price touches or near lower Bollinger Band (oversold)
   - Candles getting smaller (momentum loss)
   - Price moving back inside band (reversal confirmation)
   - MACD bullish (MACD line above Signal line, histogram rising)

2. SELL Signal Conditions (ALL must be true):
   - TDI in seller zone (above 50, ideally above 65 for soft sell, above 75 for hard sell)
   - Green line (fast MA) below Red line (slow MA) - bears in control
   - Price touches or near upper Bollinger Band (overbought)
   - Candles getting smaller (momentum loss)
   - Price moving back inside band (reversal confirmation)
   - MACD bearish (MACD line below Signal line, histogram falling)

3. TDI Zones:
   - ≤ 25: HARD BUY (2x risk) - Extreme oversold
   - 25-35: SOFT BUY (1x risk) - Oversold
   - 35-50: BUY ZONE - Getting oversold
   - 50: NO TRADE - Center line, wait
   - 50-65: NO TRADE - Neutral zone
   - 65-75: SOFT SELL (1x risk) - Overbought
   - ≥ 75: HARD SELL (2x risk) - Extreme overbought

4. MACD Rules:
   - MACD Settings: Fast={self.MACD_FAST}, Slow={self.MACD_SLOW}, Signal={self.MACD_SIGNAL}
   - Bullish: MACD line above Signal line, histogram positive and rising
   - Bearish: MACD line below Signal line, histogram negative and falling
   - MACD confirmation is {"REQUIRED" if self.REQUIRE_MACD else "RECOMMENDED"}

Return your analysis as JSON with these fields:
{{
    "decision": "APPROVE" or "REJECT" or "WAIT",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation (max 30 words)",
    "signal_strength": "HARD" or "SOFT" or "WEAK",
    "risk_level": "LOW" or "MEDIUM" or "HIGH",
    "suggested_rrr": 1.5-4.0,
    "market_analysis": "Brief market context (max 20 words)",
    "technical_factors": ["factor1", "factor2"],
    "risk_factors": ["risk1", "risk2"]
}}

Be concise and professional. Focus on the key technical factors including MACD."""

    def _build_analysis_prompt(self, signal_data: Dict[str, Any]) -> str:
        """Build the analysis prompt with MACD data."""
        direction = signal_data.get('direction', 'UNKNOWN')
        symbol = signal_data.get('symbol', 'UNKNOWN')
        tdi_level = signal_data.get('tdi_level', 50)
        tdi_zone = signal_data.get('tdi_zone', 'UNKNOWN')
        tdi_zone_desc = signal_data.get('tdi_zone_description', '')
        bb_position = signal_data.get('bb_position', 0.5)
        touch_lower = signal_data.get('touch_lower', False)
        touch_upper = signal_data.get('touch_upper', False)
        candles_shrinking = signal_data.get('candles_shrinking', False)
        reversal_confirm = signal_data.get('reversal_confirm', False)
        bullish_cross = signal_data.get('tdi_bullish_cross', False)
        bearish_cross = signal_data.get('tdi_bearish_cross', False)
        confidence = signal_data.get('confidence', 0.5)
        signal_strength = signal_data.get('signal_strength', 'SOFT')
        reason = signal_data.get('reason', '')

        # MACD data
        macd_bullish = signal_data.get('macd_bullish', False)
        macd_bearish = signal_data.get('macd_bearish', False)
        macd_histogram = signal_data.get('macd_histogram', 0.0)
        macd_above_signal = signal_data.get('macd_above_signal', False)
        macd_required = self.REQUIRE_MACD

        prompt = f"""
Analyze this {direction} trade signal for {symbol}:

Signal Details:
- Direction: {direction}
- TDI Level: {tdi_level:.1f} ({tdi_zone})
- TDI Zone Description: {tdi_zone_desc}
- Green line above Red: {'YES' if bullish_cross else 'NO'}
- Green line below Red: {'YES' if bearish_cross else 'NO'}
- BB Position: {bb_position:.0%}
- Touch Lower BB: {'YES' if touch_lower else 'NO'}
- Touch Upper BB: {'YES' if touch_upper else 'NO'}
- Candles Shrinking: {'YES' if candles_shrinking else 'NO'}
- Reversal Confirmed: {'YES' if reversal_confirm else 'NO'}
- Signal Confidence: {confidence:.0%}
- Signal Strength: {signal_strength}
- Strategy Reason: {reason}

MACD Analysis:
- MACD Settings: Fast={self.MACD_FAST}, Slow={self.MACD_SLOW}, Signal={self.MACD_SIGNAL}
- MACD Bullish: {'YES' if macd_bullish else 'NO'}
- MACD Bearish: {'YES' if macd_bearish else 'NO'}
- MACD Histogram: {macd_histogram:.4f}
- MACD above Signal: {'YES' if macd_above_signal else 'NO'}
- MACD Required: {'YES' if macd_required else 'NO'}

Please analyze if this is a valid trade signal based on the Super TDI + MACD + Super BB strategy rules.
Consider all conditions including MACD confirmation and provide your recommendation.
"""

        return prompt

    def _parse_response(self, response: str, signal_data: Dict[str, Any]) -> AIAnalysisResult:
        """Parse AI response."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # Fallback: try to parse entire response
                data = json.loads(response)

            # Extract fields with defaults
            decision = data.get('decision', 'WAIT').upper()
            if decision not in ['APPROVE', 'REJECT', 'WAIT']:
                decision = 'WAIT'

            confidence = min(1.0, max(0.0, float(data.get('confidence', 0.5))))
            reasoning = data.get('reasoning', 'AI analysis completed')
            signal_strength = data.get('signal_strength', 'SOFT').upper()
            risk_level = data.get('risk_level', 'MEDIUM').upper()
            suggested_rrr = float(data.get('suggested_rrr', signal_data.get('rrr', 2.0)))
            market_analysis = data.get('market_analysis', '')
            technical_factors = data.get('technical_factors', [])
            risk_factors = data.get('risk_factors', [])

            # Validate RRR
            suggested_rrr = max(1.0, min(4.0, suggested_rrr))

            return AIAnalysisResult(
                decision=decision,
                confidence=confidence,
                reasoning=reasoning[:200],
                signal_strength=signal_strength,
                risk_level=risk_level,
                suggested_rrr=suggested_rrr,
                market_analysis=market_analysis[:150],
                technical_factors=technical_factors[:5],
                risk_factors=risk_factors[:5],
                ai_validated=True,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")
            return self._fallback_analysis(signal_data, "AI response parsing failed")
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return self._fallback_analysis(signal_data, f"Parse error: {str(e)}")

    def _fallback_analysis(self, signal_data: Dict[str, Any], reason: str) -> AIAnalysisResult:
        """Fallback analysis when AI is unavailable with MACD awareness."""
        direction = signal_data.get('direction', 'UNKNOWN')
        tdi_level = signal_data.get('tdi_level', 50)
        macd_bullish = signal_data.get('macd_bullish', False)
        macd_bearish = signal_data.get('macd_bearish', False)
        macd_required = self.REQUIRE_MACD

        # Simple rules-based fallback with MACD
        if direction == 'BUY':
            # Check MACD condition
            macd_ok = macd_bullish or not macd_required

            if tdi_level < self.SOFT_BUY and macd_ok:
                decision = 'APPROVE'
                confidence = 0.8
                signal_strength = 'HARD' if tdi_level < self.OVERSOLD else 'SOFT'
            elif tdi_level < self.CENTER_LINE and macd_ok:
                decision = 'APPROVE'
                confidence = 0.7
                signal_strength = 'SOFT'
            elif not macd_ok:
                decision = 'WAIT'
                confidence = 0.4
                signal_strength = 'WEAK'
                reasoning = f"MACD not bullish (required: {macd_required})"
            else:
                decision = 'REJECT'
                confidence = 0.5
                signal_strength = 'WEAK'
                reasoning = f"TDI {tdi_level:.1f} not in buy zone"

        elif direction == 'SELL':
            # Check MACD condition
            macd_ok = macd_bearish or not macd_required

            if tdi_level > self.SOFT_SELL and macd_ok:
                decision = 'APPROVE'
                confidence = 0.8
                signal_strength = 'HARD' if tdi_level > self.OVERBOUGHT else 'SOFT'
            elif tdi_level > self.CENTER_LINE and macd_ok:
                decision = 'APPROVE'
                confidence = 0.7
                signal_strength = 'SOFT'
            elif not macd_ok:
                decision = 'WAIT'
                confidence = 0.4
                signal_strength = 'WEAK'
                reasoning = f"MACD not bearish (required: {macd_required})"
            else:
                decision = 'REJECT'
                confidence = 0.5
                signal_strength = 'WEAK'
                reasoning = f"TDI {tdi_level:.1f} not in sell zone"
        else:
            decision = 'WAIT'
            confidence = 0.0
            signal_strength = 'WEAK'

        # Build reasoning if not set
        if 'reasoning' not in locals():
            reasoning = f"Fallback analysis: {reason}. TDI: {tdi_level:.1f}"

        return AIAnalysisResult(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning[:200],
            signal_strength=signal_strength,
            risk_level='MEDIUM',
            suggested_rrr=signal_data.get('rrr', 2.0),
            market_analysis='Rules-based fallback analysis',
            technical_factors=[
                f'TDI level: {tdi_level:.1f}',
                f'MACD: {"Bullish" if macd_bullish else "Bearish" if macd_bearish else "Neutral"}'
            ],
            risk_factors=['AI analysis unavailable'],
            ai_validated=False,
        )

    def _generate_cache_key(self, signal_data: Dict[str, Any]) -> str:
        """Generate cache key for signal with MACD awareness."""
        key_parts = [
            signal_data.get('symbol', ''),
            signal_data.get('direction', ''),
            f"{signal_data.get('tdi_level', 0):.1f}",
            signal_data.get('tdi_zone', ''),
            str(signal_data.get('touch_lower', False)),
            str(signal_data.get('touch_upper', False)),
            str(signal_data.get('reversal_confirm', False)),
            str(signal_data.get('macd_bullish', False)),
            str(signal_data.get('macd_bearish', False)),
            f"{signal_data.get('macd_histogram', 0):.4f}",
        ]
        return "_".join(key_parts)

    def analyze_macd_signal(self, symbol: str, macd_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze MACD signal specifically.

        Args:
            symbol: Trading symbol
            macd_data: MACD data from indicators

        Returns:
            Analysis result with MACD interpretation
        """
        if not self.enabled:
            return {
                'enabled': False,
                'signal': 'NEUTRAL',
                'confidence': 0.5,
                'reasoning': 'AI not enabled for MACD analysis'
            }

        macd = macd_data.get('macd', 0)
        signal = macd_data.get('signal', 0)
        histogram = macd_data.get('histogram', 0)
        bullish = macd_data.get('bullish', False)
        bearish = macd_data.get('bearish', False)

        prompt = f"""
Analyze the MACD indicator for {symbol}:

MACD Data:
- MACD Line: {macd:.4f}
- Signal Line: {signal:.4f}
- Histogram: {histogram:.4f}
- Bullish: {'YES' if bullish else 'NO'}
- Bearish: {'YES' if bearish else 'NO'}

Please provide a brief MACD analysis with:
1. Current signal (BUY/SELL/NEUTRAL)
2. Confidence (0-1)
3. Brief reasoning (max 30 words)
4. Key observation

Return JSON:
{{
    "signal": "BUY" or "SELL" or "NEUTRAL",
    "confidence": 0.0-1.0,
    "reasoning": "brief reasoning",
    "observation": "key observation"
}}
"""

        try:
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional MACD analyst. Be concise and accurate."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200,
            )

            response_time = (time.time() - start_time) * 1000

            # Parse response
            json_match = re.search(r'\{.*\}', response.choices[0].message.content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    'enabled': True,
                    'signal': data.get('signal', 'NEUTRAL'),
                    'confidence': min(1.0, max(0.0, float(data.get('confidence', 0.5)))),
                    'reasoning': data.get('reasoning', ''),
                    'observation': data.get('observation', ''),
                    'response_time_ms': response_time,
                }

            return {
                'enabled': True,
                'signal': 'NEUTRAL',
                'confidence': 0.5,
                'reasoning': 'Could not parse MACD analysis',
                'observation': 'N/A',
                'response_time_ms': response_time,
            }

        except Exception as e:
            logger.error(f"MACD analysis error: {e}")
            return {
                'enabled': True,
                'signal': 'NEUTRAL',
                'confidence': 0.5,
                'reasoning': f'Error: {str(e)}',
                'observation': 'N/A',
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get AI analyzer statistics."""
        return {
            'enabled': self.enabled,
            'model': self.model,
            'cache_size': len(self.cache),
            'cache_ttl': self.cache_ttl,
            'available': GROQ_AVAILABLE,
            'macd_aware': True,
            'macd_settings': {
                'fast': self.MACD_FAST,
                'slow': self.MACD_SLOW,
                'signal': self.MACD_SIGNAL,
                'required': self.REQUIRE_MACD,
            },
            'version': '3.4.2'
        }


# Singleton
ai_analyzer = GroqAIAnalyzer()
