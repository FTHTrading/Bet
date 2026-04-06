"""
Market Consensus Engine
========================
Aggregates model probabilities, implied market probabilities,
and sharp action signals into a unified consensus view.

Output: per-event consensus with edge grade, confidence level,
and a recommended action (BET / LEAN / WAIT / FADE).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConsensusResult:
    event:           str
    sport:           str
    market:          str
    outcome:         str
    model_prob:      float   # our model's estimated win probability
    market_prob:     float   # no-vig market implied probability
    sharp_prob:      Optional[float]  # Pinnacle/sharp-book implied probability
    edge_pct:        float   # model_prob - market_prob
    sharp_edge:      Optional[float]  # model_prob - sharp_prob
    ev_pct:          float
    grade:           str     # A+ / A / B / C / D / F
    action:          str     # BET_NOW / LEAN_YES / WAIT / FADE / SKIP
    confidence:      str     # LOW / MEDIUM / HIGH / VERY_HIGH
    notes:           list[str]

    def to_dict(self) -> dict:
        return {
            "event":       self.event,
            "sport":       self.sport,
            "market":      self.market,
            "outcome":     self.outcome,
            "model_prob":  round(self.model_prob  * 100, 2),
            "market_prob": round(self.market_prob * 100, 2),
            "sharp_prob":  round(self.sharp_prob  * 100, 2) if self.sharp_prob else None,
            "edge_pct":    round(self.edge_pct,   2),
            "sharp_edge":  round(self.sharp_edge, 2) if self.sharp_edge else None,
            "ev_pct":      round(self.ev_pct,     2),
            "grade":       self.grade,
            "action":      self.action,
            "confidence":  self.confidence,
            "notes":       self.notes,
        }


class MarketConsensus:
    """
    Build a consensus recommendation from multi-source probability estimates.
    """

    def analyze(
        self,
        event:        str,
        sport:        str,
        market:       str,
        outcome:      str,
        model_prob:   float,
        market_odds:  float,   # decimal odds from target book
        sharp_odds:   Optional[float] = None,   # Pinnacle / consensus book
        steam_alert:  bool = False,
        rlm_signal:   bool = False,
        injury_impact: float = 0.0,  # negative = hurts our pick
    ) -> ConsensusResult:
        """
        Full consensus analysis for a single bet opportunity.
        """
        market_prob = 1.0 / market_odds if market_odds > 1.0 else 0.5
        sharp_prob  = (1.0 / sharp_odds) if sharp_odds and sharp_odds > 1.0 else None

        edge_pct  = (model_prob - market_prob) * 100
        sharp_edge = ((model_prob - sharp_prob) * 100) if sharp_prob else None

        ev_pct = (model_prob * market_odds - 1) * 100

        notes: list[str] = []

        # injury adjustment
        adjusted_edge = edge_pct + injury_impact * 100
        if injury_impact < -0.02:
            notes.append(f"Injury impact: {injury_impact*100:.1f}% hit to edge")
        if injury_impact > 0.02:
            notes.append(f"Opponent injury: +{injury_impact*100:.1f}% boost")

        # steam signal
        if steam_alert:
            notes.append("Steam move detected — sharp money on this side")
        if rlm_signal:
            notes.append("RLM: public fading this pick → sharp money agrees")

        # sharp vs market gap
        if sharp_prob and abs(sharp_prob - market_prob) > 0.03:
            direction = "efficient" if abs(sharp_prob - model_prob) < abs(market_prob - model_prob) else "overweight"
            notes.append(f"Sharp book {'agrees' if direction == 'efficient' else 'diverges'} with our model")

        # Grade + action + confidence
        grade      = self._grade(adjusted_edge, ev_pct, steam_alert, rlm_signal)
        action     = self._action(adjusted_edge, ev_pct, steam_alert, rlm_signal, injury_impact)
        confidence = self._confidence(adjusted_edge, sharp_edge, steam_alert, rlm_signal)

        return ConsensusResult(
            event=event,
            sport=sport,
            market=market,
            outcome=outcome,
            model_prob=model_prob,
            market_prob=market_prob,
            sharp_prob=sharp_prob,
            edge_pct=adjusted_edge,
            sharp_edge=sharp_edge,
            ev_pct=ev_pct,
            grade=grade,
            action=action,
            confidence=confidence,
            notes=notes,
        )

    def _grade(self, edge: float, ev: float, steam: bool, rlm: bool) -> str:
        score = edge + (ev * 0.3)
        if steam:  score += 2.0
        if rlm:    score += 1.5
        if score >= 9:  return "A+"
        if score >= 7:  return "A"
        if score >= 5:  return "B"
        if score >= 3:  return "C"
        if score >= 1:  return "D"
        return "F"

    def _action(self, edge: float, ev: float, steam: bool, rlm: bool, injury: float) -> str:
        if edge < 2.0 or ev < 0:
            return "SKIP"
        if injury < -0.05:
            return "FADE"   # injury kills the pick
        if edge >= 5 and steam:
            return "BET_NOW"
        if edge >= 5 and rlm:
            return "BET_NOW"
        if edge >= 7:
            return "BET_NOW"
        if edge >= 4:
            return "LEAN_YES"
        if edge >= 2:
            return "WAIT"
        return "SKIP"

    def _confidence(self, edge: float, sharp_edge: Optional[float], steam: bool, rlm: bool) -> str:
        score = 0
        if edge > 7:    score += 3
        elif edge > 5:  score += 2
        elif edge > 3:  score += 1
        if sharp_edge and sharp_edge > 3: score += 2
        if steam:  score += 2
        if rlm:    score += 1
        if score >= 6:  return "VERY_HIGH"
        if score >= 4:  return "HIGH"
        if score >= 2:  return "MEDIUM"
        return "LOW"

    def batch_analyze(self, opportunities: list[dict]) -> list[ConsensusResult]:
        """Analyze multiple opportunities and rank by grade + edge."""
        results = []
        for opp in opportunities:
            try:
                r = self.analyze(
                    event=opp.get("event", ""),
                    sport=opp.get("sport", ""),
                    market=opp.get("market", ""),
                    outcome=opp.get("outcome", ""),
                    model_prob=float(opp.get("model_prob", 0.5)),
                    market_odds=float(opp.get("market_odds", 2.0)),
                    sharp_odds=opp.get("sharp_odds"),
                    steam_alert=bool(opp.get("steam")),
                    rlm_signal=bool(opp.get("rlm")),
                    injury_impact=float(opp.get("injury_impact", 0.0)),
                )
                results.append(r)
            except Exception:
                continue

        # rank: A+ first, within grade by edge_pct
        grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4, "F": 5}
        results.sort(key=lambda r: (grade_order.get(r.grade, 9), -r.edge_pct))
        return results
