"""
KALISHI EDGE — MCP Server
=========================
FastAPI-based MCP (Model Context Protocol) server exposing all betting
tools as callable endpoints for AI agents and the dashboard.

Port: 8420 (configurable via MCP_PORT env var)
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import asyncio
import json
import uvicorn
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from engine.kelly import calculate_kelly, profit_machine_split, american_to_decimal
from engine.ev import calculate_ev, true_probability_no_vig, acts_of_god_adjustment
from engine.arbitrage import find_two_way_arb, find_three_way_arb, scan_multibook_lines
from engine.monte_carlo import mlb_game_sim, nba_game_sim, nfl_game_sim, nhl_game_sim
from engine.mlb_metrics import analyze_mlb_matchup, fip, woba, era
from engine.bankroll import BankrollManager

# ── AI / RAG / Intelligence (lazy-loaded so server starts without optional deps) ──
def _get_brain():
    try:
        from agents.brain import get_brain
        return get_brain()
    except Exception:
        return None

def _get_steam():
    try:
        from intelligence.steam_detector import get_steam_detector
        return get_steam_detector()
    except Exception:
        return None

def _get_consensus():
    try:
        from intelligence.consensus import MarketConsensus
        return MarketConsensus()
    except Exception:
        return None

def _get_rag():
    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        kb.seed_static_knowledge()
        return kb
    except Exception:
        return None

def _get_retriever():
    try:
        from rag.retriever import KalishiRetriever
        return KalishiRetriever()
    except Exception:
        return None

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="KALISHI EDGE — Personal Sports Betting AI",
    description="Your ultimate edge: Kelly, EV, arbitrage, Monte Carlo, and AI predictions",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BANKROLL = float(os.getenv("BANKROLL_TOTAL", "10000"))
bankroll_mgr = BankrollManager(BANKROLL)

# ── Startup: seed RAG knowledge base ─────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        await asyncio.to_thread(kb.seed_static_knowledge)
        await asyncio.to_thread(kb.ingest_bets_from_db)
        print("[KALISHI] RAG knowledge base seeded")
    except Exception as e:
        print(f"[KALISHI] RAG startup skipped: {e}")

# WebSocket connections for live dashboard updates
_ws_clients: list[WebSocket] = []
_ai_ws_clients: list[WebSocket] = []

async def broadcast_ai(data: dict):
    """Broadcast AI agent events to AI WebSocket clients."""
    msg = json.dumps(data)
    disconnected = []
    for ws in _ai_ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in _ai_ws_clients:
            _ai_ws_clients.remove(ws)

async def broadcast(data: dict):
    """Broadcast update to all dashboard WebSocket clients."""
    msg = json.dumps(data)
    disconnected = []
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_clients.remove(ws)


# ── Models ─────────────────────────────────────────────────────────────────

class KellyRequest(BaseModel):
    our_prob: float = Field(..., ge=0.01, le=0.99, description="Our estimated win probability")
    american_odds: int = Field(..., description="American odds (+150, -110, etc)")
    bankroll: Optional[float] = None
    kelly_fraction: float = Field(0.25, ge=0.1, le=1.0)
    min_edge: float = 0.03

class EVRequest(BaseModel):
    our_prob: float = Field(..., ge=0.01, le=0.99)
    decimal_odds: float = Field(..., gt=1.0)

class ArbRequest(BaseModel):
    side_a_odds: float = Field(..., gt=1.0)
    side_b_odds: float = Field(..., gt=1.0)
    draw_odds: Optional[float] = None
    stake: float = 100.0

class MLBRequest(BaseModel):
    home_team: str
    away_team: str
    home_starter_fip: float = 4.00
    away_starter_fip: float = 4.00
    home_wrc_plus: float = 100.0
    away_wrc_plus: float = 100.0
    park_factor: float = 1.00
    home_bullpen_era: float = 4.00
    away_bullpen_era: float = 4.00
    temp_f: float = 72.0
    wind_mph: float = 0.0
    wind_out: bool = False
    total_line: float = 8.5
    n_sims: int = Field(50000, ge=1000, le=200000)

class NBARequest(BaseModel):
    home_team: str
    away_team: str
    home_off_rtg: float = 112.0
    home_def_rtg: float = 112.0
    away_off_rtg: float = 112.0
    away_def_rtg: float = 112.0
    home_pace: float = 100.0
    away_pace: float = 100.0
    back_to_back_home: bool = False
    back_to_back_away: bool = False
    spread: float = 0.0
    total_line: float = 220.0
    n_sims: int = 50000

class NFLRequest(BaseModel):
    home_team: str
    away_team: str
    home_dvoa: float = 0.0
    away_dvoa: float = 0.0
    home_epa: float = 0.0
    away_epa: float = 0.0
    weather_factor: float = 1.0
    short_week_home: bool = False
    short_week_away: bool = False
    spread: float = 0.0
    total_line: float = 44.5
    n_sims: int = 50000

class BetSlipRequest(BaseModel):
    sport: str
    event: str
    market: str
    pick: str
    american_odds: int
    stake: float
    ev: float
    edge: float
    strategy: str = "value"

class ActsOfGodRequest(BaseModel):
    base_prob: float
    weather_impact: float = 0.0
    travel_impact: float = 0.0
    injury_impact: float = 0.0
    altitude_impact: float = 0.0
    rest_impact: float = 0.0

class ProfitMachineRequest(BaseModel):
    bankroll: Optional[float] = None
    confidence: str = "standard"

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    clear_history: bool = False

class PickAnalysisRequest(BaseModel):
    sport: str
    event: str
    market: str
    edge_pct: float
    ev_pct: float
    our_prob: float
    implied_prob: float
    american_odds: int
    stake: float
    additional_context: Optional[dict] = None

class ConsensusRequest(BaseModel):
    event:         str
    sport:         str
    market:        str
    outcome:       str
    model_prob:    float
    market_odds:   float
    sharp_odds:    Optional[float] = None
    steam_alert:   bool = False
    rlm_signal:    bool = False
    injury_impact: float = 0.0

class LineFeedRequest(BaseModel):
    event:   str
    sport:   str
    market:  str
    book:    str
    outcome: str
    odds:    float
    public_home_pct: Optional[float] = None

class RAGSearchRequest(BaseModel):
    query:             str
    collections:       Optional[List[str]] = None
    n_per_collection:  int = Field(3, ge=1, le=10)


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "system": "KALISHI EDGE",
        "version": "1.0.0",
        "status": "operational",
        "tools": [
            "/kelly", "/ev", "/arbitrage", "/no-vig",
            "/simulate/mlb", "/simulate/nba", "/simulate/nfl",
            "/profit-machine", "/acts-of-god",
            "/bankroll", "/bets", "/picks/today",
        ]
    }


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.now().isoformat()}


# ── Kelly Criterion ────────────────────────────────────────────────────────

@app.post("/kelly")
def kelly_endpoint(req: KellyRequest):
    """Calculate optimal bet size using Kelly Criterion."""
    bankroll = req.bankroll or bankroll_mgr.current
    decimal_odds = american_to_decimal(req.american_odds)
    result = calculate_kelly(
        our_prob=req.our_prob,
        decimal_odds=decimal_odds,
        bankroll=bankroll,
        kelly_multiplier=req.kelly_fraction,
        min_edge=req.min_edge,
    )
    return {
        "edge_pct": round(result.edge * 100, 2),
        "raw_kelly_pct": round(result.fraction * 100, 2),
        "recommended_pct": round(result.recommended * 100, 2),
        "bet_amount": result.bet_amount,
        "ev_per_100": round(result.ev * 100, 2),
        "implied_prob": round(result.implied_prob * 100, 2),
        "our_prob": round(result.our_prob * 100, 2),
        "verdict": result.verdict,
        "bankroll": bankroll,
    }


# ── Expected Value ─────────────────────────────────────────────────────────

@app.post("/ev")
def ev_endpoint(req: EVRequest):
    """Calculate Expected Value for a bet."""
    result = calculate_ev(req.our_prob, req.decimal_odds)
    return {
        "ev": round(result.ev, 4),
        "ev_pct": round(result.ev_pct, 2),
        "edge_pct": round(result.edge * 100, 2),
        "break_even_prob": round(result.break_even_prob * 100, 2),
        "confidence": result.confidence,
        "positive": result.positive,
    }


# ── Arbitrage ──────────────────────────────────────────────────────────────

@app.post("/arbitrage")
def arbitrage_endpoint(req: ArbRequest):
    """Find arbitrage opportunity between two books."""
    if req.draw_odds:
        result = find_three_way_arb(req.side_a_odds, req.draw_odds, req.side_b_odds, req.stake)
    else:
        result = find_two_way_arb(req.side_a_odds, req.side_b_odds, req.stake)
    
    if result is None:
        return {"arb_exists": False, "message": "No arbitrage opportunity found"}
    return result


# ── No-Vig True Probability ────────────────────────────────────────────────

@app.get("/no-vig")
def no_vig(home: float, away: float, draw: Optional[float] = None):
    """Remove bookmaker vig and return true market probabilities."""
    return true_probability_no_vig(home, away, draw)


# ── Profit Machine Protocol 2.0 ────────────────────────────────────────────

@app.post("/profit-machine")
def profit_machine_endpoint(req: ProfitMachineRequest):
    """Generate Profit Machine Protocol 2.0 bet allocation."""
    bankroll = req.bankroll or bankroll_mgr.current
    split = profit_machine_split(bankroll, req.confidence)
    return {
        **split,
        "protocol": "Profit Machine Protocol 2.0",
        "expected_win_rate": "70-80% (compound across all legs)",
        "strategy": {
            "primary_50pct": "Moneyline or spread — data-driven favorite",
            "hedge_20pct": "Alternate spread or opposite side protection",
            "props_20pct": "Player props (65-75% individual win rate)",
            "high_payout_10pct": "Parlay or alt spread (+150 or better)",
        }
    }


# ── Acts of God Adjustment ─────────────────────────────────────────────────

@app.post("/acts-of-god")
def acts_of_god_endpoint(req: ActsOfGodRequest):
    """Adjust probability for exogenous 'Acts of God' factors."""
    adjusted = acts_of_god_adjustment(
        base_prob=req.base_prob,
        weather_impact=req.weather_impact,
        travel_impact=req.travel_impact,
        injury_impact=req.injury_impact,
        altitude_impact=req.altitude_impact,
        rest_impact=req.rest_impact,
    )
    delta = adjusted - req.base_prob
    return {
        "base_prob": req.base_prob,
        "adjusted_prob": round(adjusted, 4),
        "delta": round(delta, 4),
        "factors": {
            "weather": req.weather_impact,
            "travel": req.travel_impact,
            "injury": req.injury_impact,
            "altitude": req.altitude_impact,
            "rest": req.rest_impact,
        }
    }


# ── Sport Simulations ──────────────────────────────────────────────────────

@app.post("/simulate/mlb")
def simulate_mlb(req: MLBRequest):
    """Run Monte Carlo MLB game simulation using sabermetrics."""
    from engine.mlb_metrics import analyze_mlb_matchup
    
    # Sabermetric matchup analysis
    matchup = analyze_mlb_matchup(
        home_team=req.home_team,
        away_team=req.away_team,
        home_starter_fip=req.home_starter_fip,
        away_starter_fip=req.away_starter_fip,
        home_team_wrc_plus=req.home_wrc_plus,
        away_team_wrc_plus=req.away_wrc_plus,
        park_factor=req.park_factor,
        home_bullpen_era=req.home_bullpen_era,
        away_bullpen_era=req.away_bullpen_era,
        temp_f=req.temp_f,
        wind_mph=req.wind_mph,
        wind_out=req.wind_out,
        total_line=req.total_line,
    )
    
    # Monte Carlo simulation
    sim = mlb_game_sim(
        home_era=req.home_starter_fip,
        away_era=req.away_starter_fip,
        home_wrc_plus=req.home_wrc_plus,
        away_wrc_plus=req.away_wrc_plus,
        park_factor=req.park_factor,
        wind_mph=req.wind_mph,
        dome=False,
        total_line=req.total_line,
        n_sims=req.n_sims,
    )
    
    return {
        "matchup": {
            "home": req.home_team,
            "away": req.away_team,
            "predicted_score": f"{matchup.predicted_home_runs:.1f} — {matchup.predicted_away_runs:.1f}",
            "total_predicted": matchup.total_predicted,
        },
        "probabilities": {
            "home_win": round(sim.home_win_prob * 100, 1),
            "away_win": round(sim.away_win_prob * 100, 1),
            "over": round(sim.over_prob * 100, 1),
            "under": round((1 - sim.over_prob) * 100, 1),
        },
        "sabermetrics": {
            "home_starter_fip": req.home_starter_fip,
            "away_starter_fip": req.away_starter_fip,
            "home_wrc_plus": req.home_wrc_plus,
            "away_wrc_plus": req.away_wrc_plus,
            "park_factor": req.park_factor,
            "weather_adj": matchup.weather_adjustment,
        },
        "edge": {
            "over_line": req.total_line,
            "over_prob": matchup.edge_over,
            "under_prob": matchup.edge_under,
        },
        "confidence_interval_95": [round(x*100, 1) for x in sim.confidence_interval_95],
        "n_simulations": req.n_sims,
    }


@app.post("/simulate/nba")
def simulate_nba(req: NBARequest):
    """Run Monte Carlo NBA game simulation."""
    sim = nba_game_sim(
        home_off_rtg=req.home_off_rtg,
        home_def_rtg=req.home_def_rtg,
        away_off_rtg=req.away_off_rtg,
        away_def_rtg=req.away_def_rtg,
        home_pace=req.home_pace,
        away_pace=req.away_pace,
        back_to_back_home=req.back_to_back_home,
        back_to_back_away=req.back_to_back_away,
        spread=req.spread,
        total_line=req.total_line,
        n_sims=req.n_sims,
    )
    return {
        "matchup": {"home": req.home_team, "away": req.away_team},
        "probabilities": {
            "home_win": round(sim.home_win_prob * 100, 1),
            "away_win": round(sim.away_win_prob * 100, 1),
            "home_cover_spread": round(sim.spread_cover_prob * 100, 1),
            "over": round(sim.over_prob * 100, 1),
        },
        "predicted_scores": {
            "home_median": round(sim.median_home_score, 1),
            "away_median": round(sim.median_away_score, 1),
        },
        "flags": {
            "home_b2b": req.back_to_back_home,
            "away_b2b": req.back_to_back_away,
        },
    }


@app.post("/simulate/nfl")
def simulate_nfl(req: NFLRequest):
    """Run Monte Carlo NFL game simulation."""
    sim = nfl_game_sim(
        home_dvoa=req.home_dvoa,
        away_dvoa=req.away_dvoa,
        home_epa=req.home_epa,
        away_epa=req.away_epa,
        weather_factor=req.weather_factor,
        short_week_home=req.short_week_home,
        short_week_away=req.short_week_away,
        spread=req.spread,
        total_line=req.total_line,
        n_sims=req.n_sims,
    )
    return {
        "matchup": {"home": req.home_team, "away": req.away_team},
        "probabilities": {
            "home_win": round(sim.home_win_prob * 100, 1),
            "away_win": round(sim.away_win_prob * 100, 1),
            "home_cover_spread": round(sim.spread_cover_prob * 100, 1),
            "over": round(sim.over_prob * 100, 1),
        },
        "flags": {
            "bad_weather": req.weather_factor < 0.95,
            "home_short_week": req.short_week_home,
            "away_short_week": req.short_week_away,
        },
    }


# ── Bankroll ───────────────────────────────────────────────────────────────

@app.get("/bankroll")
def get_bankroll():
    """Get current bankroll state and statistics."""
    state = bankroll_mgr.snapshot()
    return {
        "starting": state.starting,
        "current": round(state.current, 2),
        "pnl": round(state.current - state.starting, 2),
        "pnl_pct": round((state.current - state.starting) / state.starting * 100, 2),
        "roi": round(state.roi * 100, 2),
        "win_rate": round(state.win_rate * 100, 2),
        "bets": {
            "placed": state.bets_placed,
            "won": state.bets_won,
            "lost": state.bets_lost,
            "push": state.bets_push,
        },
        "max_drawdown_pct": round(state.max_drawdown * 100, 2),
        "clv_avg": round(state.clv_avg * 100, 4),
        "high_water_mark": round(state.high_water_mark, 2),
    }


@app.get("/bankroll/history")
def get_bankroll_history(days: int = 30):
    """Return daily bankroll snapshots for the equity curve chart."""
    import sqlite3, pathlib
    db_path = pathlib.Path("./db/kalishi_edge.db")
    snapshots: list[dict] = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                "SELECT snapshot_date, bankroll, pnl, roi_pct FROM bankroll_snapshots "
                "ORDER BY snapshot_date DESC LIMIT ?",
                (days,)
            ).fetchall()
            conn.close()
            snapshots = [
                {"date": r[0], "bankroll": r[1], "pnl": r[2], "roi_pct": r[3]}
                for r in reversed(rows)
            ]
        except Exception:
            pass
    if not snapshots:
        # Return seed point so dashboard chart renders immediately
        from datetime import datetime
        snapshots = [{"date": datetime.now().strftime("%Y-%m-%d"),
                      "bankroll": bankroll_mgr.current, "pnl": 0.0, "roi_pct": 0.0}]
    return {"history": snapshots, "count": len(snapshots)}


@app.get("/bets")
def get_bets(status: Optional[str] = None, sport: Optional[str] = None, limit: int = 50):
    """Get bet history with optional filters."""
    bets = bankroll_mgr.bets
    if status:
        bets = [b for b in bets if b.result == status]
    if sport:
        bets = [b for b in bets if b.sport.lower() == sport.lower()]
    bets = bets[-limit:]
    return {
        "bets": [
            {
                "id": b.id,
                "sport": b.sport,
                "event": b.event,
                "pick": b.pick,
                "odds": b.odds_dec,
                "stake": b.stake,
                "ev_pct": round(b.ev * 100, 2),
                "edge_pct": round(b.edge * 100, 2),
                "result": b.result or "pending",
                "pnl": round(b.pnl, 2),
                "strategy": b.strategy,
                "placed_at": b.placed_at.isoformat(),
            }
            for b in reversed(bets)
        ],
        "count": len(bets),
    }


@app.post("/bets")
async def place_bet(req: BetSlipRequest):
    """Record a new bet in the system."""
    decimal_odds = american_to_decimal(req.american_odds)
    ev_result = calculate_ev(1 - (1 / decimal_odds) + req.edge, decimal_odds)
    
    bet = bankroll_mgr.place_bet(
        sport=req.sport,
        event=req.event,
        market=req.market,
        pick=req.pick,
        american_odds=req.american_odds,
        stake=req.stake,
        ev=req.ev,
        edge=req.edge,
        strategy=req.strategy,
    )
    
    await broadcast({"type": "new_bet", "bet_id": bet.id, "event": req.event})
    
    return {"ok": True, "bet_id": bet.id, "bankroll_remaining": round(bankroll_mgr.current, 2)}


# ── Today's Picks ──────────────────────────────────────────────────────────

@app.get("/picks/today")
async def todays_picks():
    """
    Generate today's picks by running all agents.
    Fetches live odds and applies all models.
    """
    from agents.orchestrator import run_daily_picks
    picks = await run_daily_picks()
    return picks


# ── WebSocket for Live Dashboard ───────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        # Send initial state
        await ws.send_text(json.dumps({
            "type": "connected",
            "bankroll": bankroll_mgr.current,
            "ts": datetime.now().isoformat(),
        }))
        while True:
            # Heartbeat
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ── Performance Analytics ──────────────────────────────────────────────────

@app.get("/analytics/performance")
def analytics_performance():
    """Full CLV, ROI, edge-bucket, and agent-attribution breakdown."""
    from engine.analytics import build_performance_report
    raw = [
        {
            "sport":        b.sport,
            "market":       b.market,
            "stake":        b.stake,
            "pnl":          b.pnl if b.result else None,
            "result":       b.result,
            "edge_pct":     round(b.edge * 100, 2),
            "closing_odds": b.closing_odds,
            "strategy":     b.strategy,
            "placed_at":    b.placed_at.isoformat(),
        }
        for b in bankroll_mgr.bets
    ]
    return build_performance_report(raw)


# ── Line Shop — Best Available Odds Across Books ───────────────────────────

BOOKS_TO_QUERY = "draftkings,fanduel,betmgm,caesars,pointsbet,barstool,wynn"

@app.get("/lines/best")
async def best_lines(sport: str = "upcoming", limit: int = 10):
    """Return best available moneyline / spread per event across all major books."""
    api_key = os.getenv("ODDS_API_KEY", "")
    if not api_key:
        return {"markets": _mock_line_shop()}

    try:
        import httpx
    except ImportError:
        return {"markets": _mock_line_shop(), "note": "pip install httpx for live data"}

    sports_map = {
        "nfl": "americanfootball_nfl",
        "nba": "basketball_nba",
        "mlb": "baseball_mlb",
        "nhl": "icehockey_nhl",
    }
    live_sports = (
        list(sports_map.values()) if sport == "upcoming"
        else [sports_map.get(sport, sport)]
    )

    results = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for sp in live_sports:
                r = await client.get(
                    f"https://api.the-odds-api.com/v4/sports/{sp}/odds/",
                    params={
                        "apiKey": api_key,
                        "regions": "us",
                        "markets": "h2h,spreads",
                        "oddsFormat": "american",
                        "bookmakers": BOOKS_TO_QUERY,
                    },
                )
                if r.status_code == 200:
                    results.extend(r.json()[:3])
    except Exception as e:
        return {"markets": _mock_line_shop(), "error": str(e)}

    formatted = _format_line_shop(results[:limit])
    return {"markets": formatted}


def _format_line_shop(events: list) -> list:
    markets = []
    for ev in events:
        bms = ev.get("bookmakers", [])
        if not bms:
            continue
        entry = {
            "event":    f"{ev.get('away_team', 'Away')} @ {ev.get('home_team', 'Home')}",
            "sport":    ev.get("sport_key", ""),
            "commence": ev.get("commence_time", ""),
            "books":    {},
        }
        home = ev.get("home_team", "")
        for bm in bms:
            name = bm["key"]
            book_data: dict = {}
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt.get("outcomes", []):
                        side = "h2h_home" if o["name"] == home else "h2h_away"
                        book_data[side] = o["price"]
            if book_data:
                entry["books"][name] = book_data
        markets.append(entry)
    return markets


def _mock_line_shop() -> list:
    """Realistic multi-book demo — renders when no API key set."""
    return [
        {
            "event": "Lakers @ Celtics", "sport": "basketball_nba",
            "commence": "2026-04-06T23:30:00Z",
            "books": {
                "draftkings": {"h2h_home": -108, "h2h_away": -112},
                "fanduel":    {"h2h_home": -110, "h2h_away": -110},
                "betmgm":     {"h2h_home": -105, "h2h_away": -115},
                "caesars":    {"h2h_home": -112, "h2h_away": -108},
                "pointsbet":  {"h2h_home": +100, "h2h_away": -120},
            },
        },
        {
            "event": "Yankees @ Red Sox", "sport": "baseball_mlb",
            "commence": "2026-04-07T00:05:00Z",
            "books": {
                "draftkings": {"h2h_home": +105, "h2h_away": -125},
                "fanduel":    {"h2h_home": +108, "h2h_away": -128},
                "betmgm":     {"h2h_home": +110, "h2h_away": -130},
                "caesars":    {"h2h_home": +100, "h2h_away": -120},
                "pointsbet":  {"h2h_home": +112, "h2h_away": -132},
            },
        },
        {
            "event": "Chiefs @ Ravens", "sport": "americanfootball_nfl",
            "commence": "2026-04-06T22:00:00Z",
            "books": {
                "draftkings": {"h2h_home": -135, "h2h_away": +115},
                "fanduel":    {"h2h_home": -130, "h2h_away": +110},
                "betmgm":     {"h2h_home": -140, "h2h_away": +120},
                "caesars":    {"h2h_home": -132, "h2h_away": +112},
                "pointsbet":  {"h2h_home": -128, "h2h_away": +108},
            },
        },
        {
            "event": "Heat @ Bucks", "sport": "basketball_nba",
            "commence": "2026-04-07T01:30:00Z",
            "books": {
                "draftkings": {"h2h_home": -155, "h2h_away": +135},
                "fanduel":    {"h2h_home": -150, "h2h_away": +130},
                "betmgm":     {"h2h_home": -160, "h2h_away": +140},
                "caesars":    {"h2h_home": -152, "h2h_away": +132},
                "pointsbet":  {"h2h_home": -148, "h2h_away": +128},
            },
        },
        {
            "event": "Dodgers @ Giants", "sport": "baseball_mlb",
            "commence": "2026-04-07T02:10:00Z",
            "books": {
                "draftkings": {"h2h_home": +120, "h2h_away": -140},
                "fanduel":    {"h2h_home": +118, "h2h_away": -138},
                "betmgm":     {"h2h_home": +125, "h2h_away": -145},
                "caesars":    {"h2h_home": +115, "h2h_away": -135},
                "pointsbet":  {"h2h_home": +122, "h2h_away": -142},
            },
        },
    ]


# ── Sharp Line Movement Feed ───────────────────────────────────────────────

@app.get("/lines/movement")
def line_movement():
    """Recent significant line movements (sharp money indicator)."""
    # In production: pull from a time-series line DB.
    # Seeded with representative sharp-move examples.
    moves = [
        {"event": "Lakers @ Celtics",  "market": "Spread",    "from_odds": -108, "to_odds": -115, "delta": -7,  "book": "DraftKings", "sharp": True,  "sport": "nba", "age_mins": 12},
        {"event": "Yankees @ Red Sox", "market": "Moneyline", "from_odds": +105, "to_odds": +115, "delta": +10, "book": "FanDuel",    "sharp": True,  "sport": "mlb", "age_mins": 23},
        {"event": "Chiefs @ Ravens",   "market": "Spread",    "from_odds": -130, "to_odds": -140, "delta": -10, "book": "BetMGM",     "sharp": True,  "sport": "nfl", "age_mins": 47},
        {"event": "Dodgers @ Giants",  "market": "Total O/U", "from_odds": -110, "to_odds": -122, "delta": -12, "book": "Caesars",    "sharp": True,  "sport": "mlb", "age_mins": 58},
        {"event": "Heat @ Bucks",      "market": "Moneyline", "from_odds": -155, "to_odds": -148, "delta":  +7, "book": "PointsBet",  "sharp": False, "sport": "nba", "age_mins": 72},
        {"event": "Flyers @ Penguins", "market": "Puck Line", "from_odds": +110, "to_odds": +120, "delta": +10, "book": "DraftKings", "sharp": True,  "sport": "nhl", "age_mins": 89},
    ]
    return {"moves": moves, "count": len(moves)}


# ── Middle Finder ──────────────────────────────────────────────────────────

@app.get("/picks/middles")
async def middles_endpoint():
    """Middle opportunities: bet both sides of a spread for a win-win window."""
    # Seed realistic demo middles; expands with live data when Odds API key available.
    middles = [
        {
            "event": "Lakers @ Celtics", "sport": "nba",
            "leg_a": {"side": "Lakers +4.5",  "odds": -108, "book": "DraftKings", "stake": 108},
            "leg_b": {"side": "Celtics -2.5",  "odds": -108, "book": "BetMGM",    "stake": 108},
            "window": 2.0, "max_win": 188, "guaranteed_loss": -16, "ev_pct": 2.3,
        },
        {
            "event": "Chiefs @ Ravens", "sport": "nfl",
            "leg_a": {"side": "Chiefs +7",    "odds": -110, "book": "FanDuel",   "stake": 110},
            "leg_b": {"side": "Ravens -3",    "odds": -110, "book": "Caesars",   "stake": 110},
            "window": 4.0, "max_win": 200, "guaranteed_loss": -20, "ev_pct": 3.1,
        },
        {
            "event": "Yankees @ Red Sox", "sport": "mlb",
            "leg_a": {"side": "Yankees +1.5", "odds": -120, "book": "DraftKings", "stake": 120},
            "leg_b": {"side": "Red Sox -0.5", "odds": -115, "book": "PointsBet",  "stake": 115},
            "window": 1.0, "max_win": 168, "guaranteed_loss": -23, "ev_pct": 1.4,
        },
    ]
    return {"middles": middles, "count": len(middles)}


# ═══════════════════════════════════════════════════════════════════════════
# ── AI BRAIN ENDPOINTS ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/ai/chat")
async def ai_chat(req: ChatRequest):
    """
    Conversational AI interface with RAG augmentation.
    GPT-4o powered. Context-aware with conversation memory.
    """
    brain = _get_brain()
    if not brain:
        return {"response": "AI Brain not available — install openai package and set OPENAI_API_KEY", "available": False}
    if req.clear_history:
        brain.clear_history()
    response = await brain.chat(req.message)
    await broadcast_ai({"type": "ai_chat", "query": req.message[:80], "ts": datetime.now().isoformat()})
    return {"response": response, "available": brain.available, "model": "gpt-4o"}


@app.websocket("/ws/ai")
async def websocket_ai(ws: WebSocket):
    """
    Streaming AI WebSocket — token-by-token response streaming.
    Send: {"message": "your question"}
    Receive: {"type": "token", "delta": "..."} + {"type": "done"}
    """
    await ws.accept()
    _ai_ws_clients.append(ws)
    try:
        await ws.send_text(json.dumps({"type": "ready", "model": "gpt-4o", "rag": True}))
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            msg = data.get("message", "").strip()
            if not msg:
                continue
            brain = _get_brain()
            if not brain:
                await ws.send_text(json.dumps({"type": "error", "message": "AI Brain unavailable"}))
                continue
            await ws.send_text(json.dumps({"type": "thinking"}))
            full = []
            async for token in brain.stream_chat(msg):
                full.append(token)
                await ws.send_text(json.dumps({"type": "token", "delta": token}))
            await ws.send_text(json.dumps({"type": "done", "full_response": "".join(full)}))
    except WebSocketDisconnect:
        if ws in _ai_ws_clients:
            _ai_ws_clients.remove(ws)


@app.post("/ai/analyze-pick")
async def ai_analyze_pick(req: PickAnalysisRequest):
    """
    Full AI-powered pick analysis.
    Returns structured: conviction, reasoning, key edge, risks, action.
    """
    brain = _get_brain()
    if not brain:
        return {"error": "AI Brain unavailable", "conviction": "HOLD", "action": "MONITOR"}
    analysis = await brain.analyze_pick(
        sport=req.sport, event=req.event, market=req.market,
        edge_pct=req.edge_pct, ev_pct=req.ev_pct,
        our_prob=req.our_prob, implied_prob=req.implied_prob,
        american_odds=req.american_odds, stake=req.stake,
        additional_context=req.additional_context,
    )
    return {"analysis": analysis, "model": "gpt-4o"}


@app.get("/ai/briefing")
async def ai_daily_briefing():
    """Generate today's full AI-powered betting briefing."""
    brain = _get_brain()
    if not brain:
        return {"briefing": "AI Brain unavailable", "ts": datetime.now().isoformat()}
    from agents.orchestrator import run_daily_picks
    picks_data = await run_daily_picks()
    picks    = picks_data.get("picks", [])
    bankroll = bankroll_mgr.snapshot()
    market_summary = {
        "bankroll": round(bankroll.current, 2),
        "roi_pct":  round(bankroll.roi * 100, 2),
        "win_rate": round(bankroll.win_rate * 100, 2),
        "open_bets": bankroll.bets_placed,
    }
    briefing = await brain.generate_daily_briefing(picks, market_summary)
    return {"briefing": briefing, "ts": datetime.now().isoformat()}


@app.get("/ai/status")
def ai_status():
    """Check status of all AI subsystems."""
    brain = _get_brain()
    steam = _get_steam()
    rag_stats: dict = {}
    try:
        from rag.embeddings import get_store
        rag_stats = get_store().stats()
    except Exception:
        pass
    return {
        "brain":       {"available": brain.available if brain else False, "model": "gpt-4o"},
        "rag":         rag_stats,
        "steam":       steam.stats() if steam else {"available": False},
        "ts":          datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# ── INTELLIGENCE ENDPOINTS ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/intelligence/steam")
def get_steam_alerts(limit: int = 30, sharp_only: bool = False, sport: Optional[str] = None):
    """Real-time sharp money / steam move alerts."""
    detector = _get_steam()
    if not detector:
        return {"moves": _get_mock_steam_alerts(), "source": "mock"}
    alerts = detector.get_sharp_alerts(limit) if sharp_only else detector.get_alerts(limit, sport)
    if not alerts:
        alerts = _get_mock_steam_alerts()
    return {"moves": alerts, "count": len(alerts), "stats": detector.stats()}


@app.post("/intelligence/feed")
async def feed_line(req: LineFeedRequest):
    """Ingest a line observation into the steam detector."""
    detector = _get_steam()
    if not detector:
        return {"ok": False, "error": "Steam detector unavailable"}
    alert = detector.feed(
        event=req.event, sport=req.sport, market=req.market,
        book=req.book, outcome=req.outcome, odds=req.odds,
        public_home_pct=req.public_home_pct,
    )
    if alert:
        await broadcast({"type": "steam_alert", **alert.to_dict()})
        await broadcast_ai({"type": "steam_alert", "event": req.event})
        return {"ok": True, "alert": alert.to_dict()}
    return {"ok": True, "alert": None}


@app.post("/ai/consensus")
def ai_consensus(req: ConsensusRequest):
    """Full multi-signal consensus analysis for a single opportunity."""
    consensus = _get_consensus()
    if not consensus:
        return {"error": "Consensus engine unavailable"}
    result = consensus.analyze(
        event=req.event, sport=req.sport, market=req.market, outcome=req.outcome,
        model_prob=req.model_prob, market_odds=req.market_odds, sharp_odds=req.sharp_odds,
        steam_alert=req.steam_alert, rlm_signal=req.rlm_signal, injury_impact=req.injury_impact,
    )
    return result.to_dict()


# ═══════════════════════════════════════════════════════════════════════════
# ── RAG ENDPOINTS ───────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/rag/search")
def rag_search(req: RAGSearchRequest):
    """Semantic search across the RAG knowledge base."""
    retriever = _get_retriever()
    if not retriever:
        return {"results": {}, "error": "RAG unavailable — install chromadb and sentence-transformers"}
    results = retriever._store.multi_query(req.query, req.collections, req.n_per_collection)
    return {"query": req.query, "results": results}


@app.get("/rag/stats")
def rag_stats():
    """RAG vector store collection statistics."""
    try:
        from rag.embeddings import get_store
        return get_store().stats()
    except Exception as e:
        return {"ready": False, "error": str(e)}


def _get_mock_steam_alerts() -> list:
    """Demo steam alerts for when detector has no live data."""
    return [
        {"event": "Lakers @ Celtics",  "sport": "nba", "market": "Spread",    "from_odds": -108, "to_odds": -118, "delta": -10, "book": "DraftKings", "sharp": True,  "rlm": True,  "conviction": "HIGH",     "reason": "Line moved -10 in 3.2min | RLM: 68% public bets vs line move opposite", "age_mins": 8,  "detected_at": datetime.utcnow().isoformat()},
        {"event": "Yankees @ Red Sox", "sport": "mlb", "market": "Moneyline", "from_odds": +105, "to_odds": +120, "delta": +15, "book": "FanDuel",    "sharp": True,  "rlm": False, "conviction": "CRITICAL",  "reason": "Line moved +15 in 1.8min | Steam confirmed 3 books",                  "age_mins": 14, "detected_at": datetime.utcnow().isoformat()},
        {"event": "Chiefs @ Ravens",   "sport": "nfl", "market": "Spread",    "from_odds": -130, "to_odds": -145, "delta": -15, "book": "BetMGM",     "sharp": True,  "rlm": True,  "conviction": "CRITICAL",  "reason": "Steam: -15 in 4min | RLM: 74% public on Ravens vs sharp move",       "age_mins": 31, "detected_at": datetime.utcnow().isoformat()},
        {"event": "Dodgers @ Giants",  "sport": "mlb", "market": "Total O/U", "from_odds": -110, "to_odds": -125, "delta": -15, "book": "Caesars",    "sharp": True,  "rlm": False, "conviction": "HIGH",     "reason": "Under steam | hit cold number 8.5",                                 "age_mins": 52, "detected_at": datetime.utcnow().isoformat()},
        {"event": "Flyers @ Penguins", "sport": "nhl", "market": "Puck Line", "from_odds": +110, "to_odds": +125, "delta": +15, "book": "PointsBet",  "sharp": False, "rlm": False, "conviction": "MEDIUM",   "reason": "Moderate line drift",                                               "age_mins": 87, "detected_at": datetime.utcnow().isoformat()},
    ]


# ── MCP Tool Manifest ──────────────────────────────────────────────────────

@app.get("/mcp/tools")
def mcp_tools():
    """Return MCP tool manifest for AI agent discovery."""
    return {
        "protocol": "MCP/1.0",
        "agent": "KALISHI EDGE",
        "version": "2.0.0",
        "capabilities": ["quantitative", "ai_brain", "rag", "steam_intelligence", "streaming"],
        "tools": [
            # ── Quantitative ──
            {"name": "kelly_criterion",       "endpoint": "/kelly",                  "method": "POST", "category": "quant",         "description": "Optimal Kelly bet sizing"},
            {"name": "expected_value",         "endpoint": "/ev",                     "method": "POST", "category": "quant",         "description": "Expected value calculation"},
            {"name": "arbitrage_finder",       "endpoint": "/arbitrage",              "method": "POST", "category": "quant",         "description": "Cross-book arbitrage finder"},
            {"name": "no_vig_probability",     "endpoint": "/no-vig",                 "method": "GET",  "category": "quant",         "description": "No-vig true market probability"},
            {"name": "profit_machine",         "endpoint": "/profit-machine",         "method": "POST", "category": "quant",         "description": "Profit Machine Protocol 2.0"},
            {"name": "acts_of_god",            "endpoint": "/acts-of-god",            "method": "POST", "category": "quant",         "description": "Exogenous factor adjustments"},
            # ── Simulations ──
            {"name": "simulate_mlb",           "endpoint": "/simulate/mlb",           "method": "POST", "category": "simulation",    "description": "MLB Monte Carlo (50k sims, sabermetrics)"},
            {"name": "simulate_nba",           "endpoint": "/simulate/nba",           "method": "POST", "category": "simulation",    "description": "NBA Monte Carlo (pace, ratings, B2B)"},
            {"name": "simulate_nfl",           "endpoint": "/simulate/nfl",           "method": "POST", "category": "simulation",    "description": "NFL Monte Carlo (DVOA, EPA, weather)"},
            # ── Bankroll ──
            {"name": "get_bankroll",           "endpoint": "/bankroll",               "method": "GET",  "category": "bankroll",      "description": "Live bankroll state + stats"},
            {"name": "bankroll_history",       "endpoint": "/bankroll/history",       "method": "GET",  "category": "bankroll",      "description": "Daily equity curve"},
            {"name": "place_bet",              "endpoint": "/bets",                   "method": "POST", "category": "bankroll",      "description": "Record a bet"},
            # ── Picks ──
            {"name": "todays_picks",           "endpoint": "/picks/today",            "method": "GET",  "category": "picks",         "description": "AI + model generated picks"},
            {"name": "middles_finder",         "endpoint": "/picks/middles",          "method": "GET",  "category": "picks",         "description": "Middle window opportunities"},
            # ── Analytics ──
            {"name": "analytics_performance",  "endpoint": "/analytics/performance",  "method": "GET",  "category": "analytics",     "description": "CLV + ROI + edge-bucket attribution"},
            # ── Line Shopping ──
            {"name": "line_shop",              "endpoint": "/lines/best",             "method": "GET",  "category": "lines",         "description": "Best available odds across all books"},
            {"name": "sharp_moves",            "endpoint": "/lines/movement",         "method": "GET",  "category": "lines",         "description": "Sharp line movement feed"},
            # ── AI Brain ──
            {"name": "ai_chat",                "endpoint": "/ai/chat",                "method": "POST", "category": "ai",            "description": "GPT-4o conversational analysis with RAG"},
            {"name": "ai_chat_stream",         "endpoint": "/ws/ai",                  "method": "WS",   "category": "ai",            "description": "Streaming AI chat WebSocket"},
            {"name": "ai_analyze_pick",        "endpoint": "/ai/analyze-pick",        "method": "POST", "category": "ai",            "description": "Structured AI pick analysis: conviction + reasoning"},
            {"name": "ai_daily_briefing",      "endpoint": "/ai/briefing",            "method": "GET",  "category": "ai",            "description": "Full AI-powered daily briefing"},
            {"name": "ai_consensus",           "endpoint": "/ai/consensus",           "method": "POST", "category": "ai",            "description": "Multi-signal consensus analysis"},
            {"name": "ai_status",              "endpoint": "/ai/status",              "method": "GET",  "category": "ai",            "description": "AI subsystems health check"},
            # ── Intelligence ──
            {"name": "steam_alerts",           "endpoint": "/intelligence/steam",     "method": "GET",  "category": "intelligence",  "description": "Real-time steam + RLM alerts"},
            {"name": "feed_line",              "endpoint": "/intelligence/feed",      "method": "POST", "category": "intelligence",  "description": "Feed live line for steam detection"},
            # ── RAG ──
            {"name": "rag_search",             "endpoint": "/rag/search",             "method": "POST", "category": "rag",           "description": "Semantic search over knowledge base"},
            {"name": "rag_stats",              "endpoint": "/rag/stats",              "method": "GET",  "category": "rag",           "description": "Vector store collection stats"},
        ]
    }


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8420"))
    print(f"🎯 KALISHI EDGE MCP Server starting on port {port}")
    uvicorn.run(
        "mcp.server:app", host="0.0.0.0", port=port,
        reload=True, reload_dirs=["mcp", "engine", "agents", "data"],
    )
