// Mock + fallback data — used when API is offline
import type { Bankroll, Pick, SharpMove } from '@/lib/types';

export const MOCK_BANKROLL: Bankroll = {
  current_bankroll: 10000,
  starting_bankroll: 10000,
  total_profit: 0,
  roi_pct: 0,
  win_rate: 0,
  total_bets: 0,
  open_bets: 0,
  max_drawdown: 0,
  clv_avg: 0,
  high_water_mark: 10000,
  daily_pnl: 0,
};

export const MOCK_EQUITY: Array<{ date: string; bankroll: number; roi_pct: number }> = [
  { date: '2025-10-01', bankroll: 10000, roi_pct: 0 },
  { date: '2025-10-15', bankroll: 10240, roi_pct: 2.4 },
  { date: '2025-11-01', bankroll: 10580, roi_pct: 5.8 },
  { date: '2025-11-15', bankroll: 10320, roi_pct: 3.2 },
  { date: '2025-12-01', bankroll: 10890, roi_pct: 8.9 },
  { date: '2025-12-15', bankroll: 11240, roi_pct: 12.4 },
  { date: '2026-01-01', bankroll: 11580, roi_pct: 15.8 },
];

export const MOCK_PICKS: Pick[] = [
  {
    sport: 'NBA', event: 'Lakers @ Celtics', pick: 'Celtics -6.5', market: 'spread',
    american_odds: -115, decimal_odds: 1.87, our_prob: 0.62, implied_prob: 0.535,
    edge_pct: 8.5, ev_pct: 7.2, recommended_stake: 220, kelly_pct: 2.2, verdict: 'Strong Value', book: 'DraftKings',
  },
  {
    sport: 'NFL', event: 'Chiefs @ Raiders', pick: 'Chiefs ML', market: 'moneyline',
    american_odds: -145, decimal_odds: 1.69, our_prob: 0.72, implied_prob: 0.592,
    edge_pct: 12.8, ev_pct: 11.1, recommended_stake: 350, kelly_pct: 3.5, verdict: 'Excellent Edge', book: 'FanDuel',
  },
];

export const MOCK_MOVES: SharpMove[] = [
  {
    event: 'Lakers @ Celtics', market: 'spread', from_odds: -112, to_odds: -118,
    delta: -6, book: 'DraftKings', sharp: true, sport: 'NBA', age_mins: 8,
  },
  {
    event: 'Chiefs @ Raiders', market: 'moneyline', from_odds: -138, to_odds: -145,
    delta: -7, book: 'FanDuel', sharp: true, sport: 'NFL', age_mins: 23,
  },
];

export const WORKFLOW_DEFS = [
  {
    id: 'daily_picks',
    label: 'Daily Picks',
    cmd: 'python workflows/daily_picks.py',
    description: 'Runs all agents and scores every open market for edge',
    color: 'text-edge-green',
    accent: 'rgba(0,232,122,0.15)',
  },
  {
    id: 'arb_scan',
    label: 'Arb Scanner',
    cmd: 'python workflows/arbitrage_scan.py',
    description: 'Cross-book arbitrage detection across all open markets',
    color: 'text-edge-blue',
    accent: 'rgba(59,130,246,0.15)',
  },
  {
    id: 'middle_scan',
    label: 'Middle Scanner',
    cmd: 'python workflows/middle_scan.py',
    description: 'Identifies middle windows in totals and spreads',
    color: 'text-edge-gold',
    accent: 'rgba(245,158,11,0.12)',
  },
  {
    id: 'live_monitor',
    label: 'Live Monitor',
    cmd: 'python workflows/live_monitor.py',
    description: 'Watches for live line movement and steam signals',
    color: 'text-edge-cyan',
    accent: 'rgba(6,182,212,0.12)',
  },
  {
    id: 'mcp_server',
    label: 'MCP API Server',
    cmd: 'python mcp/server.py',
    description: 'FastAPI engine serving all data and intelligence endpoints',
    color: 'text-edge-purple',
    accent: 'rgba(168,85,247,0.12)',
  },
] as const;

export const API_ENDPOINTS = [
  { method: 'GET' as const,  path: '/picks/today',           description: 'Today\'s best value plays',     category: 'intelligence' },
  { method: 'GET' as const,  path: '/picks/props',           description: 'Player prop edges',             category: 'intelligence' },
  { method: 'GET' as const,  path: '/picks/college',         description: 'NCAAB edges',                  category: 'intelligence' },
  { method: 'GET' as const,  path: '/lines/best',            description: 'Best available lines',          category: 'markets' },
  { method: 'GET' as const,  path: '/lines/movement',        description: 'Sharp line movement feed',      category: 'markets' },
  { method: 'GET' as const,  path: '/picks/middles',         description: 'Middle opportunities',          category: 'markets' },
  { method: 'GET' as const,  path: '/analytics/performance', description: 'Historical performance stats',   category: 'analytics' },
  { method: 'GET' as const,  path: '/bankroll',              description: 'Bankroll + P&L state',          category: 'analytics' },
  { method: 'GET' as const,  path: '/kalshi/markets',        description: 'Kalshi prediction markets',     category: 'kalshi' },
  { method: 'POST' as const, path: '/kalshi/auto',           description: 'Auto-execute on Kalshi',        category: 'kalshi' },
  { method: 'GET' as const,  path: '/kalshi/balance',        description: 'Kalshi account balance',        category: 'kalshi' },
  { method: 'POST' as const, path: '/ai/chat',               description: 'AI Brain chat endpoint',        category: 'ai' },
  { method: 'GET' as const,  path: '/ai/briefing',           description: 'Daily AI brief',                category: 'ai' },
  { method: 'POST' as const, path: '/kelly',                 description: 'Kelly criterion calculator',    category: 'tools' },
  { method: 'WS'  as const,  path: '/ws/live',               description: 'Live odds/events stream',       category: 'ws' },
  { method: 'WS'  as const,  path: '/ws/ai',                 description: 'AI streaming chat',             category: 'ws' },
];
