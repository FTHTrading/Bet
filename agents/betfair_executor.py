"""
Betfair Exchange auto-execution engine.

Matches Kalishi Edge picks to live Betfair markets, verifies price/liquidity,
applies safety gates, and places bets (or runs dry-run simulation).

Safety gates (all must pass before any real money moves):
  1. Edge ≥ MIN_EDGE_TO_EXECUTE (default 4%)
  2. Decimal odds within [MIN_ODDS_DECIMAL, MAX_ODDS_DECIMAL]
  3. Live Betfair price ≥ 97% of our target price
  4. Available liquidity ≥ 5× our stake
  5. Stake ≤ MAX_SINGLE_BET (hard cap)
  6. dry_run=True by default — must explicitly disable to place real bets
"""

import logging
from typing import Optional

from data.feeds.betfair import BetfairClient, SPORT_EVENT_TYPE_IDS

logger = logging.getLogger(__name__)

# ── Safety parameters ────────────────────────────────────────────────────────
MIN_EDGE_TO_EXECUTE    = 0.04    # 4% minimum edge
MIN_ODDS_DECIMAL       = 1.15   # skip heavy favourites
MAX_ODDS_DECIMAL       = 15.0   # skip extreme underdogs
MAX_SINGLE_BET         = 500.0  # hard cap per bet (account currency)
MIN_BET                = 2.0    # Betfair minimum stake
MIN_LIQUIDITY_MULTIPLE = 5.0    # liquidity must be ≥ 5× our stake


# ── Odds conversion helpers ───────────────────────────────────────────────────

def american_to_decimal(american: int) -> float:
    if american > 0:
        return round(american / 100 + 1, 3)
    return round(100 / abs(american) + 1, 3)


def decimal_to_american(decimal: float) -> int:
    if decimal >= 2.0:
        return int((decimal - 1) * 100)
    return int(-100 / (decimal - 1))


# ── Market matching ───────────────────────────────────────────────────────────

def find_betfair_market(
    client: BetfairClient,
    sport: str,
    team: str,
    opponent: str,
) -> Optional[dict]:
    """
    Locate the Match Odds market on Betfair for a given game.
    Returns a dict with market_id and runners, or None if not found.
    """
    event_type_id = SPORT_EVENT_TYPE_IDS.get(sport.lower())
    if not event_type_id:
        logger.warning("No Betfair event type mapped for sport: %s", sport)
        return None

    try:
        events = client.list_events(event_type_id, text_query=team)
    except Exception as exc:
        logger.error("list_events error: %s", exc)
        return None

    if not events:
        return None

    event_ids = [e["event"]["id"] for e in events[:10]]

    try:
        markets = client.list_market_catalogue(event_ids, market_types=["MATCH_ODDS"])
    except Exception as exc:
        logger.error("list_market_catalogue error: %s", exc)
        return None

    team_lc     = team.lower()
    opponent_lc = opponent.lower()

    for market in markets:
        runners = market.get("runners", [])
        names   = [r.get("runnerName", "").lower() for r in runners]
        if any(team_lc in n for n in names) and any(opponent_lc in n for n in names):
            return {
                "market_id":   market["marketId"],
                "market_name": market.get("marketName", ""),
                "event_name":  market.get("event", {}).get("name", ""),
                "start_time":  market.get("marketStartTime", ""),
                "runners": [
                    {"name": r["runnerName"], "selection_id": r["selectionId"]}
                    for r in runners
                ],
            }

    return None


def get_best_back_price(
    client: BetfairClient,
    market_id: str,
    selection_id: int,
) -> Optional[dict]:
    """
    Return the best available BACK price and depth for a selection.
    {"price": float, "size": float} or None.
    """
    try:
        books = client.list_market_book([market_id])
    except Exception as exc:
        logger.error("list_market_book error: %s", exc)
        return None

    for book in books:
        for runner in book.get("runners", []):
            if runner["selectionId"] == selection_id:
                avail = runner.get("ex", {}).get("availableToBack", [])
                if avail:
                    best = avail[0]
                    return {"price": best["price"], "size": best["size"]}

    return None


# ── Single pick execution ─────────────────────────────────────────────────────

def execute_pick(
    client:   BetfairClient,
    pick:     dict,
    bankroll: float,
    dry_run:  bool = True,
) -> dict:
    """
    Attempt to execute one pick on Betfair.

    Expected pick keys:
      sport, team (our pick), opponent, edge_pct, kelly_fraction, american_odds

    Returns a result dict describing what happened (or would happen in dry_run).
    dry_run=True by default — no real money placed unless explicitly False.
    """
    sport        = pick.get("sport", "").lower()
    team         = pick.get("team") or pick.get("pick", "")
    opponent     = pick.get("opponent", "")
    edge_pct     = float(pick.get("edge_pct", 0.0))
    kelly_frac   = float(pick.get("kelly_fraction", 0.0))
    american_odds = int(pick.get("american_odds", 0))

    result: dict = {
        "pick":       f"{team} vs {opponent}",
        "sport":      sport,
        "edge_pct":   edge_pct,
        "status":     "NOT_EXECUTED",
        "reason":     None,
        "bet_id":     None,
        "stake":      None,
        "price":      None,
        "dry_run":    dry_run,
    }

    # ── Gate 1: Edge threshold ────────────────────────────────────────────────
    if edge_pct < MIN_EDGE_TO_EXECUTE:
        result["reason"] = f"Edge {edge_pct:.1%} below minimum {MIN_EDGE_TO_EXECUTE:.0%}"
        return result

    # ── Gate 2: Odds range ───────────────────────────────────────────────────
    target_decimal = american_to_decimal(american_odds)
    if not (MIN_ODDS_DECIMAL <= target_decimal <= MAX_ODDS_DECIMAL):
        result["reason"] = (
            f"Target odds {target_decimal:.2f} outside acceptable range "
            f"[{MIN_ODDS_DECIMAL}, {MAX_ODDS_DECIMAL}]"
        )
        return result

    # ── Market lookup ────────────────────────────────────────────────────────
    market_info = find_betfair_market(client, sport, team, opponent)
    if not market_info:
        result["reason"] = "No matching Betfair market found"
        return result

    selection = next(
        (r for r in market_info["runners"] if team.lower() in r["name"].lower()),
        None,
    )
    if not selection:
        result["reason"] = f"Runner '{team}' not found in market ({market_info['market_name']})"
        return result

    # ── Live price check ──────────────────────────────────────────────────────
    price_info = get_best_back_price(client, market_info["market_id"], selection["selection_id"])
    if not price_info:
        result["reason"] = "No available back price on Betfair"
        return result

    live_price     = price_info["price"]
    available_size = price_info["size"]

    # Gate 3: Price drift — don't bet if market has moved badly against us
    if live_price < target_decimal * 0.97:
        result["reason"] = (
            f"Live price {live_price:.2f} too far below target {target_decimal:.2f} "
            f"(line has moved)"
        )
        return result

    # ── Stake sizing (quarter-Kelly) ──────────────────────────────────────────
    kelly_stake = bankroll * kelly_frac * 0.25
    stake       = min(kelly_stake, MAX_SINGLE_BET)
    stake       = round(max(stake, MIN_BET), 2)

    # Gate 4: Liquidity
    if available_size < stake * MIN_LIQUIDITY_MULTIPLE:
        result["reason"] = (
            f"Insufficient liquidity: £{available_size:.2f} available, "
            f"need £{stake * MIN_LIQUIDITY_MULTIPLE:.2f} (5× stake)"
        )
        return result

    result.update({
        "market_id":        market_info["market_id"],
        "event_name":       market_info["event_name"],
        "market_name":      market_info["market_name"],
        "selection":        selection["name"],
        "selection_id":     selection["selection_id"],
        "price":            live_price,
        "stake":            stake,
        "potential_profit": round(stake * (live_price - 1), 2),
        "start_time":       market_info.get("start_time", ""),
    })

    if dry_run:
        result["status"] = "DRY_RUN"
        result["reason"] = "Simulation only — set dry_run=false to place real bets"
        return result

    # ── Place the bet ─────────────────────────────────────────────────────────
    try:
        order = client.place_bet(
            market_id=market_info["market_id"],
            selection_id=selection["selection_id"],
            side="BACK",
            size=stake,
            price=live_price,
            customer_ref=f"ke-{sport[:3]}-{team[:8].replace(' ', '')}",
        )
    except Exception as exc:
        result["status"] = "ERROR"
        result["reason"] = str(exc)
        return result

    reports = order.get("instructionReports", [])
    if reports and reports[0].get("status") == "SUCCESS":
        result["status"] = "PLACED"
        result["bet_id"] = reports[0].get("betId", "")
        result["reason"] = "Bet placed successfully"
        logger.info(
            "BET PLACED: %s @ %.2f stake=%.2f bet_id=%s",
            team, live_price, stake, result["bet_id"],
        )
    else:
        result["status"] = "FAILED"
        result["reason"] = str(order.get("errorCode") or reports)
        logger.error("Bet placement failed: %s", result["reason"])

    return result


# ── Batch auto-execution ──────────────────────────────────────────────────────

def auto_execute_picks(
    client:   BetfairClient,
    picks:    list,
    bankroll: float,
    min_edge: float = MIN_EDGE_TO_EXECUTE,
    dry_run:  bool  = True,
) -> dict:
    """
    Auto-execute all picks that meet the edge threshold.

    IMPORTANT: dry_run=True by default.
    Explicitly pass dry_run=False to place real bets.
    """
    results         = []
    placed          = 0
    skipped_edge    = 0
    total_risked    = 0.0
    total_potential = 0.0

    for pick in picks:
        if float(pick.get("edge_pct", 0.0)) < min_edge:
            skipped_edge += 1
            continue

        res = execute_pick(client, pick, bankroll, dry_run=dry_run)
        results.append(res)

        if res["status"] in ("PLACED", "DRY_RUN"):
            placed       += 1
            total_risked += res.get("stake") or 0.0
            total_potential += res.get("potential_profit") or 0.0

    return {
        "mode":               "DRY_RUN" if dry_run else "LIVE",
        "total_picks_in":     len(picks),
        "eligible":           len(results),
        "skipped_below_edge": skipped_edge,
        "placed":             placed,
        "total_risked":       round(total_risked, 2),
        "total_potential":    round(total_potential, 2),
        "results":            results,
    }


# ── P&L reporting ─────────────────────────────────────────────────────────────

def get_pnl_summary(client: BetfairClient) -> dict:
    """Compute P&L summary from Betfair settled orders."""
    try:
        orders = client.list_cleared_orders()
    except Exception as exc:
        return {"error": str(exc), "settled_bets": 0}

    if not orders:
        return {
            "settled_bets": 0,
            "wins":         0,
            "losses":       0,
            "win_rate":     0.0,
            "total_staked": 0.0,
            "total_profit": 0.0,
            "roi":          0.0,
            "recent_orders": [],
        }

    profits      = [o.get("profit", 0.0) for o in orders]
    staked       = [o.get("sizeSettled", 0.0) for o in orders]
    wins         = sum(1 for p in profits if p > 0)
    losses       = sum(1 for p in profits if p < 0)
    total_profit = sum(profits)
    total_staked = sum(staked)

    # Group by sport/market for breakdown
    by_market: dict = {}
    for o in orders:
        mname = o.get("marketName", "Unknown")
        by_market.setdefault(mname, {"bets": 0, "profit": 0.0, "staked": 0.0})
        by_market[mname]["bets"]   += 1
        by_market[mname]["profit"] += o.get("profit", 0.0)
        by_market[mname]["staked"] += o.get("sizeSettled", 0.0)

    return {
        "settled_bets":  len(orders),
        "wins":          wins,
        "losses":        losses,
        "win_rate":      round(wins / len(orders), 3),
        "total_staked":  round(total_staked, 2),
        "total_profit":  round(total_profit, 2),
        "roi":           round(total_profit / total_staked, 3) if total_staked else 0.0,
        "by_market":     {
            k: {**v, "profit": round(v["profit"], 2), "roi": round(v["profit"] / v["staked"], 3) if v["staked"] else 0.0}
            for k, v in sorted(by_market.items(), key=lambda x: x[1]["profit"], reverse=True)
        },
        "recent_orders": orders[:20],
    }
