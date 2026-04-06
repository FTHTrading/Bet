"""
Steam / Sharp Money Detector
=============================
Identifies sharp activity through:
  1. Rapid line movement (steam) — > threshold in < window minutes
  2. Reverse Line Movement (RLM) — line moves against public %
  3. Cross-book consensus divergence
  4. Cold number tracking (historic sharp levels)

This module maintains in-memory line history and computes alerts in real-time.
Alerts are broadcast to the dashboard via WebSocket.
"""
from __future__ import annotations
import time
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ── Thresholds ─────────────────────────────────────────────────────────────
STEAM_WINDOW_SECS   = 300   # 5-minute window
SPREAD_STEAM_THRESH = 1.5   # points of spread movement = steam
TOTAL_STEAM_THRESH  = 1.0   # points of total movement = steam
ML_STEAM_THRESH     = 10    # American odds points = steam (e.g. -110 → -120)
RLM_THRESH          = 0.10  # 10% of bets on one side but line moves other way

# "Cold numbers" — historically significant spread/total levels
COLD_NUMBERS = {
    "nfl":   {-3, -2.5, -3.5, -7, -6.5, -7.5, -10, 44.5, 47, 48.5},
    "nba":   {-5.5, -6, -6.5, -7, 220, 224, 225},
    "mlb":   {-1.5, 1.5, 8, 8.5, 9},
    "nhl":   {-1.5, 1.5, 5.5, 6},
}


@dataclass
class LineSnapshot:
    event:       str
    sport:       str
    market:      str
    book:        str
    outcome:     str
    odds:        float
    timestamp:   float = field(default_factory=time.time)


@dataclass
class SteamAlert:
    event:       str
    sport:       str
    market:      str
    from_odds:   float
    to_odds:     float
    delta:       float
    book:        str
    sharp:       bool
    rlm:         bool
    conviction:  str   # LOW | MEDIUM | HIGH | CRITICAL
    reason:      str
    age_mins:    float
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "event":       self.event,
            "sport":       self.sport,
            "market":      self.market,
            "from_odds":   self.from_odds,
            "to_odds":     self.to_odds,
            "delta":       round(self.delta, 2),
            "book":        self.book,
            "sharp":       self.sharp,
            "rlm":         self.rlm,
            "conviction":  self.conviction,
            "reason":      self.reason,
            "age_mins":    round(self.age_mins, 1),
            "detected_at": self.detected_at,
        }


class SteamDetector:
    """
    Real-time sharp/steam move detector.
    Maintains a rolling window of line changes per event/market.
    """

    def __init__(self):
        # key: (event, market, outcome) → deque of LineSnapshot
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self._alerts:  list[SteamAlert] = []
        self._max_alerts = 200

        # last known public betting % per event
        # key: (event, market) → {"home": 0.62, "away": 0.38}
        self._public_pct: dict[str, dict[str, float]] = {}

    # ── Feed Line Data ──────────────────────────────────────────────────────

    def feed(
        self,
        event:   str,
        sport:   str,
        market:  str,
        book:    str,
        outcome: str,
        odds:    float,
        public_home_pct: Optional[float] = None,
        public_away_pct: Optional[float] = None,
    ) -> Optional[SteamAlert]:
        """
        Ingest one line observation.
        Returns a SteamAlert if this update triggers steam detection.
        """
        key = f"{event}|{market}|{outcome}"
        snapshot = LineSnapshot(event, sport, market, book, outcome, odds)
        history  = self._history[key]

        if public_home_pct is not None:
            self._public_pct[f"{event}|{market}"] = {
                "home": public_home_pct,
                "away": public_away_pct or (1 - public_home_pct),
            }

        alert = None
        if history:
            alert = self._check_steam(snapshot, history)

        history.append(snapshot)

        if alert:
            # prevent duplicate alerts within 5 minutes
            if not self._is_duplicate(alert):
                self._alerts.insert(0, alert)
                self._alerts = self._alerts[: self._max_alerts]

        return alert

    def feed_batch(self, odds_data: list[dict]) -> list[SteamAlert]:
        """Feed multiple line observations at once. Returns all new alerts."""
        new_alerts: list[SteamAlert] = []
        for d in odds_data:
            a = self.feed(
                event=d.get("event", ""),
                sport=d.get("sport", ""),
                market=d.get("market", ""),
                book=d.get("book", ""),
                outcome=d.get("outcome", ""),
                odds=d.get("odds", 0),
                public_home_pct=d.get("public_home_pct"),
                public_away_pct=d.get("public_away_pct"),
            )
            if a:
                new_alerts.append(a)
        return new_alerts

    # ── Detection Logic ─────────────────────────────────────────────────────

    def _check_steam(
        self,
        snap: LineSnapshot,
        history: deque,
    ) -> Optional[SteamAlert]:
        """Core detection: check if latest snapshot triggers a steam alert."""
        recent = [
            s for s in history
            if snap.timestamp - s.timestamp <= STEAM_WINDOW_SECS
        ]
        if not recent:
            return None

        earliest = min(recent, key=lambda s: s.timestamp)
        delta    = snap.odds - earliest.odds
        abs_delta = abs(delta)

        # Determine threshold based on market
        market = snap.market.lower()
        if "total" in market or "ou" in market:
            threshold = TOTAL_STEAM_THRESH
        elif "spread" in market or "ats" in market:
            threshold = SPREAD_STEAM_THRESH
        else:
            threshold = ML_STEAM_THRESH

        if abs_delta < threshold:
            return None

        # Check for RLM
        rlm = self._check_rlm(snap, delta)

        # Compute conviction
        conviction = self._conviction(abs_delta, threshold, rlm, snap.sport)

        # Build reason string
        elapsed = (snap.timestamp - earliest.timestamp) / 60
        reason_parts = [f"Line moved {delta:+.1f} in {elapsed:.1f}min"]
        if rlm:
            pub = self._public_pct.get(f"{snap.event}|{snap.market}", {})
            home_pct = pub.get("home", 0) * 100
            reason_parts.append(f"RLM: {home_pct:.0f}% public bets vs line move opposite")
        if snap.sport in COLD_NUMBERS:
            cold = COLD_NUMBERS[snap.sport]
            if round(snap.odds) in cold or abs(snap.odds) in cold:
                reason_parts.append("Hit cold number")

        return SteamAlert(
            event=snap.event,
            sport=snap.sport,
            market=snap.market,
            from_odds=round(earliest.odds, 2),
            to_odds=round(snap.odds, 2),
            delta=round(delta, 2),
            book=snap.book,
            sharp=(conviction in ("HIGH", "CRITICAL")),
            rlm=rlm,
            conviction=conviction,
            reason=" | ".join(reason_parts),
            age_mins=0.0,
        )

    def _check_rlm(self, snap: LineSnapshot, delta: float) -> bool:
        """Reverse Line Movement: >60% of bets one way, line moves opposite."""
        pub = self._public_pct.get(f"{snap.event}|{snap.market}")
        if not pub:
            return False
        home_pct = pub.get("home", 0.5)
        # Public heavy on home (>60%) but line moved AWAY from home (negative delta)
        if home_pct > 0.60 and delta < 0:
            return True
        # Public heavy on away (<40%) but line moved TOWARD home (positive delta)
        if home_pct < 0.40 and delta > 0:
            return True
        return False

    def _conviction(
        self,
        abs_delta: float,
        threshold: float,
        rlm: bool,
        sport: str,
    ) -> str:
        ratio = abs_delta / threshold
        score = ratio
        if rlm:
            score += 1.0
        if score > 3.0:
            return "CRITICAL"
        if score > 2.0:
            return "HIGH"
        if score > 1.2:
            return "MEDIUM"
        return "LOW"

    def _is_duplicate(self, alert: SteamAlert) -> bool:
        """Debounce: don't fire same alert twice in 10 minutes."""
        ten_min_ago = time.time() - 600
        for existing in self._alerts:
            ts = datetime.fromisoformat(existing.detected_at).timestamp() if existing.detected_at else 0
            if (
                existing.event  == alert.event
                and existing.market == alert.market
                and ts > ten_min_ago
            ):
                return True
        return False

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_alerts(self, limit: int = 50, sport: Optional[str] = None) -> list[dict]:
        """Return recent steam alerts as dicts."""
        now = time.time()
        result = []
        for a in self._alerts[:limit]:
            ts = datetime.fromisoformat(a.detected_at).timestamp() if a.detected_at else now
            d  = a.to_dict()
            d["age_mins"] = round((now - ts) / 60, 1)
            if sport and d.get("sport", "").lower() != sport.lower():
                continue
            result.append(d)
        return result

    def get_sharp_alerts(self, limit: int = 20) -> list[dict]:
        """Return only HIGH/CRITICAL conviction alerts."""
        return [
            a for a in self.get_alerts(limit=100)
            if a.get("conviction") in ("HIGH", "CRITICAL") or a.get("sharp")
        ][:limit]

    def stats(self) -> dict:
        alerts = self.get_alerts(limit=1000)
        sharp  = [a for a in alerts if a.get("sharp")]
        rlm    = [a for a in alerts if a.get("rlm")]
        return {
            "total_alerts":  len(alerts),
            "sharp_alerts":  len(sharp),
            "rlm_alerts":    len(rlm),
            "last_alert":    alerts[0]["detected_at"] if alerts else None,
        }


# Singleton
_detector: Optional[SteamDetector] = None


def get_steam_detector() -> SteamDetector:
    global _detector
    if _detector is None:
        _detector = SteamDetector()
    return _detector
