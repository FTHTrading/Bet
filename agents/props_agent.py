"""
Player Props Agent — Cross-Sport Individual Bet Analysis
=========================================================
Analyzes player prop bets across NBA, NFL, MLB, NHL using:
- Usage rate / snap count / plate appearance analysis
- Matchup defensive ratings vs position
- Pace/tempo adjustments (NBA: pace; NFL: pass volume; MLB: park)
- Season trends vs recent form (regression detection)
- Injury & lineup news impact factors
- Kelly sizing on each prop over/under
"""
from __future__ import annotations
from typing import Optional
import math


# ─── Shared EV + Kelly helpers ────────────────────────────────────────────────

def _prop_ev(our_prob: float, decimal_odds: float) -> dict:
    """Return edge, ev_pct and confidence label."""
    implied = 1.0 / decimal_odds
    edge = our_prob - implied
    ev = (our_prob * (decimal_odds - 1) - (1 - our_prob))
    ev_pct = ev / 1.0 * 100
    if edge > 0.08:
        conf = "STRONG_VALUE"
    elif edge > 0.04:
        conf = "VALUE"
    elif edge > 0.00:
        conf = "LEAN"
    else:
        conf = "NO_VALUE"
    return {"edge": edge, "ev_pct": round(ev_pct, 2), "confidence": conf, "positive": edge > 0}


def _kelly_prop(our_prob: float, decimal_odds: float, bankroll: float) -> dict:
    """Quarter-Kelly on a prop. Returns fraction and dollar amount."""
    implied = 1.0 / decimal_odds
    if our_prob <= implied:
        return {"fraction": 0.0, "bet_amount": 0.0}
    full_kelly = (our_prob * decimal_odds - 1) / (decimal_odds - 1)
    quarter_kelly = full_kelly * 0.25
    return {
        "fraction": round(quarter_kelly, 4),
        "bet_amount": round(bankroll * quarter_kelly, 2),
    }


def _american_to_dec(american: int) -> float:
    if american > 0:
        return (american / 100) + 1
    return (100 / abs(american)) + 1


def _dec_to_american(dec: float) -> int:
    if dec >= 2.0:
        return int((dec - 1) * 100)
    return int(-100 / (dec - 1))


# ═══════════════════════════════════════════════════════════════════════════════
# ── NBA PLAYER PROPS ───────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_nba_prop(
    player_name: str,
    prop_type: str,          # "points", "rebounds", "assists", "3pm", "pra", "blocks", "steals"
    line: float,             # The o/u line (e.g. 27.5 for points)
    american_odds_over: int,
    american_odds_under: int,
    # Season averages
    season_avg: float,
    # Matchup
    opp_def_rtg: float = 112.0,       # opponent defensive rating
    opp_pace: float = 100.0,           # opponent pace factor
    # Usage / role
    usage_rate: float = 0.25,
    minutes_avg: float = 33.0,
    # Recent form
    last_5_avg: Optional[float] = None,
    # Situational
    back_to_back: bool = False,
    home_game: bool = True,
    bankroll: float = 10_000,
) -> dict:
    """
    NBA player prop analysis — points, rebounds, assists, 3PM, PRA, blocks, steals.
    Returns the best direction (over/under) with edge, EV, and recommended stake.
    """
    # ── Projection engine ──
    # Matchup factor: vs defense quality
    # 110 = average def_rtg. Higher = weaker defense = more scoring
    def_factor = (opp_def_rtg - 110.0) / 10.0  # roughly ±0.1 per 1pt def_rtg diff

    # Pace factor: faster pace = more possessions = more counting stats
    pace_factor = (opp_pace - 100.0) / 100.0 * 0.05

    # Usage amplifies projection for scoring/rebounding
    usage_multiplier = usage_rate / 0.25

    if prop_type in ("points", "pra"):
        proj = season_avg * (1 + def_factor * 0.08) * usage_multiplier * (1 + pace_factor)
    elif prop_type in ("rebounds",):
        proj = season_avg * (1 + pace_factor * 0.5) * (1 if usage_rate > 0.22 else 0.95)
    elif prop_type in ("assists",):
        proj = season_avg * (1 + def_factor * 0.04) * (1 + pace_factor * 0.3)
    elif prop_type in ("3pm",):
        proj = season_avg * (1 + def_factor * 0.05)
    elif prop_type in ("blocks", "steals"):
        proj = season_avg * (1 + pace_factor * 0.2)
    else:
        proj = season_avg

    # Recent form regression: blend season avg and last-5 (70/30)
    if last_5_avg is not None:
        proj = proj * 0.70 + last_5_avg * 0.30

    # Situational adjustments
    if back_to_back:
        proj *= 0.94  # ~6% drop on B2B
    if not home_game:
        proj *= 0.97  # small road penalty

    # Minutes adjustment: regression if avg is inflated
    if minutes_avg < 28.0:
        proj *= (minutes_avg / 33.0)

    proj = round(proj, 2)

    # ── Win probability ──
    # Model the stat as log-normal; variance based on prop type
    variance_map = {"points": 0.28, "rebounds": 0.35, "assists": 0.38, "3pm": 0.55,
                    "pra": 0.22, "blocks": 0.70, "steals": 0.65}
    sigma = variance_map.get(prop_type, 0.30)

    # Prob(stat > line) via normal approximation around projection
    if proj <= 0:
        over_prob = 0.10
    else:
        z = (math.log(line / proj)) / sigma if proj > 0 else 99
        over_prob = 1 - _normal_cdf(z)
    over_prob = round(max(0.05, min(0.95, over_prob)), 4)
    under_prob = round(1 - over_prob, 4)

    # ── EV for each side ──
    dec_over = _american_to_dec(american_odds_over)
    dec_under = _american_to_dec(american_odds_under)

    ev_over = _prop_ev(over_prob, dec_over)
    ev_under = _prop_ev(under_prob, dec_under)
    kelly_over = _kelly_prop(over_prob, dec_over, bankroll)
    kelly_under = _kelly_prop(under_prob, dec_under, bankroll)

    best_direction = "over" if ev_over["edge"] > ev_under["edge"] else "under"
    best_ev = ev_over if best_direction == "over" else ev_under
    best_kelly = kelly_over if best_direction == "over" else kelly_under
    best_prob = over_prob if best_direction == "over" else under_prob
    best_am_odds = american_odds_over if best_direction == "over" else american_odds_under

    return {
        "player": player_name,
        "sport": "NBA",
        "prop_type": prop_type,
        "line": line,
        "direction": best_direction,
        "american_odds": best_am_odds,
        "projection": proj,
        "our_prob": round(best_prob * 100, 1),
        "implied_prob": round((1 / _american_to_dec(best_am_odds)) * 100, 1),
        "edge_pct": round(best_ev["edge"] * 100, 2),
        "ev_pct": best_ev["ev_pct"],
        "kelly_fraction": best_kelly["fraction"],
        "recommended_stake": best_kelly["bet_amount"],
        "confidence": best_ev["confidence"],
        "factors": {
            "def_factor": round(def_factor, 3),
            "pace_factor": round(pace_factor, 3),
            "back_to_back": back_to_back,
            "recent_form": last_5_avg,
        },
        "both_sides": {
            "over": {"prob": round(over_prob * 100, 1), "edge_pct": round(ev_over["edge"] * 100, 2), "confidence": ev_over["confidence"]},
            "under": {"prob": round(under_prob * 100, 1), "edge_pct": round(ev_under["edge"] * 100, 2), "confidence": ev_under["confidence"]},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── NFL PLAYER PROPS ───────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_nfl_prop(
    player_name: str,
    prop_type: str,     # "passing_yards", "rushing_yards", "receiving_yards", "pass_tds", "rush_tds", "receptions"
    line: float,
    american_odds_over: int,
    american_odds_under: int,
    season_avg: float,
    # Matchup
    opp_def_dvoa: float = 0.0,          # Defense DVOA vs position (negative = tough)
    opp_pass_def_rank: int = 16,         # 1=best, 32=worst pass defense
    opp_rush_def_rank: int = 16,
    # Context
    game_total: float = 44.5,           # Over/under total
    pass_volume: float = 35.0,           # Projected pass attempts
    implied_team_score: float = 22.0,
    # Recent
    last_3_avg: Optional[float] = None,
    # Situational
    weather_wind_mph: float = 0.0,
    dome_game: bool = False,
    back_to_back_short_week: bool = False,
    bankroll: float = 10_000,
) -> dict:
    """NFL player prop analysis."""
    # Passing props
    if prop_type == "passing_yards":
        def_adj = (opp_pass_def_rank - 16) / 16 * 0.10  # weak defense = more yards
        pace_adj = (pass_volume - 35) / 35 * 0.05
        wind_adj = -min(0.12, weather_wind_mph / 100) if not dome_game else 0.0
        proj = season_avg * (1 + def_adj + pace_adj + wind_adj)

    elif prop_type == "rushing_yards":
        def_adj = (opp_rush_def_rank - 16) / 16 * 0.10
        proj = season_avg * (1 + def_adj)
        if implied_team_score < 17:  # blowout concern — team may abandon run
            proj *= 0.90

    elif prop_type == "receiving_yards":
        def_adj = (opp_pass_def_rank - 16) / 16 * 0.08
        proj = season_avg * (1 + def_adj)

    elif prop_type in ("pass_tds", "rush_tds"):
        # TD props are high variance, use simpler model
        # Implied TDs from team scoring * position share
        if prop_type == "pass_tds":
            implied_tds = (implied_team_score / 7.0) * 0.65  # ~65% of TDs are passing
        else:
            implied_tds = (implied_team_score / 7.0) * 0.30
        proj = implied_tds * (season_avg / max(0.1, (implied_tds * 1.0)))

    elif prop_type == "receptions":
        def_adj = (opp_pass_def_rank - 16) / 16 * 0.06
        vol_adj = (pass_volume - 35) / 35 * 0.04
        proj = season_avg * (1 + def_adj + vol_adj)

    else:
        proj = season_avg

    if last_3_avg is not None:
        proj = proj * 0.65 + last_3_avg * 0.35

    if back_to_back_short_week:
        proj *= 0.93

    proj = round(max(0.0, proj), 2)

    # Variance by prop type
    sigma_map = {
        "passing_yards": 0.26, "rushing_yards": 0.38, "receiving_yards": 0.40,
        "pass_tds": 0.85, "rush_tds": 1.10, "receptions": 0.35,
    }
    sigma = sigma_map.get(prop_type, 0.35)

    if proj <= 0 or line <= 0:
        over_prob = 0.45
    else:
        z = (math.log(max(line, 0.5) / max(proj, 0.5))) / sigma
        over_prob = 1 - _normal_cdf(z)
    over_prob = round(max(0.05, min(0.95, over_prob)), 4)
    under_prob = round(1 - over_prob, 4)

    dec_over = _american_to_dec(american_odds_over)
    dec_under = _american_to_dec(american_odds_under)
    ev_over = _prop_ev(over_prob, dec_over)
    ev_under = _prop_ev(under_prob, dec_under)
    kelly_over = _kelly_prop(over_prob, dec_over, bankroll)
    kelly_under = _kelly_prop(under_prob, dec_under, bankroll)

    best_direction = "over" if ev_over["edge"] > ev_under["edge"] else "under"
    best_ev = ev_over if best_direction == "over" else ev_under
    best_kelly = kelly_over if best_direction == "over" else kelly_under
    best_prob = over_prob if best_direction == "over" else under_prob
    best_am_odds = american_odds_over if best_direction == "over" else american_odds_under

    return {
        "player": player_name,
        "sport": "NFL",
        "prop_type": prop_type,
        "line": line,
        "direction": best_direction,
        "american_odds": best_am_odds,
        "projection": proj,
        "our_prob": round(best_prob * 100, 1),
        "implied_prob": round((1 / _american_to_dec(best_am_odds)) * 100, 1),
        "edge_pct": round(best_ev["edge"] * 100, 2),
        "ev_pct": best_ev["ev_pct"],
        "kelly_fraction": best_kelly["fraction"],
        "recommended_stake": best_kelly["bet_amount"],
        "confidence": best_ev["confidence"],
        "factors": {
            "def_dvoa": opp_def_dvoa,
            "pass_def_rank": opp_pass_def_rank,
            "wind_adj": weather_wind_mph,
            "short_week": back_to_back_short_week,
        },
        "both_sides": {
            "over": {"prob": round(over_prob * 100, 1), "edge_pct": round(ev_over["edge"] * 100, 2), "confidence": ev_over["confidence"]},
            "under": {"prob": round(under_prob * 100, 1), "edge_pct": round(ev_under["edge"] * 100, 2), "confidence": ev_under["confidence"]},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── MLB PLAYER PROPS ───────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_mlb_prop(
    player_name: str,
    prop_type: str,   # "hits", "total_bases", "strikeouts", "rbis", "runs", "hrs"
    line: float,
    american_odds_over: int,
    american_odds_under: int,
    season_avg: float,
    # Pitching matchup
    opp_starter_fip: float = 4.00,
    opp_starter_k9: float = 8.5,        # strikeouts per 9 (for batter K props)
    # Batter context
    batter_hand: str = "R",              # "R", "L", "S"
    pitcher_hand: str = "R",
    batter_ba_vs_hand: Optional[float] = None,    # BA vs this pitcher handedness
    batter_slg_vs_hand: Optional[float] = None,
    # Environment
    park_factor: float = 1.00,
    temp_f: float = 72.0,
    wind_out: bool = False,
    wind_mph: float = 0.0,
    # Recent
    last_7_avg: Optional[float] = None,
    bankroll: float = 10_000,
) -> dict:
    """MLB player prop analysis."""
    # Matchup quality
    fip_factor = (4.50 - opp_starter_fip) / 4.50  # positive = worse pitcher = better for batter

    if prop_type == "hits":
        proj = season_avg * (1 + fip_factor * 0.12) * park_factor
        if batter_ba_vs_hand is not None:
            handedness_adj = (batter_ba_vs_hand - 0.250) / 0.250 * 0.08
            proj *= (1 + handedness_adj)

    elif prop_type == "total_bases":
        slugging_bonus = fip_factor * 0.15
        park_adj = park_factor * (1.03 if (wind_out and wind_mph > 10) else 1.0)
        temp_adj = 1 + max(0, (temp_f - 72) / 72) * 0.02
        proj = season_avg * (1 + slugging_bonus) * park_adj * temp_adj
        if batter_slg_vs_hand is not None:
            h_adj = (batter_slg_vs_hand - 0.420) / 0.420 * 0.08
            proj *= (1 + h_adj)

    elif prop_type == "strikeouts":
        # For PITCHER strikeout props
        k9_factor = opp_starter_k9 / 8.0  # more K/9 = more Ks
        proj = season_avg * k9_factor * (1 + fip_factor * 0.05)

    elif prop_type in ("rbis", "runs"):
        proj = season_avg * (1 + fip_factor * 0.10) * park_factor

    elif prop_type == "hrs":
        park_adj = park_factor * (1.05 if (wind_out and wind_mph > 12) else 1.0)
        proj = season_avg * (1 + fip_factor * 0.20) * park_adj

    else:
        proj = season_avg

    if last_7_avg is not None:
        proj = proj * 0.65 + last_7_avg * 0.35

    proj = round(max(0.0, proj), 2)

    # High variance for non-hits props (rare events per game)
    sigma_map = {
        "hits": 0.55, "total_bases": 0.45, "strikeouts": 0.30,
        "rbis": 0.70, "runs": 0.70, "hrs": 1.20,
    }
    sigma = sigma_map.get(prop_type, 0.55)

    if proj <= 0 or line <= 0:
        over_prob = 0.45
    else:
        z = (math.log(max(line, 0.1) / max(proj, 0.1))) / sigma
        over_prob = 1 - _normal_cdf(z)
    over_prob = round(max(0.05, min(0.95, over_prob)), 4)
    under_prob = round(1 - over_prob, 4)

    dec_over = _american_to_dec(american_odds_over)
    dec_under = _american_to_dec(american_odds_under)
    ev_over = _prop_ev(over_prob, dec_over)
    ev_under = _prop_ev(under_prob, dec_under)
    kelly_over = _kelly_prop(over_prob, dec_over, bankroll)
    kelly_under = _kelly_prop(under_prob, dec_under, bankroll)

    best_direction = "over" if ev_over["edge"] > ev_under["edge"] else "under"
    best_ev = ev_over if best_direction == "over" else ev_under
    best_kelly = kelly_over if best_direction == "over" else kelly_under
    best_prob = over_prob if best_direction == "over" else under_prob
    best_am_odds = american_odds_over if best_direction == "over" else american_odds_under

    return {
        "player": player_name,
        "sport": "MLB",
        "prop_type": prop_type,
        "line": line,
        "direction": best_direction,
        "american_odds": best_am_odds,
        "projection": proj,
        "our_prob": round(best_prob * 100, 1),
        "implied_prob": round((1 / _american_to_dec(best_am_odds)) * 100, 1),
        "edge_pct": round(best_ev["edge"] * 100, 2),
        "ev_pct": best_ev["ev_pct"],
        "kelly_fraction": best_kelly["fraction"],
        "recommended_stake": best_kelly["bet_amount"],
        "confidence": best_ev["confidence"],
        "factors": {
            "opp_fip": opp_starter_fip,
            "park_factor": park_factor,
            "wind_out": wind_out,
            "wind_mph": wind_mph,
        },
        "both_sides": {
            "over": {"prob": round(over_prob * 100, 1), "edge_pct": round(ev_over["edge"] * 100, 2), "confidence": ev_over["confidence"]},
            "under": {"prob": round(under_prob * 100, 1), "edge_pct": round(ev_under["edge"] * 100, 2), "confidence": ev_under["confidence"]},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── NHL PLAYER PROPS ───────────────────────────────────════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_nhl_prop(
    player_name: str,
    prop_type: str,   # "shots", "goals", "assists", "points", "saves"
    line: float,
    american_odds_over: int,
    american_odds_under: int,
    season_avg: float,
    # Matchup
    opp_shots_allowed_pg: float = 30.0,
    opp_save_pct: float = 0.910,
    # Role
    toi_avg: float = 18.0,              # time on ice in minutes
    pp_time: float = 2.0,               # power play minutes per game
    line_mates_quality: float = 1.0,    # multiplier for linemate quality (1.0=avg)
    # Situational
    back_to_back: bool = False,
    last_5_avg: Optional[float] = None,
    bankroll: float = 10_000,
) -> dict:
    """NHL player prop analysis."""
    # Base TOI factor
    toi_factor = toi_avg / 18.0  # normalize to average TOI

    if prop_type == "shots":
        opp_shots_factor = opp_shots_allowed_pg / 30.0  # more allowed = more for shooter
        proj = season_avg * opp_shots_factor * toi_factor * line_mates_quality

    elif prop_type == "goals":
        shooting_opp = opp_shots_allowed_pg / 30.0
        sv_weakness = (0.910 - opp_save_pct) / 0.020  # better angle when SV% weak
        pp_bonus = (pp_time - 2.0) * 0.03
        proj = season_avg * (1 + sv_weakness * 0.15 + pp_bonus) * shooting_opp * toi_factor

    elif prop_type == "assists":
        proj = season_avg * toi_factor * line_mates_quality
        proj *= (1 + pp_time / 20)  # PP generates more assists

    elif prop_type == "points":
        proj = season_avg * toi_factor * line_mates_quality
        pp_adj = 1 + (pp_time - 2.0) / 10
        proj *= pp_adj

    elif prop_type == "saves":
        # Goalie prop
        proj = season_avg * (opp_shots_allowed_pg / 30.0)

    else:
        proj = season_avg

    if back_to_back:
        proj *= 0.93
    if last_5_avg is not None:
        proj = proj * 0.65 + last_5_avg * 0.35

    proj = round(max(0.0, proj), 2)

    sigma_map = {"shots": 0.35, "goals": 1.10, "assists": 0.90, "points": 0.65, "saves": 0.22}
    sigma = sigma_map.get(prop_type, 0.50)

    if proj <= 0 or line <= 0:
        over_prob = 0.45
    else:
        z = (math.log(max(line, 0.1) / max(proj, 0.1))) / sigma
        over_prob = 1 - _normal_cdf(z)
    over_prob = round(max(0.05, min(0.95, over_prob)), 4)
    under_prob = round(1 - over_prob, 4)

    dec_over = _american_to_dec(american_odds_over)
    dec_under = _american_to_dec(american_odds_under)
    ev_over = _prop_ev(over_prob, dec_over)
    ev_under = _prop_ev(under_prob, dec_under)
    kelly_over = _kelly_prop(over_prob, dec_over, bankroll)
    kelly_under = _kelly_prop(under_prob, dec_under, bankroll)

    best_direction = "over" if ev_over["edge"] > ev_under["edge"] else "under"
    best_ev = ev_over if best_direction == "over" else ev_under
    best_kelly = kelly_over if best_direction == "over" else kelly_under
    best_prob = over_prob if best_direction == "over" else under_prob
    best_am_odds = american_odds_over if best_direction == "over" else american_odds_under

    return {
        "player": player_name,
        "sport": "NHL",
        "prop_type": prop_type,
        "line": line,
        "direction": best_direction,
        "american_odds": best_am_odds,
        "projection": proj,
        "our_prob": round(best_prob * 100, 1),
        "implied_prob": round((1 / _american_to_dec(best_am_odds)) * 100, 1),
        "edge_pct": round(best_ev["edge"] * 100, 2),
        "ev_pct": best_ev["ev_pct"],
        "kelly_fraction": best_kelly["fraction"],
        "recommended_stake": best_kelly["bet_amount"],
        "confidence": best_ev["confidence"],
        "factors": {
            "toi": toi_avg,
            "pp_time": pp_time,
            "opp_sv_pct": opp_save_pct,
            "back_to_back": back_to_back,
        },
        "both_sides": {
            "over": {"prob": round(over_prob * 100, 1), "edge_pct": round(ev_over["edge"] * 100, 2), "confidence": ev_over["confidence"]},
            "under": {"prob": round(under_prob * 100, 1), "edge_pct": round(ev_under["edge"] * 100, 2), "confidence": ev_under["confidence"]},
        },
    }


# ─── Batch Prop Scanner ───────────────────────────────────────────────────────

def scan_props_for_value(prop_list: list[dict], min_edge: float = 0.04) -> list[dict]:
    """
    Given a list of props already analyzed (output of analyze_* functions),
    filter to only those with edge >= min_edge and sort by edge desc.
    """
    value_props = [p for p in prop_list if p.get("edge_pct", 0) >= min_edge * 100]
    value_props.sort(key=lambda x: x["edge_pct"], reverse=True)
    return value_props


# ─── Math helpers ─────────────────────────────────────────────────────────────

def _normal_cdf(z: float) -> float:
    """Approximation of the standard normal CDF using Horner's method."""
    # Abramowitz and Stegun approximation
    if z < -8.0:
        return 0.0
    if z > 8.0:
        return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if z >= 0 else -1
    z = abs(z)
    t = 1.0 / (1.0 + p * z)
    y = 1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * math.exp(-z * z))
    return 0.5 * (1.0 + sign * y)
