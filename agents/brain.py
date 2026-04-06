"""
KALISHI EDGE — AI Brain
========================
GPT-4o powered master intelligence layer.
Every response is augmented with RAG context from the knowledge base,
historical bets, and live market intelligence.

Capabilities:
  - Conversational sports betting analysis (chat)
  - Pick generation with full reasoning chains
  - Matchup breakdown with sabermetric/advanced stats
  - Real-time market context injection
  - Streaming responses for live dashboard
"""
from __future__ import annotations
import os
import json
import asyncio
from datetime import datetime
from typing import AsyncIterator, Optional
from dotenv import load_dotenv

load_dotenv()

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

try:
    from openai import AsyncOpenAI
    OAI_AVAILABLE = bool(OPENAI_KEY)
except ImportError:
    OAI_AVAILABLE = False

from rag.retriever import KalishiRetriever

# ── System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are KALISHI — a hyper-intelligent sports betting AI engineered to find and exploit market inefficiencies.

Your core capabilities:
• Kelly Criterion sizing → never overbetting, always mathematically optimal
• Expected Value (EV) analysis → only positive EV bets, minimum 3% edge
• Closing Line Value (CLV) tracking → the gold standard for long-term edge
• Monte Carlo simulation → 50,000+ simulations per game
• Sharp money detection → steam moves, reverse line movement (RLM), limit reductions
• Arbitrage & middles → guaranteed profit when books disagree
• Advanced sabermetrics: FIP, wRC+, DVOA, EPA, pace, net rating

Behavioral rules:
• Always show the math — edge %, EV, Kelly fraction, recommended stake
• Be direct, be fast, be sharp
• Flag steam moves and RLM as top priority intelligence
• Never recommend a bet without positive EV and minimum 3% edge
• Warn about injury/weather impacts on your analysis

When analyzing picks, structure your output:
1. THE PLAY: [Pick] [Market] [Odds] @ [Book]
2. THE MATH: Edge X%, EV +X%, Kelly X% → $X stake
3. THE EDGE: Why this bet has value over the market
4. THE RISK: What kills this bet (injuries, weather, line steam against)
5. CONVICTION: LOW / MEDIUM / HIGH / STRONG BUY

You have access to real-time context injected below each query. Use it."""


class AIBrain:
    """
    Master LLM intelligence layer for KALISHI EDGE.
    Wraps OpenAI GPT-4o with full RAG context augmentation.
    """

    def __init__(self):
        self._retriever = KalishiRetriever()
        self._client = AsyncOpenAI(api_key=OPENAI_KEY) if OAI_AVAILABLE else None
        self._model = "gpt-4o"
        self._history: list[dict] = []  # conversation memory (last 20 turns)

    @property
    def available(self) -> bool:
        return OAI_AVAILABLE and bool(OPENAI_KEY)

    def _build_messages(self, user_message: str, context: str) -> list[dict]:
        """Assemble message array with system prompt + RAG context + history."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # recent conversation history (last 10 turns)
        messages.extend(self._history[-20:])

        # inject RAG context into user turn
        full_user = user_message
        if context:
            full_user = f"{context}\n\n---\nUSER QUERY: {user_message}"

        messages.append({"role": "user", "content": full_user})
        return messages

    # ── Chat ───────────────────────────────────────────────────────────────

    async def chat(self, user_message: str, remember: bool = True) -> str:
        """
        Single-turn chat with RAG augmentation.
        Returns the complete response text.
        """
        if not self.available:
            return self._fallback_response(user_message)

        context = self._retriever.retrieve_for_chat(user_message)
        messages = self._build_messages(user_message, context)

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,   # low temp = consistent, sharp analysis
                max_tokens=1500,
            )
            content = resp.choices[0].message.content or ""
        except Exception as e:
            return f"[KALISHI Brain offline: {e}]"

        if remember:
            self._history.append({"role": "user", "content": user_message})
            self._history.append({"role": "assistant", "content": content})
            self._history = self._history[-40:]  # cap at 20 pairs

        return content

    async def stream_chat(
        self, user_message: str, remember: bool = True
    ) -> AsyncIterator[str]:
        """
        Streaming chat — yields token chunks as they arrive.
        For WebSocket real-time display.
        """
        if not self.available:
            yield self._fallback_response(user_message)
            return

        context = self._retriever.retrieve_for_chat(user_message)
        messages = self._build_messages(user_message, context)
        full_response = []

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,
                max_tokens=1500,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response.append(delta)
                    yield delta
        except Exception as e:
            yield f"\n[KALISHI Brain error: {e}]"
            return

        if remember:
            self._history.append({"role": "user",      "content": user_message})
            self._history.append({"role": "assistant", "content": "".join(full_response)})
            self._history = self._history[-40:]

    # ── Structured Analysis ────────────────────────────────────────────────

    async def analyze_pick(
        self,
        sport: str,
        event: str,
        market: str,
        edge_pct: float,
        ev_pct: float,
        our_prob: float,
        implied_prob: float,
        american_odds: int,
        stake: float,
        additional_context: Optional[dict] = None,
    ) -> dict:
        """
        Generate structured AI analysis for a specific pick.
        Returns JSON with reasoning, conviction, risk factors.
        """
        context = self._retriever.retrieve_for_pick(sport, event, market)
        similar = self._retriever.retrieve_similar_bets(sport, market, edge_pct)

        user_msg = f"""Analyze this betting opportunity:

SPORT: {sport}
EVENT: {event}
MARKET: {market}
ODDS: {american_odds:+d}
OUR PROBABILITY: {our_prob*100:.1f}%
IMPLIED PROBABILITY: {implied_prob*100:.1f}%
EDGE: {edge_pct:.2f}%
EXPECTED VALUE: +{ev_pct:.2f}%
RECOMMENDED STAKE: ${stake:.2f}

{json.dumps(additional_context, indent=2) if additional_context else ''}

{similar}

Provide a structured pick analysis as JSON with keys:
  conviction (STRONG_BUY|BUY|HOLD|PASS),
  one_line_thesis (max 20 words),
  reasoning (3-4 sentences),
  key_edge (the specific market inefficiency),
  risk_factors (list of 2-3 risks),
  sharp_signal (any steam/RLM indicators or null),
  recommended_action (PLACE_NOW|WAIT_FOR_LINE|MONITOR|SKIP)
"""
        if not self.available:
            return self._fallback_pick_analysis(edge_pct, ev_pct)

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "assistant", "content": context or ""},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as e:
            return {"error": str(e), **self._fallback_pick_analysis(edge_pct, ev_pct)}

    async def generate_daily_briefing(self, picks: list[dict], market_summary: dict) -> str:
        """Generate a full daily betting briefing with all picks ranked."""
        if not self.available:
            return "AI Brain unavailable — connect OpenAI API key for daily briefing."

        context = self._retriever.retrieve(
            "daily picks strategy bankroll discipline sharp money",
            collections=["knowledge", "market_moves"],
            n_per_collection=3,
        )

        picks_text = json.dumps(picks[:10], indent=2)

        prompt = f"""Generate the KALISHI EDGE daily betting briefing.

TODAY'S PICKS (top candidates):
{picks_text}

MARKET SUMMARY:
{json.dumps(market_summary, indent=2)}

{context}

Write a sharp, concise daily briefing covering:
1. EXECUTIVE SUMMARY (2 sentences — what's the play today)
2. TOP 3 PLAYS ranked by conviction (each with 1-sentence thesis + bet sizing)
3. MARKET INTELLIGENCE (sharp moves, steam, notable line movement)
4. BANKROLL NOTE (any sizing adjustments based on recent performance)
5. AVOID LIST (overvalued favorites, public square plays to fade)

Style: Sharp, direct, no fluff. This is an institutional intelligence briefing."""

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1200,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[Briefing generation failed: {e}]"

    def clear_history(self):
        self._history.clear()

    # ── Fallbacks ──────────────────────────────────────────────────────────

    def _fallback_response(self, query: str) -> str:
        return (
            f"[KALISHI Operating in offline mode — OpenAI API key not configured]\n\n"
            f"Your query was: '{query}'\n\n"
            f"Connect your OPENAI_API_KEY in .env to activate full AI analysis. "
            f"All quantitative tools (Kelly, EV, Monte Carlo) remain fully functional."
        )

    def _fallback_pick_analysis(self, edge_pct: float, ev_pct: float) -> dict:
        conviction = "STRONG_BUY" if edge_pct > 8 else "BUY" if edge_pct > 5 else "HOLD"
        return {
            "conviction": conviction,
            "one_line_thesis": f"Quantitative edge {edge_pct:.1f}% above market",
            "reasoning": "AI Brain offline. Kelly/EV analysis confirms positive expected value.",
            "key_edge": f"+{ev_pct:.2f}% EV over implied probability",
            "risk_factors": ["Connect OpenAI API for full risk analysis"],
            "sharp_signal": None,
            "recommended_action": "PLACE_NOW" if edge_pct > 5 else "MONITOR",
        }


# Singleton
_brain: Optional[AIBrain] = None


def get_brain() -> AIBrain:
    global _brain
    if _brain is None:
        _brain = AIBrain()
    return _brain
