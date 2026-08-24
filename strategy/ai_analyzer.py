"""
Groq AI Analyzer - Intelligent Signal Validation
Provides AI-powered analysis and reasoning for trade signals.
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
    Groq AI Analyzer for trade signal validation.

    Uses Groq's LLM to analyze market conditions and validate trade signals.
    Provides human-readable reasoning and risk assessment.
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
        self.OVERSOLD = 25.0
        self.SOFT_BUY = 35.0
        self.CENTER_LINE = 50.0
        self.SOFT_SELL = 65.0
        self.OVERBOUGHT = 75.0

        logger.info(f"🤖 AI Analyzer initialized: {'✅ Enabled' if self.enabled else '❌ Disabled'}")
        if self.enabled:
            logger.info(f"   Model: {self.model}")
            logger.info(f"   Temperature: {self.temperature}")

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
        Analyze a trade signal using Groq AI.

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
        """Get system prompt for AI."""
        return """You are a professional crypto trading analyst using the Super TDI + Super Bollinger Bands strategy.

Your job is to analyze trade signals and provide clear, actionable feedback.

Strategy Rules:
1. BUY Signal Conditions (ALL must be true):
   - TDI in buyer zone (below 50, ideally below 35 for soft buy, below 25 for hard buy)
   - Green line (fast MA) above Red line (slow MA) - bulls in control
   - Price touches or near lower Bollinger Band (oversold)
   - Candles getting smaller (momentum loss)
   - Price moving back inside band (reversal confirmation)

2. SELL Signal Conditions (ALL must be true):
   - TDI in seller zone (above 50, ideally above 65 for soft sell, above 75 for hard sell)
   - Green line (fast MA) below Red line (slow MA) - bears in control
   - Price touches or near upper Bollinger Band (overbought)
   - Candles getting smaller (momentum loss)
   - Price moving back inside band (reversal confirmation)

3. TDI Zones:
   - ≤ 25: HARD BUY (2x risk) - Extreme oversold
   - 25-35: SOFT BUY (1x risk) - Oversold
   - 35-50: BUY ZONE - Getting oversold
   - 50: NO TRADE - Center line, wait
   - 50-65: NO TRADE - Neutral zone
   - 65-75: SOFT SELL (1x risk) - Overbought
   - ≥ 75: HARD SELL (2x risk) - Extreme overbought

Return your analysis as JSON with these fields:
{
    "decision": "APPROVE" or "REJECT" or "WAIT",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation (max 30 words)",
    "signal_strength": "HARD" or "SOFT" or "WEAK",
    "risk_level": "LOW" or "MEDIUM" or "HIGH",
    "suggested_rrr": 1.5-4.0,
    "market_analysis": "Brief market context (max 20 words)",
    "technical_factors": ["factor1", "factor2"],
    "risk_factors": ["risk1", "risk2"]
}

Be concise and professional. Focus on the key technical factors."""

    def _build_analysis_prompt(self, signal_data: Dict[str, Any]) -> str:
        """Build the analysis prompt."""
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

Please analyze if this is a valid trade signal based on the Super TDI + Super BB strategy rules.
Consider all 5 conditions and provide your recommendation.
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
        """Fallback analysis when AI is unavailable."""
        direction = signal_data.get('direction', 'UNKNOWN')
        tdi_level = signal_data.get('tdi_level', 50)

        # Simple rules-based fallback
        if direction == 'BUY':
            if tdi_level < self.SOFT_BUY:
                decision = 'APPROVE'
                confidence = 0.8
                signal_strength = 'HARD' if tdi_level < self.OVERSOLD else 'SOFT'
            elif tdi_level < self.CENTER_LINE:
                decision = 'APPROVE'
                confidence = 0.7
                signal_strength = 'SOFT'
            else:
                decision = 'REJECT'
                confidence = 0.5
                signal_strength = 'WEAK'

        elif direction == 'SELL':
            if tdi_level > self.SOFT_SELL:
                decision = 'APPROVE'
                confidence = 0.8
                signal_strength = 'HARD' if tdi_level > self.OVERBOUGHT else 'SOFT'
            elif tdi_level > self.CENTER_LINE:
                decision = 'APPROVE'
                confidence = 0.7
                signal_strength = 'SOFT'
            else:
                decision = 'REJECT'
                confidence = 0.5
                signal_strength = 'WEAK'
        else:
            decision = 'WAIT'
            confidence = 0.0
            signal_strength = 'WEAK'

        return AIAnalysisResult(
            decision=decision,
            confidence=confidence,
            reasoning=f"Fallback analysis: {reason}. Using rules-based evaluation.",
            signal_strength=signal_strength,
            risk_level='MEDIUM',
            suggested_rrr=signal_data.get('rrr', 2.0),
            market_analysis='Rules-based fallback analysis',
            technical_factors=['TDI level: {:.1f}'.format(tdi_level)],
            risk_factors=['AI analysis unavailable'],
            ai_validated=False,
        )

    def _generate_cache_key(self, signal_data: Dict[str, Any]) -> str:
        """Generate cache key for signal."""
        key_parts = [
            signal_data.get('symbol', ''),
            signal_data.get('direction', ''),
            f"{signal_data.get('tdi_level', 0):.1f}",
            signal_data.get('tdi_zone', ''),
            str(signal_data.get('touch_lower', False)),
            str(signal_data.get('touch_upper', False)),
            str(signal_data.get('reversal_confirm', False)),
        ]
        return "_".join(key_parts)

    def get_stats(self) -> Dict[str, Any]:
        """Get AI analyzer statistics."""
        return {
            'enabled': self.enabled,
            'model': self.model,
            'cache_size': len(self.cache),
            'cache_ttl': self.cache_ttl,
            'available': GROQ_AVAILABLE,
        }


# Singleton
ai_analyzer = GroqAIAnalyzer()
