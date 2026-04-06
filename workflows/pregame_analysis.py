"""
Pre-Game Agentic Analysis Pipeline
====================================
Full SR-engineered multi-agent workflow for pre-game analysis.
Each game runs through all agents in parallel, then consensus + AI brain
synthesize the final recommendation.

Pipeline:
  1. Fetch live odds (Odds API)
  2. Run sport-specific Monte Carlo simulation
  3. Build market consensus (model vs market vs sharp)
  4. Check steam detector for any live alerts on this game
  5. RAG-retrieve relevant historical context
  6. AI Brain synthesizes to final structured pick
  7. Index pick in RAG for future retrieval
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Optional


async def run_pregame_analysis(
    event:       str,
    sport:       str,
    home_team:   str,
    away_team:   str,
    market:      str = "h2h",
    home_odds:   Optional[float] = None,
    away_odds:   Optional[float] = None,
    sharp_odds_home: Optional[float] = None,
    sharp_odds_away: Optional[float] = None,
    sim_params:  Optional[dict] = None,
    bankroll:    float = 10_000,
) -> dict:
    """
    Full agentic pre-game analysis pipeline.
    Returns a rich dict with simulation, consensus, AI analysis, and pick recommendation.
    """
    result: dict = {
        "event":    event,
        "sport":    sport,
        "home":     home_team,
        "away":     away_team,
        "market":   market,
        "analyzed_at": datetime.utcnow().isoformat(),
        "pipeline":  [],
    }

    # ── Step 1: Run Monte Carlo simulation ─────────────────────────────────
    sim_result = await _run_simulation(sport, home_team, away_team, sim_params or {})
    result["simulation"] = sim_result
    result["pipeline"].append("simulation")

    # ── Step 2: Build market consensus ─────────────────────────────────────
    home_win_prob = sim_result.get("home_win_prob", 0.5)
    consensus_home = await _run_consensus(
        event=event, sport=sport, market=market, outcome="home",
        model_prob=home_win_prob,
        market_odds=home_odds or 2.0,
        sharp_odds=sharp_odds_home,
    )
    consensus_away = await _run_consensus(
        event=event, sport=sport, market=market, outcome="away",
        model_prob=1 - home_win_prob,
        market_odds=away_odds or 2.0,
        sharp_odds=sharp_odds_away,
    )
    result["consensus"] = {
        "home": consensus_home,
        "away": consensus_away,
        "best_side": "home" if (consensus_home.get("edge_pct", 0)) >= (consensus_away.get("edge_pct", 0)) else "away",
    }
    result["pipeline"].append("consensus")

    # ── Step 3: Check steam alerts ─────────────────────────────────────────
    steam_alerts = _get_steam_for_event(event)
    result["steam"] = steam_alerts
    result["pipeline"].append("steam_check")

    # ── Step 4: Kelly sizing ────────────────────────────────────────────────
    best = result["consensus"]["best_side"]
    best_consensus = consensus_home if best == "home" else consensus_away
    best_odds_dec  = home_odds if best == "home" else away_odds
    sizing = _compute_kelly(
        prob=home_win_prob if best == "home" else (1 - home_win_prob),
        decimal_odds=best_odds_dec or 2.0,
        bankroll=bankroll,
    )
    result["sizing"] = sizing
    result["pipeline"].append("kelly_sizing")

    # ── Step 5: AI Brain analysis ───────────────────────────────────────────
    ai_analysis = await _run_ai_analysis(
        event=event, sport=sport, market=market,
        best_side=best,
        edge_pct=best_consensus.get("edge_pct", 0),
        ev_pct=best_consensus.get("ev_pct", 0),
        model_prob=home_win_prob if best == "home" else (1 - home_win_prob),
        implied_prob=best_consensus.get("market_prob", 50) / 100,
        american_odds=_dec_to_american(best_odds_dec or 2.0),
        stake=sizing.get("bet_amount", 0),
        steam_alerts=steam_alerts,
    )
    result["ai_analysis"] = ai_analysis
    result["pipeline"].append("ai_brain")

    # ── Step 6: Final pick assembly ─────────────────────────────────────────
    pick = _assemble_pick(result, best, best_consensus, sizing, ai_analysis)
    result["pick"] = pick
    result["pipeline"].append("pick_assembled")

    # ── Step 7: Index in RAG ───────────────────────────────────────────────
    _index_in_rag(pick, ai_analysis.get("reasoning", ""))
    result["pipeline"].append("rag_indexed")

    return result


# ── Step Implementations ───────────────────────────────────────────────────

async def _run_simulation(sport: str, home: str, away: str, params: dict) -> dict:
    """Run the appropriate Monte Carlo simulation."""
    try:
        if sport in ("mlb", "baseball_mlb"):
            from engine.monte_carlo import mlb_game_sim
            sim = mlb_game_sim(
                home_era=params.get("home_fip", 4.0),
                away_era=params.get("away_fip", 4.0),
                home_wrc_plus=params.get("home_wrc", 100),
                away_wrc_plus=params.get("away_wrc", 100),
                park_factor=params.get("park_factor", 1.0),
                n_sims=50_000,
            )
        elif sport in ("nba", "basketball_nba"):
            from engine.monte_carlo import nba_game_sim
            sim = nba_game_sim(
                home_off_rtg=params.get("home_off", 112),
                home_def_rtg=params.get("home_def", 112),
                away_off_rtg=params.get("away_off", 112),
                away_def_rtg=params.get("away_def", 112),
                home_pace=params.get("home_pace", 100),
                away_pace=params.get("away_pace", 100),
            )
        elif sport in ("nfl", "americanfootball_nfl"):
            from engine.monte_carlo import nfl_game_sim
            sim = nfl_game_sim(
                home_dvoa=params.get("home_dvoa", 0),
                away_dvoa=params.get("away_dvoa", 0),
                home_epa=params.get("home_epa", 0),
                away_epa=params.get("away_epa", 0),
            )
        else:
            return {"home_win_prob": 0.5, "away_win_prob": 0.5, "over_prob": 0.5}

        return {
            "home_win_prob": round(sim.home_win_prob, 4),
            "away_win_prob": round(sim.away_win_prob, 4),
            "over_prob":     round(getattr(sim, "over_prob", 0.5), 4),
            "n_sims": 50_000,
        }
    except Exception as e:
        return {"home_win_prob": 0.5, "away_win_prob": 0.5, "over_prob": 0.5, "error": str(e)}


async def _run_consensus(
    event: str, sport: str, market: str, outcome: str,
    model_prob: float, market_odds: float, sharp_odds: Optional[float],
) -> dict:
    try:
        from intelligence.consensus import MarketConsensus
        c = MarketConsensus()
        r = c.analyze(
            event=event, sport=sport, market=market, outcome=outcome,
            model_prob=model_prob, market_odds=market_odds, sharp_odds=sharp_odds,
        )
        return r.to_dict()
    except Exception:
        edge = (model_prob - (1 / market_odds)) * 100 if market_odds > 1 else 0
        return {"edge_pct": round(edge, 2), "market_prob": round(100 / market_odds, 2) if market_odds > 1 else 50.0, "ev_pct": round(edge, 2)}


def _get_steam_for_event(event: str) -> list:
    try:
        from intelligence.steam_detector import get_steam_detector
        d = get_steam_detector()
        return [a for a in d.get_alerts(50) if a.get("event") == event]
    except Exception:
        return []


def _compute_kelly(prob: float, decimal_odds: float, bankroll: float) -> dict:
    try:
        from engine.kelly import calculate_kelly, american_to_decimal
        result = calculate_kelly(prob, decimal_odds, bankroll, kelly_multiplier=0.25)
        return {
            "edge_pct":   round(result.edge * 100, 2),
            "kelly_pct":  round(result.fraction * 100, 2),
            "rec_pct":    round(result.recommended * 100, 2),
            "bet_amount": round(result.bet_amount, 2),
            "verdict":    result.verdict,
        }
    except Exception as e:
        return {"bet_amount": 0, "verdict": "ERROR", "error": str(e)}


async def _run_ai_analysis(
    event: str, sport: str, market: str, best_side: str,
    edge_pct: float, ev_pct: float, model_prob: float, implied_prob: float,
    american_odds: int, stake: float, steam_alerts: list,
) -> dict:
    try:
        from agents.brain import get_brain
        brain = get_brain()
        if not brain.available:
            return {"conviction": "HOLD", "reasoning": "AI Brain offline", "action": "MONITOR"}
        analysis = await brain.analyze_pick(
            sport=sport, event=event, market=market,
            edge_pct=edge_pct, ev_pct=ev_pct,
            our_prob=model_prob, implied_prob=implied_prob,
            american_odds=american_odds, stake=stake,
            additional_context={"best_side": best_side, "steam_alerts": steam_alerts[:3]},
        )
        return analysis
    except Exception as e:
        return {"conviction": "HOLD", "error": str(e)}


def _assemble_pick(result: dict, best: str, consensus: dict, sizing: dict, ai: dict) -> dict:
    home = result["home"]
    away = result["away"]
    pick_team  = home if best == "home" else away
    return {
        "sport":         result["sport"],
        "event":         result["event"],
        "pick":          pick_team,
        "market":        result["market"],
        "edge_pct":      consensus.get("edge_pct", 0),
        "ev_pct":        consensus.get("ev_pct", 0),
        "grade":         consensus.get("grade", "C"),
        "action":        consensus.get("action", "WAIT"),
        "conviction":    ai.get("conviction", "HOLD"),
        "bet_amount":    sizing.get("bet_amount", 0),
        "kelly_pct":     sizing.get("kelly_pct", 0),
        "ai_thesis":     ai.get("one_line_thesis", ""),
        "risk_factors":  ai.get("risk_factors", []),
        "steam":         bool(result.get("steam")),
        "generated_at":  datetime.utcnow().isoformat(),
    }


def _index_in_rag(pick: dict, reasoning: str) -> bool:
    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        return kb.ingest_ai_pick(pick, reasoning)
    except Exception:
        return False


def _dec_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2.0:
        return int((decimal_odds - 1) * 100)
    elif decimal_odds > 1.0:
        return int(-100 / (decimal_odds - 1))
    return -110
