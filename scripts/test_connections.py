"""
test_connections.py — Verify all system dependencies and API keys
=================================================================
Usage: python scripts/test_connections.py
"""
from __future__ import annotations
import asyncio
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


OK    = "  ✓"
WARN  = "  ⚠"
FAIL  = "  ✗"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
RESET  = "\033[0m"


def c(symbol: str, msg: str) -> str:
    colors = {OK: GREEN, WARN: YELLOW, FAIL: RED}
    return f"{colors.get(symbol, '')}{symbol}  {msg}{RESET}"


def check(label: str, ok: bool, detail: str = "", warn: bool = False) -> bool:
    if ok:
        print(c(OK, f"{label}  {detail}"))
    elif warn:
        print(c(WARN, f"{label}  {detail}"))
    else:
        print(c(FAIL, f"{label}  {detail}"))
    return ok


async def run_checks() -> int:
    """Returns number of failures (0 = all good)."""
    failures = 0

    print()
    print("=" * 54)
    print("  KALISHI EDGE -- Connection & Config Test")
    print("=" * 54)
    print()

    # ── Python version ──────────────────────────────────────────────────────
    print("[ Python ]")
    import platform
    version = platform.python_version()
    major, minor, *_ = [int(x) for x in version.split(".")]
    ok = major >= 3 and minor >= 10
    if not check(f"Python {version}", ok, "(need 3.10+)", warn=not ok):
        failures += 1
    print()

    # ── Required packages ───────────────────────────────────────────────────
    print("[ Packages ]")
    required = [
        "fastapi", "uvicorn", "httpx", "openai",
        "python_dotenv", "sqlalchemy", "pydantic",
    ]
    pkg_aliases = {"python_dotenv": "dotenv"}
    for pkg in required:
        import_name = pkg_aliases.get(pkg, pkg)
        try:
            importlib.import_module(import_name)
            check(pkg, True)
        except ImportError:
            check(pkg, False, "(run: pip install -r requirements.txt)")
            failures += 1
    print()

    # ── Database ─────────────────────────────────────────────────────────────
    print("[ Database ]")
    db_path = Path("./db/kalishi_edge.db")
    if not check("SQLite file exists", db_path.exists(),
                 f"({db_path})" if db_path.exists() else "(run: python db/setup.py)"):
        failures += 1
    bankroll_path = Path("./db/bankroll.json")
    check("Bankroll JSON exists", bankroll_path.exists(),
          f"({bankroll_path})" if bankroll_path.exists() else "(will be created on first run)",
          warn=not bankroll_path.exists())
    print()

    # ── Environment variables ────────────────────────────────────────────────
    print("[ Environment / API Keys ]")
    odds_key    = os.getenv("ODDS_API_KEY", "")
    kalshi_key  = os.getenv("KALSHI_API_KEY", "")
    kalshi_pem  = os.getenv("KALSHI_PRIVATE_KEY_PATH", "")
    openai_key  = os.getenv("OPENAI_API_KEY", "")
    bankroll    = os.getenv("BANKROLL_TOTAL", "")

    odds_configured = bool(odds_key) and odds_key != "YOUR_ODDS_API_KEY_HERE"
    check("ODDS_API_KEY", odds_configured,
          "(live odds active)" if odds_configured else "(using mock slate -- add key for live data)",
          warn=not odds_configured)
    kalshi_ready = bool(kalshi_key) and bool(kalshi_pem)
    check("KALSHI_API_KEY",         bool(kalshi_key),
          kalshi_key if kalshi_key else "(not set)",
          warn=not kalshi_key)
    check("KALSHI_PRIVATE_KEY_PATH", bool(kalshi_pem),
          f"({kalshi_pem})" if kalshi_pem else "(not set -- RSA signing disabled)",
          warn=not kalshi_pem)
    if kalshi_pem and not os.path.isabs(kalshi_pem):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_pem = os.path.join(root, kalshi_pem)
    else:
        abs_pem = kalshi_pem
    pem_exists = bool(kalshi_pem) and os.path.isfile(abs_pem)
    check("  PEM file exists", pem_exists,
          f"({abs_pem})" if pem_exists else f"not found at {abs_pem}",
          warn=not pem_exists)
    check("OPENAI_API_KEY", bool(openai_key),
          "(AI tips enabled)" if openai_key else "(optional — AI tips disabled)",
          warn=not openai_key)
    check("BANKROLL_TOTAL", bool(bankroll), f"${float(bankroll or 10000):,.2f}")
    print()

    # ── Odds API connectivity ─────────────────────────────────────────────────
    print("[ Odds API ]")
    if odds_configured:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.the-odds-api.com/v4/sports",
                    params={"apiKey": odds_key},
                )
                if resp.status_code == 200:
                    remaining = resp.headers.get("x-requests-remaining", "?")
                    check("API reachable", True, f"(requests remaining: {remaining})")
                elif resp.status_code == 401:
                    check("API reachable", False, "(401 Unauthorized — check ODDS_API_KEY)")
                    failures += 1
                else:
                    check("API reachable", False, f"(HTTP {resp.status_code})")
                    failures += 1
        except Exception as exc:
            check("API reachable", False, f"(network error: {exc})")
            failures += 1
    else:
        check("API reachable", True,
              "(skipped — no key configured; mock slate will be used)", warn=True)
    print()

    # ── Kalshi API connectivity ───────────────────────────────────────────────
    print("[ Kalshi ]")
    if kalshi_ready and pem_exists:
        import httpx, base64, time
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding as asym_pad
            with open(abs_pem, "rb") as f:
                priv = load_pem_private_key(f.read(), password=None)
            ts   = str(int(time.time() * 1000))
            path = "/trade-api/v2/portfolio/balance"
            msg  = f"{ts}GET{path}".encode()
            sig  = priv.sign(msg,
                asym_pad.PSS(mgf=asym_pad.MGF1(hashes.SHA256()),
                             salt_length=asym_pad.PSS.DIGEST_LENGTH),
                hashes.SHA256())
            req_headers = {
                "KALSHI-ACCESS-KEY":       kalshi_key,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.elections.kalshi.com" + path,
                    headers=req_headers,
                )
            if resp.status_code == 200:
                balance = resp.json().get("balance", 0) / 100
                check("RSA auth + balance", True, f"(${balance:,.2f} available)")
            elif resp.status_code == 401:
                check("RSA auth", False, "(401 -- key ID or signature mismatch)")
                failures += 1
            else:
                check("API reachable", False, f"(HTTP {resp.status_code})")
                failures += 1
        except Exception as exc:
            check("Kalshi RSA auth", False, f"(error: {exc})")
            failures += 1
    else:
        check("Auth", True, "(skipped -- configure KALSHI_API_KEY + KALSHI_PRIVATE_KEY_PATH)", warn=True)
    print()

    # ── Local API server ──────────────────────────────────────────────────────
    print("[ Local API server (port 8420) ]")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get("http://localhost:8420/health")
            if resp.status_code == 200:
                check("Server running", True, "(http://localhost:8420)")
            else:
                check("Server running", False,
                      f"(HTTP {resp.status_code} — run: .\\start.ps1)",
                      warn=True)
    except Exception:
        check("Server running", False,
              "(not running — start with: .\\start.ps1)", warn=True)
    print()

    # ── Orchestrator smoke test ───────────────────────────────────────────────
    print("[ Pick engine smoke test ]")
    try:
        from agents.orchestrator import run_daily_picks
        result = await run_daily_picks()
        n_picks = result.get("total_picks", 0)
        sports  = ", ".join(result.get("sports_covered", [])).upper() or "MOCK"
        check("Pick generation", n_picks > 0,
              f"({n_picks} picks across {sports})",
              warn=n_picks == 0)
        if n_picks == 0:
            print(c(WARN, "  0 picks — check MODEL_ALPHA in .env (should be ≥ 0.03)"))
    except Exception as exc:
        check("Pick generation", False, f"({exc})")
        failures += 1
    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("=" * 54)
    if failures == 0:
        print(c(OK, "All checks passed -- system ready to run"))
    else:
        print(c(FAIL, f"{failures} check(s) failed -- see details above"))
    print("=" * 54)
    print()
    return failures


if __name__ == "__main__":
    fails = asyncio.run(run_checks())
    sys.exit(min(fails, 1))
