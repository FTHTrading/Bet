'use client';
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Target, GitMerge, BarChart, TrendingUp, BookOpen,
  Bot, RefreshCw, Filter, SlidersHorizontal, ChevronRight,
  ExternalLink, Flame, Clock, Star, ArrowUpRight, Zap, DollarSign,
} from 'lucide-react';
import {
  GlassPanel, Badge, SportPill, VerdictBadge, OddsChip,
  Skeleton, SkeletonRows, EmptyState,
} from '@/components/ui';
import clsx from 'clsx';

const API = process.env.NEXT_PUBLIC_MCP_API_URL || 'http://localhost:8420';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Pick {
  id: string; sport: string; event: string; pick: string;
  odds: number; verdict: string; confidence: number;
  kelly_fraction: number; edge_pct: number;
  line?: number; book?: string; matchup?: string;
  analysis?: string;
}

interface Arb {
  id: string; event: string; sport: string;
  book_a: string; book_b: string;
  side_a: string; side_b: string;
  odds_a: number; odds_b: number;
  profit_pct: number; stake_100: number; created_at?: string;
}

interface LineShopItem {
  id: string; event: string; sport: string;
  team: string; best_odds: number; worst_odds: number;
  consensus: number; books: { name: string; odds: number }[];
}

interface SharpMove {
  id: string; event: string; sport: string;
  description: string; severity: string;
  line_move: number; pct_bets: number; pct_money: number;
  created_at?: string;
}

interface Bet {
  id: string; event: string; side: string;
  odds: number; stake: number; pnl?: number;
  status: 'won' | 'lost' | 'push' | 'pending';
  created_at?: string; book?: string;
}

interface PerfStat {
  sport: string; bets: number; wins: number;
  units: number; roi: number;
}

// ─── Tab definition ───────────────────────────────────────────────────────────

type TabId = 'picks' | 'arb' | 'lineshop' | 'steam' | 'performance' | 'betlog' | 'ai';

interface TabDef {
  id: TabId; label: string; icon: React.ElementType;
  description: string; badge?: string;
}

const TABS: TabDef[] = [
  { id: 'picks',       icon: Target,      label: 'Picks',        description: "Today's AI value picks"     },
  { id: 'arb',         icon: GitMerge,    label: 'Arb',          description: 'Arbitrage opportunities'     },
  { id: 'lineshop',    icon: BarChart,    label: 'Line Shop',     description: 'Best odds across books'      },
  { id: 'steam',       icon: Flame,       label: 'Steam',         description: 'Sharp line movement alerts'  },
  { id: 'performance', icon: TrendingUp,  label: 'Performance',   description: 'Historical performance lab'  },
  { id: 'betlog',      icon: BookOpen,    label: 'Bet Log',       description: 'Full wagering history'       },
  { id: 'ai',          icon: Bot,         label: 'AI Chat',       description: 'Intelligence assistant'      },
];

// ─── Mock data ────────────────────────────────────────────────────────────────

const MOCK_PICKS: Pick[] = [
  { id:'p1', sport:'americanfootball_nfl', event:'Chiefs vs Raiders',  pick:'Chiefs -6.5',     odds:-115, verdict:'EXCELLENT EDGE', confidence:82, kelly_fraction:0.09, edge_pct:8.4, book:'DraftKings',  matchup:'KC vs LV' },
  { id:'p2', sport:'basketball_nba',       event:'Lakers vs Celtics',  pick:'Celtics -3',      odds:-108, verdict:'GOOD EDGE',      confidence:71, kelly_fraction:0.06, edge_pct:5.1, book:'FanDuel',     matchup:'LAL vs BOS' },
  { id:'p3', sport:'baseball_mlb',         event:'Yankees vs Sox',     pick:'Over 9.5',        odds:-112, verdict:'GOOD EDGE',      confidence:68, kelly_fraction:0.05, edge_pct:4.6, book:'BetMGM',      matchup:'NYY vs BOS' },
  { id:'p4', sport:'icehockey_nhl',        event:'Bruins vs Penguins', pick:'Bruins ML',       odds:+118, verdict:'MARGINAL',       confidence:55, kelly_fraction:0.02, edge_pct:2.1, book:'Caesars',     matchup:'BOS vs PIT' },
];

const MOCK_ARB: Arb[] = [
  { id:'a1', event:'49ers vs Seahawks', sport:'americanfootball_nfl', book_a:'DraftKings', book_b:'FanDuel', side_a:'49ers ML', side_b:'Seahawks ML +105', odds_a:-118, odds_b:+135, profit_pct:1.83, stake_100:92.56 },
  { id:'a2', event:'Heat vs Bucks',     sport:'basketball_nba',       book_a:'BetMGM',     book_b:'Caesars',  side_a:'Heat +4.5', side_b:'Bucks -3.5', odds_a:-105, odds_b:-108, profit_pct:0.91, stake_100:94.18 },
];

const MOCK_STEAM: SharpMove[] = [
  { id:'s1', event:'Eagles vs Cowboys', sport:'americanfootball_nfl', description:'Eagles ML sharp reverse move', severity:'HIGH',   line_move:4, pct_bets:32, pct_money:68 },
  { id:'s2', event:'Warriors vs Suns',  sport:'basketball_nba',       description:'Suns -3.5 steam tick at open',  severity:'MEDIUM', line_move:2, pct_bets:41, pct_money:62 },
];

const MOCK_PERF: PerfStat[] = [
  { sport:'NFL', bets:42, wins:26, units:3.8, roi:9.1 },
  { sport:'NBA', bets:38, wins:22, units:2.1, roi:5.5 },
  { sport:'MLB', bets:35, wins:20, units:1.6, roi:4.6 },
  { sport:'NHL', bets:17, wins: 8, units:-0.4, roi:-2.4 },
];

const MOCK_BETS: Bet[] = [
  { id:'b1', event:'Chiefs vs Raiders', side:'Chiefs -6.5', odds:-115, stake:220, pnl:191, status:'won',  created_at:'2024-01-15', book:'DraftKings' },
  { id:'b2', event:'Lakers vs Celtics', side:'Lakers +3',   odds:-110, stake:110, pnl:-110, status:'lost', created_at:'2024-01-14', book:'FanDuel' },
  { id:'b3', event:'Over 9.5 NYY-BOS', side:'Over',         odds:-112, stake:112, pnl:0, status:'pending', created_at:'2024-01-16', book:'BetMGM' },
];

// ─── Picks Table ──────────────────────────────────────────────────────────────

function PicksPane({
  search, onSelect,
}: { search: string; onSelect: (p: Pick) => void }) {
  const [picks, setPicks]   = useState<Pick[]>(MOCK_PICKS);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const r = await fetch(`${API}/picks/today`, { signal: AbortSignal.timeout(5000) });
      const d = await r.json();
      if (Array.isArray(d) && d.length > 0) setPicks(d);
    } catch { /* keep mock */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() =>
    picks.filter(p =>
      !search || p.event.toLowerCase().includes(search.toLowerCase())
        || p.pick.toLowerCase().includes(search.toLowerCase())
    ), [picks, search]);

  if (loading) return <SkeletonRows n={4} />;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[10px] text-ink-500 pb-1">
        <span>{filtered.length} picks today</span>
        <button
          className="flex items-center gap-1 hover:text-ink-300 transition-colors"
          onClick={() => load(true)}
        >
          <RefreshCw className={clsx('w-3 h-3', refreshing && 'animate-spin')} />
          Refresh
        </button>
      </div>
      {filtered.length === 0 && <EmptyState msg="No picks match your search." icon={Target} />}
      {filtered.map((pick, i) => (
        <motion.div
          key={pick.id}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.04 }}
        >
          <div
            className="group flex items-start gap-4 p-4 rounded-xl bg-ink-900/50 border border-ink-800
              hover:border-ink-700 hover:bg-ink-850/70 cursor-pointer transition-all duration-150"
            onClick={() => onSelect(pick)}
          >
            <SportPill sport={pick.sport} />
            <div className="flex-1 min-w-0">
              <div className="flex items-start gap-2 flex-wrap">
                <span className="text-sm font-semibold text-ink-100 leading-tight">{pick.pick}</span>
                <VerdictBadge verdict={pick.verdict} />
              </div>
              <div className="text-[11px] text-ink-500 mt-0.5 truncate">{pick.event}</div>
              {pick.book && (
                <div className="text-[10px] text-ink-600 mt-0.5">{pick.book}</div>
              )}
            </div>
            <div className="text-right shrink-0 space-y-1">
              <OddsChip odds={pick.odds} />
              <div className="text-[10px] text-ink-500">{(pick.confidence).toFixed(0)}% conf</div>
              <div className={clsx('text-[10px] font-semibold', pick.edge_pct >= 5 ? 'text-edge-green' : 'text-edge-gold')}>
                +{pick.edge_pct.toFixed(1)}% edge
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-ink-700 group-hover:text-ink-400 transition-colors mt-0.5 shrink-0" />
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ─── Arb Pane ─────────────────────────────────────────────────────────────────

function ArbPane({ search, onSelect }: { search: string; onSelect: (a: Arb) => void }) {
  const [arbs, setArbs]   = useState<Arb[]>(MOCK_ARB);
  const [loading, setLoading] = useState(true);
  const [runningAuto, setRunningAuto] = useState(false);

  useEffect(() => {
    fetch(`${API}/arb/live`, { signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(d => { if (Array.isArray(d) && d.length) setArbs(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() =>
    arbs.filter(a => !search || a.event.toLowerCase().includes(search.toLowerCase())),
    [arbs, search]);

  const runAutoArb = useCallback(async () => {
    setRunningAuto(true);
    try {
      await fetch(`${API}/arb/auto`, { method: 'POST', signal: AbortSignal.timeout(10000) });
    } catch {}
    finally { setRunningAuto(false); }
  }, []);

  if (loading) return <SkeletonRows n={3} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-ink-500">{filtered.length} live opportunities</span>
        <button
          onClick={runAutoArb}
          disabled={runningAuto}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
            bg-edge-green/10 border border-edge-green/25 text-edge-green
            hover:bg-edge-green/15 disabled:opacity-50 transition-all"
        >
          <Zap className="w-3 h-3" />
          {runningAuto ? 'Scanning…' : 'Auto-Scan'}
        </button>
      </div>
      {filtered.length === 0 && <EmptyState msg="No arb opportunities found right now." icon={GitMerge} />}
      {filtered.map(arb => (
        <div
          key={arb.id}
          className="group p-4 rounded-xl bg-edge-green/5 border border-edge-green/15
            hover:border-edge-green/30 cursor-pointer transition-all"
          onClick={() => onSelect(arb)}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <SportPill sport={arb.sport} />
                <Badge v="green" className="font-mono">+{arb.profit_pct.toFixed(2)}%</Badge>
              </div>
              <p className="text-sm font-semibold text-ink-100">{arb.event}</p>
              <div className="mt-2 space-y-1 text-xs text-ink-400">
                <div className="flex items-center gap-2">
                  <span className="w-20 text-ink-500">{arb.book_a}</span>
                  <span className="font-medium text-ink-200">{arb.side_a}</span>
                  <OddsChip odds={arb.odds_a} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-20 text-ink-500">{arb.book_b}</span>
                  <span className="font-medium text-ink-200">{arb.side_b}</span>
                  <OddsChip odds={arb.odds_b} />
                </div>
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-lg font-bold text-edge-green font-mono">+{arb.profit_pct.toFixed(2)}%</div>
              <div className="text-[10px] text-ink-500">${arb.stake_100.toFixed(0)} / $100</div>
              <ChevronRight className="w-4 h-4 text-ink-600 group-hover:text-ink-400 ml-auto mt-1 transition-colors" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Steam / Sharp Moves Pane ─────────────────────────────────────────────────

function SteamPane({ search }: { search: string }) {
  const [moves, setMoves] = useState<SharpMove[]>(MOCK_STEAM);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/sharp/moves`, { signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(d => { if (Array.isArray(d) && d.length) setMoves(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() =>
    moves.filter(m => !search || m.event.toLowerCase().includes(search.toLowerCase())),
    [moves, search]);

  if (loading) return <SkeletonRows n={3} />;

  return (
    <div className="space-y-2">
      {filtered.length === 0 && <EmptyState msg="No sharp moves detected recently." icon={Flame} />}
      {filtered.map(move => (
        <div
          key={move.id}
          className="flex items-center gap-4 p-4 rounded-xl bg-orange-500/5 border border-orange-500/15 hover:border-orange-500/25 transition-all"
        >
          <div className={clsx(
            'shrink-0 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-widest',
            move.severity === 'HIGH' ? 'bg-edge-red/15 text-edge-red border border-edge-red/25' : 'bg-edge-gold/15 text-edge-gold border border-edge-gold/25',
          )}>
            {move.severity}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-ink-200">{move.description}</p>
            <p className="text-[10px] text-ink-500 mt-0.5">{move.event}</p>
          </div>
          <div className="text-right shrink-0 space-y-0.5">
            <div className="text-xs font-mono font-semibold text-orange-400">{move.line_move > 0 ? '+' : ''}{move.line_move} pts</div>
            <div className="text-[9px] text-ink-500">{move.pct_money}% money</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Performance Pane ─────────────────────────────────────────────────────────

function PerformancePane() {
  const [stats, setStats] = useState<PerfStat[]>(MOCK_PERF);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/performance/breakdown`, { signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(d => { if (Array.isArray(d) && d.length) setStats(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <SkeletonRows n={4} />;

  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-5 gap-2 text-[9px] font-semibold text-ink-500 uppercase tracking-widest px-1 pb-1 border-b border-ink-800">
        <div>Sport</div>
        <div className="text-right">Bets</div>
        <div className="text-right">W/L</div>
        <div className="text-right">Units</div>
        <div className="text-right">ROI</div>
      </div>
      {stats.map(s => (
        <div key={s.sport} className="grid grid-cols-5 gap-2 items-center py-2.5 px-1 rounded-lg hover:bg-ink-850 transition-colors">
          <div className="text-xs font-semibold text-ink-200">{s.sport}</div>
          <div className="text-xs font-mono text-right text-ink-400">{s.bets}</div>
          <div className="text-xs font-mono text-right text-ink-400">{s.wins}-{s.bets - s.wins}</div>
          <div className={clsx('text-xs font-mono text-right font-semibold', s.units >= 0 ? 'text-edge-green' : 'text-edge-red')}>
            {s.units >= 0 ? '+' : ''}{s.units.toFixed(1)}u
          </div>
          <div className={clsx('text-xs font-mono text-right font-semibold', s.roi >= 0 ? 'text-edge-green' : 'text-edge-red')}>
            {s.roi >= 0 ? '+' : ''}{s.roi.toFixed(1)}%
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Bet Log Pane ─────────────────────────────────────────────────────────────

const STATUS_STYLES = {
  won:     'bg-edge-green/15 text-edge-green border-edge-green/25',
  lost:    'bg-edge-red/15   text-edge-red   border-edge-red/25',
  push:    'bg-ink-700       text-ink-400    border-ink-600',
  pending: 'bg-edge-gold/15  text-edge-gold  border-edge-gold/25',
};

function BetLogPane({ search, onSelect }: { search: string; onSelect: (b: Bet) => void }) {
  const [bets, setBets]   = useState<Bet[]>(MOCK_BETS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/bets`, { signal: AbortSignal.timeout(5000) })
      .then(r => r.json())
      .then(d => { if (Array.isArray(d) && d.length) setBets(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() =>
    bets.filter(b => !search || b.event.toLowerCase().includes(search.toLowerCase())),
    [bets, search]);

  if (loading) return <SkeletonRows n={4} />;

  return (
    <div className="space-y-1.5">
      {filtered.length === 0 && <EmptyState msg="No bets found." icon={BookOpen} />}
      {filtered.map(bet => (
        <div
          key={bet.id}
          className="group flex items-center gap-4 py-3 px-4 rounded-xl hover:bg-ink-850 cursor-pointer transition-all border border-transparent hover:border-ink-800"
          onClick={() => onSelect(bet)}
        >
          <span className={clsx('shrink-0 px-2 py-0.5 rounded border text-[9px] font-bold uppercase tracking-widest', STATUS_STYLES[bet.status])}>
            {bet.status}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-ink-200 truncate">{bet.side}</p>
            <p className="text-[10px] text-ink-500 truncate">{bet.event} · {bet.book}</p>
          </div>
          <div className="text-right shrink-0">
            <div className="text-xs font-mono text-ink-300">${bet.stake}</div>
            {bet.pnl !== undefined && bet.status !== 'pending' && (
              <div className={clsx('text-xs font-mono font-bold', bet.pnl >= 0 ? 'text-edge-green' : 'text-edge-red')}>
                {bet.pnl >= 0 ? '+' : ''}${bet.pnl}
              </div>
            )}
          </div>
          <ChevronRight className="w-3.5 h-3.5 text-ink-700 group-hover:text-ink-400 transition-colors shrink-0" />
        </div>
      ))}
    </div>
  );
}

// ─── Line Shop Pane (stub) ────────────────────────────────────────────────────

function LineShopPane({ search }: { search: string }) {
  return (
    <EmptyState msg="Line shop compares odds across DraftKings, FanDuel, BetMGM, Caesars. Connect your API to populate." icon={BarChart} />
  );
}

// ─── AI Chat Pane ─────────────────────────────────────────────────────────────

function AIChatPane() {
  const [msgs, setMsgs]   = useState<Array<{ role: 'user' | 'ai'; content: string }>>([
    { role: 'ai', content: "I'm your betting intelligence assistant. Ask me about any pick, market, or strategy." },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);

  const send = async () => {
    if (!input.trim()) return;
    const q = input.trim();
    setInput('');
    setMsgs(m => [...m, { role: 'user', content: q }]);
    setLoading(true);
    try {
      const r = await fetch(`${API}/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q }),
        signal: AbortSignal.timeout(30000),
      });
      const d = await r.json();
      setMsgs(m => [...m, { role: 'ai', content: d.response || d.message || 'No response received.' }]);
    } catch (e: any) {
      setMsgs(m => [...m, { role: 'ai', content: `Error: ${e?.message ?? 'Connection failed'}` }]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  return (
    <div className="flex flex-col h-full min-h-[400px]">
      <div className="flex-1 overflow-y-auto space-y-3 pr-1 min-h-0 max-h-[500px]">
        {msgs.map((m, i) => (
          <div key={i} className={clsx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={clsx(
              'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
              m.role === 'user'
                ? 'bg-edge-blue/15 border border-edge-blue/25 text-ink-200 rounded-br-sm'
                : 'bg-ink-850 border border-ink-800 text-ink-300 rounded-bl-sm',
            )}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-ink-850 border border-ink-800 rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                {[0,1,2].map(i => (
                  <span key={i} className="w-1.5 h-1.5 bg-edge-blue/50 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div className="mt-3 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Ask about any pick or market…"
          className="input-field flex-1 text-sm"
        />
        <button
          onClick={send}
          disabled={!input.trim() || loading}
          className="px-4 py-2 rounded-xl text-sm font-semibold bg-edge-blue/20 border border-edge-blue/30
            text-edge-blue hover:bg-edge-blue/25 disabled:opacity-40 transition-all"
        >
          Send
        </button>
      </div>
    </div>
  );
}

// ─── IntelligenceTabs (main export) ──────────────────────────────────────────

interface Props {
  onPickSelect?: (p: Pick) => void;
  onArbSelect?:  (a: Arb)  => void;
  onBetSelect?:  (b: Bet)  => void;
}

export default function IntelligenceTabs({ onPickSelect, onArbSelect, onBetSelect }: Props) {
  const [active, setActive] = useState<TabId>('picks');
  const [search, setSearch] = useState('');

  const currentTab = TABS.find(t => t.id === active)!;

  return (
    <GlassPanel padding="none" className="flex flex-col">
      {/* Tab bar */}
      <div className="flex items-center gap-0 border-b border-ink-800 px-2 pt-1 overflow-x-auto">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => { setActive(tab.id); setSearch(''); }}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-all duration-150 whitespace-nowrap',
              'border-b-2 -mb-px',
              active === tab.id
                ? 'border-edge-green text-edge-green'
                : 'border-transparent text-ink-500 hover:text-ink-300',
            )}
          >
            <tab.icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Search / filter bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800">
        <div className="flex items-center gap-2 flex-1 bg-ink-850 border border-ink-800 rounded-lg px-2.5 py-1.5">
          <Search className="w-3 h-3 text-ink-600 shrink-0" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={`Search ${currentTab.label.toLowerCase()}…`}
            className="text-xs text-ink-300 bg-transparent outline-none placeholder:text-ink-600 flex-1 w-full"
          />
        </div>
        <div className="text-[10px] text-ink-600 hidden sm:block">
          {currentTab.description}
        </div>
      </div>

      {/* Pane content */}
      <div className="flex-1 p-4 overflow-y-auto min-h-0 max-h-[520px]">
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
          >
            {active === 'picks'       && <PicksPane       search={search} onSelect={onPickSelect ?? (() => {})} />}
            {active === 'arb'         && <ArbPane         search={search} onSelect={onArbSelect  ?? (() => {})} />}
            {active === 'lineshop'    && <LineShopPane    search={search} />}
            {active === 'steam'       && <SteamPane       search={search} />}
            {active === 'performance' && <PerformancePane />}
            {active === 'betlog'      && <BetLogPane      search={search} onSelect={onBetSelect ?? (() => {})} />}
            {active === 'ai'          && <AIChatPane />}
          </motion.div>
        </AnimatePresence>
      </div>
    </GlassPanel>
  );
}
