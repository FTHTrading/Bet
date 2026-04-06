"""
RAG Knowledge Base
==================
Ingests and indexes sports betting knowledge into the vector store.
Covers:
  - Historical bet records
  - Sport-specific strategy documents
  - Sharp money patterns
  - Injury/weather impact profiles
  - Market structure knowledge
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from .embeddings import get_store

DB_PATH = Path(__file__).parent.parent / "db" / "kalishi_edge.db"


# ── Static Knowledge Documents ─────────────────────────────────────────────

BETTING_KNOWLEDGE = [
    {
        "id": "kb_kelly_001",
        "text": (
            "Kelly Criterion: The mathematically optimal fraction of bankroll to wager. "
            "Full Kelly f* = (bp - q) / b where b = decimal odds - 1, p = win probability, q = 1-p. "
            "Quarter Kelly (f*/4) is standard for bankroll preservation. "
            "Never bet negative Kelly — that means no edge exists."
        ),
        "meta": {"category": "strategy", "topic": "kelly_criterion", "importance": "critical"},
    },
    {
        "id": "kb_ev_001",
        "text": (
            "Expected Value (EV): EV = (p * decimal_odds) - 1. "
            "Positive EV means the bet has long-term value. "
            "Edge % = our_probability - implied_probability. "
            "A 3%+ edge is generally required before placing a bet. "
            "EV betting beats parlays over the long run."
        ),
        "meta": {"category": "strategy", "topic": "expected_value", "importance": "critical"},
    },
    {
        "id": "kb_clv_001",
        "text": (
            "Closing Line Value (CLV): The difference between your bet odds and closing odds. "
            "Positive CLV means you beat the closing line — the gold standard for sharp betting. "
            "CLV > 0 on 55%+ of bets indicates genuine edge. "
            "Books close sharp bettors because they consistently have positive CLV."
        ),
        "meta": {"category": "strategy", "topic": "clv", "importance": "critical"},
    },
    {
        "id": "kb_steam_001",
        "text": (
            "Steam move: Rapid, coordinated sharp money across multiple books. "
            "Identified by: line moves > 2 points (sides) or > 0.5 (totals) in under 5 minutes. "
            "Sharp syndicates bet large at many books simultaneously. "
            "Following steam moves within 2 minutes captures most CLV. "
            "Steam is strongest when line moves AGAINST public betting percentage."
        ),
        "meta": {"category": "intelligence", "topic": "steam_moves", "importance": "high"},
    },
    {
        "id": "kb_rlm_001",
        "text": (
            "Reverse Line Movement (RLM): Line moves opposite to public betting percentage. "
            "Example: 70% of bets on Team A but line moves away from Team A = sharp on Team B. "
            "RLM is one of the most reliable sharp money indicators. "
            "Best used on NFL, college football, and NBA markets."
        ),
        "meta": {"category": "intelligence", "topic": "rlm", "importance": "high"},
    },
    {
        "id": "kb_arb_001",
        "text": (
            "Arbitrage (arb): Guaranteed profit by betting both sides at different books. "
            "Arb exists when sum of implied probabilities < 1.0 across all outcomes. "
            "Two-way arb formula: stake_a/odds_a + stake_b/odds_b = total_stake. "
            "Typical arb profit 0.5-2.5%. Risk: line movement between bets, limits."
        ),
        "meta": {"category": "strategy", "topic": "arbitrage", "importance": "high"},
    },
    {
        "id": "kb_middle_001",
        "text": (
            "Middles: Buy both sides of a line at different numbers to win both bets. "
            "Example: bet Team A -2.5 and Team B +3.5 — if final margin is exactly 3, both win. "
            "Best found when books disagree by > 1 point on the spread. "
            "Middle window = gap between the two spread numbers. "
            "EV calculation: (middle_probability * combined_return) - guaranteed_loss."
        ),
        "meta": {"category": "strategy", "topic": "middles", "importance": "medium"},
    },
    {
        "id": "kb_mlb_001",
        "text": (
            "MLB betting: Focus on FIP (Fielding Independent Pitching) over ERA. "
            "FIP = (13*HR + 3*BB - 2*K) / IP + 3.10. Lower is better. "
            "wRC+ (weighted Runs Created Plus): 100 = league avg, 120+ = elite offense. "
            "Park factors matter: Coors Field (1.18), Petco Park (0.88). "
            "Wind > 10mph out adds ~0.3 runs to total. Temperature below 50F reduces scoring."
        ),
        "meta": {"category": "analysis", "topic": "mlb_metrics", "importance": "high"},
    },
    {
        "id": "kb_nba_001",
        "text": (
            "NBA betting: Offensive/Defensive Rating (per 100 possessions). "
            "Net rating = OffRtg - DefRtg. League average ~112 for both. "
            "Pace factor controls possessions per game — higher pace = higher totals. "
            "Back-to-back games: road team on second night is -2 to -3 points weaker. "
            "Rest advantage of 2+ days is worth ~1-1.5 points against no-rest team."
        ),
        "meta": {"category": "analysis", "topic": "nba_metrics", "importance": "high"},
    },
    {
        "id": "kb_nfl_001",
        "text": (
            "NFL betting: DVOA (Defense-adjusted Value Over Average) is the gold standard metric. "
            "EPA (Expected Points Added) per play measures efficiency. "
            "Home field advantage averages 2.5-3 points in NFL. "
            "Short week (less than 7 days rest) costs ~1.5 points. "
            "Weather: rain/snow reduces totals by 1-2.5 points, wind > 15mph reduces further."
        ),
        "meta": {"category": "analysis", "topic": "nfl_metrics", "importance": "high"},
    },
    {
        "id": "kb_bankroll_001",
        "text": (
            "Bankroll management: Never bet more than 5% of bankroll on single event. "
            "Unit size = 1-2% of bankroll. Use Kelly Criterion for sizing. "
            "Track ROI, CLV, win rate, and Sharpe ratio. "
            "Drawdown alert at -20%; stop at -30% and reassess. "
            "Profit Machine Protocol: 50% primary/20% hedge/20% props/10% high-payout."
        ),
        "meta": {"category": "strategy", "topic": "bankroll_management", "importance": "critical"},
    },
    {
        "id": "kb_sharp_001",
        "text": (
            "Sharp money indicators: Line moves without public bets piling on. "
            "Steam: coordinated rapid moves across books. "
            "Cold number: a spread that has been bet through multiple times (e.g. -3 to -3.5). "
            "Book limit reduction: books cutting limits signals sharp activity. "
            "Sharp syndicates: Pinnacle moves first, then DraftKings/FanDuel follow."
        ),
        "meta": {"category": "intelligence", "topic": "sharp_money", "importance": "high"},
    },
    {
        "id": "kb_profit_machine_001",
        "text": (
            "Profit Machine Protocol 2.0: Tiered allocation system. "
            "Tier 1 (50%): Moneyline or spread — highest confidence play, data-driven, EV > 5%. "
            "Tier 2 (20%): Hedge or alternate spread for protection with positive expected value. "
            "Tier 3 (20%): Player props — individual stats, 65-75% win rate. "
            "Tier 4 (10%): High-payout parlay or alt spread at +150 or better. "
            "Total expected compound win rate: 70-80%."
        ),
        "meta": {"category": "strategy", "topic": "profit_machine", "importance": "high"},
    },
]

SPORT_STRATEGIES = [
    {
        "id": "strat_mlb_total_001",
        "text": (
            "MLB totals strategy: Target games where starting pitcher FIP diverges > 0.5 from ERA. "
            "High strikeout pitchers (K/9 > 10) suppress scoring even with poor ERA. "
            "Bullpen ERA below 3.80 is elite, above 4.50 is vulnerable. "
            "Night games in cold weather (under 55F) lean under. "
            "Dome games remove weather variable — park factor becomes primary."
        ),
        "meta": {"category": "strategy", "topic": "mlb_totals", "sport": "mlb"},
    },
    {
        "id": "strat_nba_live_001",
        "text": (
            "NBA live betting strategy: First quarter momentum rarely holds for full game. "
            "Teams trailing by 15+ at half cover spread 45% of the time (regression to mean). "
            "Second night B2B teams start slow — profitable to bet under first quarter. "
            "Foul trouble to star players boosts opponent spread cover probability +8%. "
            "Late-game fouling situations make totals go over — avoid under after Q3."
        ),
        "meta": {"category": "strategy", "topic": "nba_live", "sport": "nba"},
    },
    {
        "id": "strat_nfl_weather_001",
        "text": (
            "NFL weather betting: Wind above 20mph destroys passing games — both over and spread impact. "
            "Temperature below 32F in outdoor stadiums reduces scoring by ~2-4 points. "
            "Teams practicing in domes (Falcons, Saints, Vikings) suffer in outdoor cold. "
            "Rain reduces tracking/turf speed — favors ground game, run heavy teams. "
            "Historical data: over/under hits rate drops to 43% in wind > 20mph games."
        ),
        "meta": {"category": "strategy", "topic": "nfl_weather", "sport": "nfl"},
    },
]


class KnowledgeBase:
    """
    Manages ingestion of betting knowledge, bet history, and game intelligence
    into the RAG vector store.
    """

    def __init__(self):
        self._store = get_store()

    def seed_static_knowledge(self) -> int:
        """Load static betting knowledge documents into vector store."""
        if not self._store.ready:
            return 0

        all_docs = BETTING_KNOWLEDGE + SPORT_STRATEGIES
        texts    = [d["text"] for d in all_docs]
        metas    = [d["meta"] for d in all_docs]
        ids      = [d["id"]   for d in all_docs]

        count = self._store.upsert("knowledge", texts, metas, ids)
        print(f"[RAG:KB] Seeded {count} knowledge documents")
        return count

    def ingest_bet(self, bet: dict) -> bool:
        """Index a single bet record for future retrieval."""
        if not self._store.ready:
            return False

        text = (
            f"Bet: {bet.get('sport','?')} | {bet.get('event','?')} | "
            f"Pick: {bet.get('pick','?')} | Market: {bet.get('market','?')} | "
            f"Odds: {bet.get('american_odds','?')} | Stake: ${bet.get('stake',0):.2f} | "
            f"Edge: {bet.get('edge_pct',0):.1f}% | EV: {bet.get('ev_pct',0):.1f}% | "
            f"Result: {bet.get('result','open')} | P&L: {bet.get('pnl','?')} | "
            f"CLV: {bet.get('clv','?')} | Strategy: {bet.get('strategy','?')}"
        )
        meta = {
            "sport":     str(bet.get("sport", "")),
            "market":    str(bet.get("market", "")),
            "result":    str(bet.get("result", "open")),
            "edge_pct":  float(bet.get("edge_pct", 0)),
            "placed_at": str(bet.get("placed_at", datetime.utcnow().isoformat())),
        }

        self._store.upsert("bet_history", [text], [meta], [f"bet_{bet.get('id','?')}"])
        return True

    def ingest_bets_from_db(self) -> int:
        """Batch ingest all bets from SQLite into the vector store."""
        if not DB_PATH.exists():
            return 0
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM bets ORDER BY placed_at DESC LIMIT 500").fetchall()
            conn.close()
        except Exception as e:
            print(f"[RAG:KB] DB error: {e}")
            return 0

        count = 0
        for row in rows:
            if self.ingest_bet(dict(row)):
                count += 1
        print(f"[RAG:KB] Ingested {count} bets from DB")
        return count

    def ingest_game_intel(
        self,
        event: str,
        sport: str,
        analysis_text: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Add game analysis notes to the intelligence collection."""
        if not self._store.ready:
            return False
        meta = {
            "event":     event,
            "sport":     sport,
            "indexed_at": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }
        self._store.upsert("game_intel", [analysis_text], [meta])
        return True

    def ingest_market_move(self, move: dict) -> bool:
        """Index a sharp/steam move alert."""
        if not self._store.ready:
            return False
        text = (
            f"Sharp move: {move.get('event','?')} | {move.get('market','?')} | "
            f"Line moved {move.get('from_odds','?')} → {move.get('to_odds','?')} "
            f"({move.get('delta',0):+.1f}) | Book: {move.get('book','?')} | "
            f"Sharp: {move.get('sharp', False)} | Sport: {move.get('sport','?')}"
        )
        meta = {
            "event":  str(move.get("event", "")),
            "sport":  str(move.get("sport", "")),
            "sharp":  str(move.get("sharp", False)),
            "detected_at": datetime.utcnow().isoformat(),
        }
        self._store.upsert("market_moves", [text], [meta])
        return True

    def ingest_ai_pick(self, pick: dict, reasoning: str) -> bool:
        """Index an AI-generated pick with its full reasoning chain."""
        if not self._store.ready:
            return False
        text = (
            f"AI Pick: {pick.get('sport','?')} | {pick.get('event','?')} | "
            f"Pick: {pick.get('pick','?')} | {pick.get('market','?')} | "
            f"Edge: {pick.get('edge_pct',0):.1f}% | EV: {pick.get('ev_pct',0):.1f}% | "
            f"Odds: {pick.get('american_odds','?')} | "
            f"Reasoning: {reasoning}"
        )
        meta = {
            "event":    str(pick.get("event", "")),
            "sport":    str(pick.get("sport", "")),
            "edge_pct": float(pick.get("edge_pct", 0)),
            "generated_at": datetime.utcnow().isoformat(),
        }
        self._store.upsert("daily_picks", [text], [meta])
        return True

    def stats(self) -> dict:
        return self._store.stats()
