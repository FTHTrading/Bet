"""
Daily Briefing Agentic Workflow
================================
Scheduled (or on-demand) workflow that assembles the master daily intelligence report:

  1. Pull today's top picks from RAG / DB
  2. Grab current steam alerts
  3. Fetch bankroll state
  4. Run AI Brain: generate_daily_briefing()
  5. Broadcast to /ws/live  (JSON) + /ws/ai  (streaming markdown)
  6. Persist briefing to DB

Usage:
  asyncio.run(generate_briefing())          # standalone / scheduler
  await generate_briefing(broadcast=False)  # inside FastAPI startup
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
from datetime import date, datetime
from typing import Any, Optional


DB_PATH = "db/kalishi.db"


async def generate_briefing(broadcast: bool = True) -> dict:
    """
    Master daily briefing generator.
    Returns the full briefing dict and optionally broadcasts it over WebSocket.
    """
    today   = date.today().isoformat()
    now_iso = datetime.utcnow().isoformat()

    # ── Gather all intelligence in parallel ──────────────────────────────
    picks_task   = asyncio.create_task(_get_today_picks())
    steam_task   = asyncio.create_task(_get_steam_alerts())
    bankroll_task = asyncio.create_task(_get_bankroll())

    picks, steam, bankroll = await asyncio.gather(picks_task, steam_task, bankroll_task)

    # ── Build inputs for AI brain ────────────────────────────────────────
    market_intelligence = _assemble_market_intel(picks, steam)

    # ── Call AI Brain ────────────────────────────────────────────────────
    ai_briefing = await _call_brain_briefing(
        picks=picks,
        steam_alerts=steam,
        bankroll=bankroll,
        market_intel=market_intelligence,
    )

    briefing = {
        "date":             today,
        "generated_at":     now_iso,
        "top_picks":        picks[:10],
        "steam_alerts":     steam[:10],
        "bankroll":         bankroll,
        "market_intel":     market_intelligence,
        "ai_summary":       ai_briefing.get("summary", ""),
        "key_angles":       ai_briefing.get("key_angles", []),
        "fade_list":        ai_briefing.get("fade_list", []),
        "profit_machine":   ai_briefing.get("profit_machine_plays", []),
        "risk_flags":       ai_briefing.get("risk_flags", []),
        "total_picks":      len(picks),
        "sharp_alerts":     sum(1 for s in steam if s.get("conviction") in ("HIGH", "CRITICAL")),
        "type": "daily_briefing",
    }

    # ── Persist to DB ────────────────────────────────────────────────────
    await _persist_briefing(today, briefing)

    # ── Broadcast to WebSocket clients ───────────────────────────────────
    if broadcast:
        await _broadcast(briefing)

    return briefing


# ── Data-gathering helpers ─────────────────────────────────────────────────

async def _get_today_picks() -> list[dict]:
    """Fetch today's picks from RAG (by recency) + DB."""
    picks: list[dict] = []

    # Try RAG retrieval first
    try:
        from rag.retriever import KalishiRetriever
        r = KalishiRetriever()
        raw = r.retrieve_for_pick(sport="*", event="daily_picks", extra_context="top picks today A+ grade")
        # raw is a markdown string — we just attach it as metadata
    except Exception:
        raw = ""

    # Pull from SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        today = date.today().isoformat()
        rows = cur.execute(
            """
            SELECT sport, home_team, away_team, market, pick, odds,
                   edge_pct, ev_pct, stake, outcome
            FROM bets
            WHERE date(placed_at) = ?
            ORDER BY ev_pct DESC
            LIMIT 20
            """,
            (today,),
        ).fetchall()
        conn.close()
        picks = [dict(r) for r in rows]
    except Exception:
        pass

    return picks


async def _get_steam_alerts() -> list[dict]:
    try:
        from intelligence.steam_detector import get_steam_detector
        d = get_steam_detector()
        return d.get_alerts(50)
    except Exception:
        return []


async def _get_bankroll() -> dict:
    try:
        from engine.bankroll import get_bankroll_manager
        bm  = get_bankroll_manager()
        state = bm.get_state()
        return {
            "total":    state.total_bankroll,
            "units":    state.unit_size,
            "roi":      state.roi,
            "win_rate": state.win_rate,
            "streak":   state.current_streak,
        }
    except Exception:
        return {"total": 10_000, "units": 100, "roi": 0, "win_rate": 0.5, "streak": 0}


def _assemble_market_intel(picks: list, steam: list) -> dict:
    total_edge   = sum(p.get("edge_pct", 0) for p in picks) / max(len(picks), 1)
    sharp_storms = [s for s in steam if s.get("conviction") in ("HIGH", "CRITICAL")]
    sports_active = list({p.get("sport", "unknown") for p in picks})
    return {
        "avg_edge":      round(total_edge, 2),
        "sharp_storms":  len(sharp_storms),
        "sports_active": sports_active,
        "total_picks":   len(picks),
    }


async def _call_brain_briefing(
    picks: list, steam_alerts: list, bankroll: dict, market_intel: dict
) -> dict:
    try:
        from agents.brain import get_brain
        brain = get_brain()
        if not brain.available:
            return _fallback_briefing(picks, steam_alerts, bankroll)
        return await brain.generate_daily_briefing(
            top_picks=picks[:10],
            steam_alerts=steam_alerts[:10],
            bankroll=bankroll,
            market_intel=market_intel,
        )
    except Exception as e:
        return _fallback_briefing(picks, steam_alerts, bankroll)


def _fallback_briefing(picks: list, steam_alerts: list, bankroll: dict) -> dict:
    top = picks[:3]
    return {
        "summary": f"Today's scouting report: {len(picks)} picks queued across {len({p.get('sport') for p in picks})} sports. "
                   f"Bankroll at ${bankroll.get('total', 0):,.0f}. "
                   f"{len(steam_alerts)} steam alerts active.",
        "key_angles": [p.get("pick", "") for p in top if p.get("pick")],
        "profit_machine_plays": [p for p in picks if p.get("edge_pct", 0) >= 5][:5],
        "fade_list": [],
        "risk_flags": ["AI Brain offline — using rule-based briefing"],
    }


async def _persist_briefing(today: str, briefing: dict) -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                briefing_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_briefings (date, briefing_json, created_at)
            VALUES (?, ?, ?)
            """,
            (today, json.dumps(briefing), datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


async def _broadcast(briefing: dict) -> None:
    try:
        # Import the live WS broadcast from the MCP server module
        from mcp.server import broadcast
        await broadcast(json.dumps(briefing))
    except Exception:
        pass


if __name__ == "__main__":
    result = asyncio.run(generate_briefing(broadcast=False))
    print(json.dumps(result, indent=2, default=str))
