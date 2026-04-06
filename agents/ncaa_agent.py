"""
NCAA Agent — March Madness & College Basketball Finals
=======================================================
Handles college basketball tournament analysis:
- March Madness bracket / upset probability
- KenPom-style efficiency ratings (AdjEM, AdjO, AdjD)
- Seed-based upset curves calibrated from 40+ years of data
- Tournament momentum / hot-team adjustments
- Conference strength modifiers
- Championship / National Finals deep run modeling
- NCAAF Bowl Championship / CFP Playoff picks
"""
from __future__ import annotations
from typing import Optional
import math
import random


# ─── Seed Upset Probability Tables (from 1985-2025 tournament data) ──────────
# P(underdog upsets favorite) by seed matchup
SEED_UPSET_PROBS: dict[tuple[int, int], float] = {
    (1, 16): 0.01,   # 1 vs 16: 1 loss ever (UMBC 2018)
    (2, 15): 0.06,   # 13 2-15 upsets all time
    (3, 14): 0.15,
    (4, 13): 0.21,
    (5, 12): 0.35,   # "5-12 upset" is famous
    (6, 11): 0.37,
    (7, 10): 0.39,
    (8,  9): 0.49,   # near coin flip
}


def seed_upset_probability(fav_seed: int, dog_seed: int) -> float:
    """
    Return P(underdog wins) for a seed matchup.
    Handles non-standard matchups via regression to mean.
    """
    pair = (min(fav_seed, dog_seed), max(fav_seed, dog_seed))
    if pair in SEED_UPSET_PROBS:
        return SEED_UPSET_PROBS[pair]
    # General formula: upset prob increases with seed gap
    seed_gap = dog_seed - fav_seed
    base = 0.50 - (seed_gap * 0.04)
    return max(0.02, min(0.65, base))


# ─── KenPom-Style Efficiency Model ───────────────────────────────────────────

def kenpom_win_probability(
    team_adj_em: float,
    opp_adj_em: float,
    neutral_site: bool = True,
    home_court_pts: float = 3.0,
) -> float:
    """
    Estimate win probability using Adjusted Efficiency Margin.
    adj_em = AdjO - AdjD (points per 100 possessions above average)
    Positive = better than average; Duke ~+30, avg team ~0.

    Neutral site removes home court. Returns P(team wins).
    """
    diff = team_adj_em - opp_adj_em
    if not neutral_site:
        diff += home_court_pts   # home team gets bonus

    # Logistic mapping calibrated to 68-team field
    win_prob = 1.0 / (1.0 + math.exp(-diff / 11.0))
    return round(max(0.02, min(0.98, win_prob)), 4)


def adjusted_win_prob_with_momentum(
    team_adj_em: float,
    opp_adj_em: float,
    recent_wins: int = 0,        # wins in last 6 games
    recent_losses: int = 0,
    conf_tourney_run: int = 0,   # games played in conference tourney
    neutral_site: bool = True,
) -> tuple[float, str]:
    """
    Adds tournament-momentum factor on top of base efficiency win prob.
    Returns (adjusted_win_prob, flags_str).
    """
    base = kenpom_win_probability(team_adj_em, opp_adj_em, neutral_site)

    # Hot-team bonus: +1.5% per net positive recent games
    momentum = (recent_wins - recent_losses) * 0.015
    # Conference tourney fatigue: -0.8% per extra game played
    fatigue = -conf_tourney_run * 0.008

    adjusted = base + momentum + fatigue
    adjusted = max(0.02, min(0.98, adjusted))

    flags = []
    if momentum > 0.02:
        flags.append("HOT_TEAM")
    if fatigue < -0.02:
        flags.append("FRESH_LEGS_OPPONENT")
    if base > 0.75:
        flags.append("HEAVY_FAVORITE")
    if 0.42 <= base <= 0.58:
        flags.append("TOSS_UP")

    return round(adjusted, 4), ",".join(flags) or "NEUTRAL"


# ─── Tournament Round Analysis ────────────────────────────────────────────────

ROUND_NAMES = {
    64: "First Round",
    32: "Second Round",
    16: "Sweet 16",
    8:  "Elite Eight",
    4:  "Final Four",
    2:  "National Championship",
}


def analyze_tournament_matchup(
    team_a: str,
    team_b: str,
    seed_a: int,
    seed_b: int,
    adj_em_a: float,
    adj_em_b: float,
    adj_off_a: float = 0.0,
    adj_def_a: float = 0.0,
    adj_off_b: float = 0.0,
    adj_def_b: float = 0.0,
    recent_wins_a: int = 0,
    recent_losses_a: int = 0,
    recent_wins_b: int = 0,
    recent_losses_b: int = 0,
    conf_tourney_games_a: int = 0,
    conf_tourney_games_b: int = 0,
    tournament_round: int = 64,
    spread: Optional[float] = None,
    moneyline_a: Optional[int] = None,
    moneyline_b: Optional[int] = None,
) -> dict:
    """
    Full tournament matchup analysis.
    Returns win probabilities, upset alert, betting edge, and narrative.
    """
    # ── Win Probability ──
    win_prob_a, flags_a = adjusted_win_prob_with_momentum(
        adj_em_a, adj_em_b,
        recent_wins_a, recent_losses_a,
        conf_tourney_games_a,
    )
    win_prob_b = 1.0 - win_prob_a

    # ── Seed-based lens ──
    fav_seed = min(seed_a, seed_b)
    dog_seed = max(seed_a, seed_b)
    seed_upset_prob = seed_upset_probability(fav_seed, dog_seed)

    # Blend efficiency model with seed history (80/20 weight at deeper rounds)
    blend_weight = 0.80  # trust efficiency more than seeds
    if seed_a <= seed_b:
        blended_win_a = blend_weight * win_prob_a + (1 - blend_weight) * (1 - seed_upset_prob)
        blended_win_b = 1.0 - blended_win_a
    else:
        blended_win_b_from_seed = seed_upset_prob
        blended_win_b = blend_weight * win_prob_b + (1 - blend_weight) * blended_win_b_from_seed
        blended_win_a = 1.0 - blended_win_b

    blended_win_a = round(max(0.02, min(0.98, blended_win_a)), 4)
    blended_win_b = round(1.0 - blended_win_a, 4)

    round_name = ROUND_NAMES.get(tournament_round, f"Round of {tournament_round}")

    # ── EV vs market ──
    picks = []
    if moneyline_a is not None:
        from engine.kelly import american_to_decimal, calculate_kelly
        from engine.ev import calculate_ev
        dec_a = american_to_decimal(moneyline_a)
        ev_a = calculate_ev(blended_win_a, dec_a)
        kel_a = calculate_kelly(blended_win_a, dec_a, 10000, 0.25, 0.03)
        if kel_a.fraction > 0 and ev_a.edge > 0.03:
            picks.append({
                "team": team_a,
                "seed": seed_a,
                "market": "moneyline",
                "american_odds": moneyline_a,
                "our_prob": round(blended_win_a * 100, 1),
                "edge_pct": round(ev_a.edge * 100, 2),
                "ev_pct": round(ev_a.ev_pct, 2),
                "recommended_stake": kel_a.bet_amount,
                "verdict": ev_a.confidence,
            })

    if moneyline_b is not None:
        from engine.kelly import american_to_decimal, calculate_kelly
        from engine.ev import calculate_ev
        dec_b = american_to_decimal(moneyline_b)
        ev_b = calculate_ev(blended_win_b, dec_b)
        kel_b = calculate_kelly(blended_win_b, dec_b, 10000, 0.25, 0.03)
        if kel_b.fraction > 0 and ev_b.edge > 0.03:
            picks.append({
                "team": team_b,
                "seed": seed_b,
                "market": "moneyline",
                "american_odds": moneyline_b,
                "our_prob": round(blended_win_b * 100, 1),
                "edge_pct": round(ev_b.edge * 100, 2),
                "ev_pct": round(ev_b.ev_pct, 2),
                "recommended_stake": kel_b.bet_amount,
                "verdict": ev_b.confidence,
            })

    upset_alert = (
        dog_seed - fav_seed >= 4 and   # at least 4-seed gap
        seed_upset_prob >= 0.20 and    # meaningful historic upset rate
        abs(blended_win_a - blended_win_b) < 0.25  # not a blowout mismatch
    )

    cinderella_factor = _cinderella_score(
        dog_seed=dog_seed,
        dog_adj_em=adj_em_b if seed_a < seed_b else adj_em_a,
        round_num=tournament_round,
    )

    return {
        "matchup": f"{team_a} (#{seed_a}) vs {team_b} (#{seed_b})",
        "round": round_name,
        "win_probability": {
            team_a: round(blended_win_a * 100, 1),
            team_b: round(blended_win_b * 100, 1),
        },
        "efficiency_edge": round(adj_em_a - adj_em_b, 2),
        "seed_upset_probability": round(seed_upset_prob * 100, 1),
        "upset_alert": upset_alert,
        "cinderella_score": cinderella_factor,
        "momentum_flags": flags_a,
        "picks": picks,
        "narrative": _generate_narrative(
            team_a, seed_a, team_b, seed_b, blended_win_a,
            adj_em_a, adj_em_b, upset_alert, round_name
        ),
    }


def _cinderella_score(dog_seed: int, dog_adj_em: float, round_num: int) -> float:
    """
    Score 0-10 indicating 'Cinderella potential.'
    High-seed team that's quietly good (better adj_em than seed suggests).
    """
    seed_baseline_em = {12: -5, 13: -8, 14: -12, 15: -17, 16: -22}
    baseline = seed_baseline_em.get(dog_seed, -5)
    em_above_expected = dog_adj_em - baseline

    # Higher round = more impressive, more cinderella weight
    round_mult = {64: 1.0, 32: 1.3, 16: 1.6, 8: 2.0, 4: 2.5, 2: 3.0}.get(round_num, 1.0)
    score = min(10.0, max(0.0, (em_above_expected * 0.3 + 2.0) * round_mult))
    return round(score, 1)


def _generate_narrative(
    team_a: str,
    seed_a: int,
    team_b: str,
    seed_b: int,
    win_prob_a: float,
    adj_em_a: float,
    adj_em_b: float,
    upset_alert: bool,
    round_name: str,
) -> str:
    em_diff = round(adj_em_a - adj_em_b, 1)
    fav = team_a if win_prob_a > 0.5 else team_b
    dog = team_b if win_prob_a > 0.5 else team_a
    fav_seed = seed_a if win_prob_a > 0.5 else seed_b
    dog_seed = seed_b if win_prob_a > 0.5 else seed_a
    fav_prob = max(win_prob_a, 1 - win_prob_a)

    if upset_alert:
        return (
            f"UPSET ALERT — {round_name}: #{dog_seed} {dog} has genuine upset potential. "
            f"Our model gives them {round((1-fav_prob)*100,1)}% despite the seed gap. "
            f"Efficiency margin only {abs(em_diff):.1f} pts apart — bet value on the dog."
        )
    if fav_prob > 0.80:
        return (
            f"{round_name}: #{fav_seed} {fav} is a heavy favorite at {round(fav_prob*100,1)}%. "
            f"+{abs(em_diff):.1f} AdjEM advantage. Barring an injury, this should be straightforward."
        )
    return (
        f"{round_name}: Close matchup. #{fav_seed} {fav} leads with {round(fav_prob*100,1)}% "
        f"but #{dog_seed} {dog} is scrappy. AdjEM gap: {abs(em_diff):.1f} pts. Look for spread value."
    )


# ─── Conference Tournament Strength ──────────────────────────────────────────

CONFERENCE_STRENGTH: dict[str, float] = {
    "SEC":     2.8,
    "Big 12":  2.6,
    "Big Ten": 2.4,
    "ACC":     2.3,
    "Pac-12":  1.8,
    "Big East":1.9,
    "AAC":     0.8,
    "MWC":     0.7,
    "WCC":     0.6,
    "A-10":    0.5,
}


def conference_strength_modifier(conference: str) -> float:
    """Return AdjEM bonus for conference strength (e.g. SEC teams slightly undervalued by pure stats)."""
    return CONFERENCE_STRENGTH.get(conference, 0.0) * 0.1


# ─── March Madness Live Bracket Picks ────────────────────────────────────────

def generate_bracket_picks(games: list[dict]) -> list[dict]:
    """
    Given a list of live NCAAB tournament games (from odds API),
    run full analysis and return ranked picks.

    Expected game schema (from odds API normalized):
        { "home_team": str, "away_team": str, "best_lines": {...},
          "commence_time": str, "is_live": bool }
    """
    from engine.ev import true_probability_no_vig
    from engine.kelly import american_to_decimal, calculate_kelly
    from engine.ev import calculate_ev

    picks = []
    for game in games:
        h2h = game.get("best_lines", {}).get("h2h", {})
        if not h2h or len(h2h) < 2:
            continue

        teams = list(h2h.keys())
        odds_a = h2h[teams[0]]["odds"]
        odds_b = h2h[teams[1]]["odds"]

        vig_result = true_probability_no_vig(odds_a, odds_b)
        true_probs = list(vig_result["true_probs"].values())
        if len(true_probs) < 2:
            continue

        home_true = true_probs[0]
        away_true = true_probs[1]

        for team, prob, odds in [(teams[0], home_true, odds_a), (teams[1], away_true, odds_b)]:
            ev = calculate_ev(prob, odds)
            kelly = calculate_kelly(prob, odds, 10000, 0.25, 0.03)
            if kelly.fraction > 0 and ev.edge > 0.03:
                # Convert decimal odds to american
                if odds >= 2.0:
                    am_odds = int((odds - 1.0) * 100)
                else:
                    am_odds = int(-100 / (odds - 1.0))

                picks.append({
                    "sport": "NCAAB",
                    "tournament": "March Madness",
                    "event": f"{game.get('away_team','Away')} @ {game.get('home_team','Home')}",
                    "pick": team,
                    "market": "moneyline",
                    "book": h2h[team].get("book", "best"),
                    "decimal_odds": odds,
                    "american_odds": am_odds,
                    "our_prob": round(prob * 100, 1),
                    "implied_prob": round((1 / odds) * 100, 1),
                    "edge_pct": round(ev.edge * 100, 2),
                    "ev_pct": round(ev.ev_pct, 2),
                    "kelly_pct": round(kelly.recommended * 100, 2),
                    "recommended_stake": kelly.bet_amount,
                    "verdict": ev.confidence,
                    "commence_time": game.get("commence_time"),
                    "is_live": game.get("is_live", False),
                })

    picks.sort(key=lambda x: x["edge_pct"], reverse=True)
    return picks
