"""Dedicated 5-minute UP/DOWN prediction engine."""

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from strategy.bb_detector import BBDetector
from strategy.tdi_detector import TDIDetector

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    symbol: str
    prediction: str
    confidence: float
    bullish_score: float
    bearish_score: float
    tdi_level: float
    macd_bullish: bool
    macd_histogram: float
    bb_position: float
    volume_ratio: float
    htf_trend: str
    score_breakdown: Dict[str, float]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class PredictionEngine:
    """Score the next 5-minute direction using 5m data and context frames."""

    def __init__(self, strategy_config):
        self.tdi_detector = TDIDetector()
        self.bb_detector = BBDetector()
        self.tdi_soft_buy = getattr(strategy_config, "tdi_soft_buy", 32.0)
        self.tdi_soft_sell = getattr(strategy_config, "tdi_soft_sell", 68.0)
        self.min_confidence = 55.0

    def predict(
        self,
        df_5m: pd.DataFrame,
        df_1m: Optional[pd.DataFrame] = None,
        df_context: Optional[pd.DataFrame] = None,
        symbol: str = "UNKNOWN",
    ) -> PredictionResult:
        if df_5m is None or df_5m.empty or len(df_5m) < 20:
            return self._neutral(symbol, "Insufficient 5m data")

        tdi = self.tdi_detector.detect_opportunity(df_5m)
        bb = self.bb_detector.detect_bb_interaction(df_5m)
        macd = self._macd(df_5m)
        volume_ratio = self._volume_ratio(df_5m)
        momentum = self._momentum(df_5m)
        context_trend = self._context_trend(df_context)

        bullish, bearish, breakdown = self._scores(
            tdi, bb, macd, volume_ratio, momentum, context_trend
        )
        total = bullish + bearish
        confidence = abs(bullish - bearish) / max(total, 1.0) * 100
        prediction = "NEUTRAL"
        if confidence >= self.min_confidence:
            prediction = "UP" if bullish > bearish else "DOWN" if bearish > bullish else "NEUTRAL"

        if prediction == "UP" and not macd["bullish"]:
            confidence -= 10
        elif prediction == "DOWN" and not macd["bearish"]:
            confidence -= 10
        if confidence > 60 and volume_ratio <= 1.3:
            confidence -= 5
        confidence = max(0.0, min(100.0, confidence))

        return PredictionResult(
            symbol=symbol,
            prediction=prediction,
            confidence=confidence,
            bullish_score=bullish,
            bearish_score=bearish,
            tdi_level=float(tdi.get("tdi_level", 50.0)),
            macd_bullish=macd["bullish"],
            macd_histogram=float(macd["histogram"]),
            bb_position=float(bb.get("position", 0.5)),
            volume_ratio=volume_ratio,
            htf_trend=context_trend,
            score_breakdown=breakdown,
        )

    def _scores(self, tdi, bb, macd, volume_ratio, momentum, context) -> Tuple[float, float, Dict[str, float]]:
        bullish = bearish = 0.0
        breakdown: Dict[str, float] = {}
        tdi_level = float(tdi.get("tdi_level", 50.0))
        green_above_red = bool(tdi.get("green_above_red", False))
        if tdi_level < self.tdi_soft_buy:
            score = 25.0 * (1 - tdi_level / self.tdi_soft_buy)
            bullish += score * (1.3 if green_above_red else 1.0)
            breakdown["tdi"] = score
        elif tdi_level > self.tdi_soft_sell:
            score = 25.0 * (tdi_level - self.tdi_soft_sell) / (100 - self.tdi_soft_sell)
            bearish += score * (1.3 if not green_above_red else 1.0)
            breakdown["tdi"] = -score
        else:
            score = 10.0
            if green_above_red:
                bullish += score
                breakdown["tdi"] = score
            else:
                bearish += score
                breakdown["tdi"] = -score

        if macd["bullish"]:
            bullish += 20
            breakdown["macd"] = 20
        elif macd["bearish"]:
            bearish += 20
            breakdown["macd"] = -20
        elif macd["histogram"] > 0:
            bullish += 8
            breakdown["macd"] = 8
        else:
            bearish += 8
            breakdown["macd"] = -8

        position = float(bb.get("position", 0.5))
        if position < 0.2:
            score = 15 * (1 - position / 0.2)
            bullish += score
            breakdown["bb"] = score
        elif position > 0.8:
            score = 15 * ((position - 0.8) / 0.2)
            bearish += score
            breakdown["bb"] = -score
        elif position < 0.5:
            bullish += 5
            breakdown["bb"] = 5
        else:
            bearish += 5
            breakdown["bb"] = -5

        if volume_ratio > 1.3:
            score = 10 if volume_ratio <= 2 else 15
            if momentum >= 0:
                bullish += score
                breakdown["volume"] = score
            else:
                bearish += score
                breakdown["volume"] = -score
        elif volume_ratio > 1:
            bullish += 5
            breakdown["volume"] = 5
        else:
            bearish += 5
            breakdown["volume"] = -5

        if context == "BULLISH":
            bullish += 15
            breakdown["context"] = 15
        elif context == "BEARISH":
            bearish += 15
            breakdown["context"] = -15
        else:
            bullish += 5
            bearish += 5
            breakdown["context"] = 0

        momentum_score = min(15, abs(momentum) * 30)
        if momentum >= 0:
            bullish += momentum_score
            breakdown["momentum"] = momentum_score
        else:
            bearish += momentum_score
            breakdown["momentum"] = -momentum_score
        return bullish, bearish, breakdown

    @staticmethod
    def _macd(df: pd.DataFrame) -> Dict[str, Any]:
        last = df.iloc[-1]
        previous = df.iloc[-2] if len(df) > 1 else last
        macd = float(last.get("macd", 0) or 0)
        signal = float(last.get("macd_signal", 0) or 0)
        histogram = float(last.get("macd_histogram", 0) or 0)
        previous_histogram = float(previous.get("macd_histogram", 0) or 0)
        return {
            "bullish": macd > signal and histogram > previous_histogram,
            "bearish": macd < signal and histogram < previous_histogram,
            "histogram": histogram,
        }

    @staticmethod
    def _volume_ratio(df: pd.DataFrame) -> float:
        if "volume" not in df.columns:
            return 1.0
        average = float(df["volume"].tail(20).mean())
        return float(df.iloc[-1].get("volume", 0)) / average if average > 0 else 1.0

    @staticmethod
    def _momentum(df: pd.DataFrame) -> float:
        if len(df) < 3:
            return 0.0
        previous_close = float(df.iloc[-2]["close"])
        change = (float(df.iloc[-1]["close"]) - previous_close) / previous_close if previous_close else 0
        return float(np.clip(change * 20, -1, 1))

    @staticmethod
    def _context_trend(df: Optional[pd.DataFrame]) -> str:
        if df is None or df.empty:
            return "NEUTRAL"
        last = df.iloc[-1]
        ema_fast = last.get("ema7", 0)
        ema_slow = last.get("ema25", 0)
        rsi = last.get("rsi", 50)
        if ema_fast > ema_slow and rsi > 50:
            return "BULLISH"
        if ema_fast < ema_slow and rsi < 50:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _neutral(symbol: str, reason: str) -> PredictionResult:
        logger.debug("NEUTRAL: %s - %s", symbol, reason)
        return PredictionResult(symbol, "NEUTRAL", 0, 0, 0, 50, False, 0, 0.5, 1, "NEUTRAL", {})


__all__ = ["PredictionEngine", "PredictionResult"]
