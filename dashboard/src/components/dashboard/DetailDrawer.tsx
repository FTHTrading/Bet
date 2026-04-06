'use client';
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Target, GitMerge, BookOpen, BarChart2,
  TrendingUp, TrendingDown, ExternalLink, Zap,
  DollarSign, Clock, Award,
} from 'lucide-react';
import { Badge, StatusPill, OddsChip, SportPill, VerdictBadge } from '@/components/ui';
import clsx from 'clsx';

// ─── Payload types (inline to avoid import dependency) ────────────────────────

export type DrawerPayload =
  | { type: 'pick';    data: PickPayload }
  | { type: 'arb';     data: ArbPayload }
  | { type: 'bet';     data: BetPayload }
  | { type: 'metric';  data: MetricPayload }
  | { type: 'workflow'; data: WorkflowPayload };

interface PickPayload {
  id: string; sport: string; event: string; pick: string;
  odds: number; verdict: string; confidence: number;
  kelly_fraction: number; edge_pct: number;
  line?: number; book?: string; analysis?: string;
}

interface ArbPayload {
  id: string; event: string; sport: string;
  book_a: string; book_b: string; side_a: string; side_b: string;
  odds_a: number; odds_b: number; profit_pct: number; stake_100: number;
}

interface BetPayload {
  id: string; event: string; side: string;
  odds: number; stake: number; pnl?: number;
  status: string; created_at?: string; book?: string;
}

interface MetricPayload {
  id: string; label: string; value: string; trend?: number;
}

interface WorkflowPayload {
  id: string; label: string; status: string; last_run?: string;
}

// ─── Drawer Panel ─────────────────────────────────────────────────────────────

interface Props {
  payload: DrawerPayload | null;
  onClose: () => void;
}

function PickDetail({ p }: { p: PickPayload }) {
  const API = process.env.NEXT_PUBLIC_MCP_API_URL || 'http://localhost:8420';
  const [placing, setPlacing] = React.useState(false);
  const [placed,  setPlaced]  = React.useState(false);

  const place = async () => {
    setPlacing(true);
    try {
      await fetch(`${API}/bets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pick_id: p.id, odds: p.odds }),
        signal: AbortSignal.timeout(8000),
      });
      setPlaced(true);
    } catch {}
    finally { setPlacing(false); }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 grid place-items-center rounded-xl bg-edge-green/10 border border-edge-green/20 shrink-0">
          <Target className="w-5 h-5 text-edge-green" />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <SportPill sport={p.sport} />
            <VerdictBadge verdict={p.verdict} />
          </div>
          <h3 className="text-base font-bold text-ink-100 mt-1">{p.pick}</h3>
          <p className="text-xs text-ink-400 mt-0.5">{p.event}</p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3">
        {[
          { l: 'American Odds', v: p.odds > 0 ? `+${p.odds}` : `${p.odds}`, c: p.odds > 0 ? 'text-edge-green' : 'text-ink-200' },
          { l: 'Edge',          v: `+${p.edge_pct.toFixed(1)}%`,             c: p.edge_pct >= 5 ? 'text-edge-green' : 'text-edge-gold' },
          { l: 'Confidence',    v: `${p.confidence.toFixed(0)}%`,            c: 'text-edge-blue' },
          { l: 'Half Kelly',    v: `${(p.kelly_fraction * 50).toFixed(2)}%`, c: 'text-ink-200' },
        ].map(({ l, v, c }) => (
          <div key={l} className="p-3 rounded-xl bg-ink-850 border border-ink-800">
            <div className="text-[9px] text-ink-500 uppercase tracking-widest">{l}</div>
            <div className={clsx('font-mono font-bold text-lg mt-0.5', c)}>{v}</div>
          </div>
        ))}
      </div>

      {/* Analysis */}
      {p.analysis && (
        <div className="p-4 rounded-xl bg-ink-850 border border-ink-800">
          <div className="text-[9px] font-semibold text-ink-500 uppercase tracking-widest mb-2">Analysis</div>
          <p className="text-sm text-ink-300 leading-relaxed">{p.analysis}</p>
        </div>
      )}

      {/* Book */}
      {p.book && (
        <div className="flex items-center justify-between py-2.5 border-t border-ink-800">
          <span className="text-xs text-ink-500">Best book</span>
          <span className="text-sm font-semibold text-ink-200">{p.book}</span>
        </div>
      )}

      {/* Action */}
      {!placed ? (
        <button
          onClick={place}
          disabled={placing}
          className="w-full py-3 rounded-xl font-semibold text-sm bg-edge-green/15 border border-edge-green/30
            text-edge-green hover:bg-edge-green/25 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
        >
          <Zap className="w-4 h-4" />
          {placing ? 'Placing…' : 'Log this Pick'}
        </button>
      ) : (
        <div className="w-full py-3 rounded-xl text-center text-sm font-semibold bg-edge-green/10 border border-edge-green/25 text-edge-green">
          ✓ Pick Logged
        </div>
      )}
    </div>
  );
}

function ArbDetail({ a }: { a: ArbPayload }) {
  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 grid place-items-center rounded-xl bg-edge-green/10 border border-edge-green/20 shrink-0">
          <GitMerge className="w-5 h-5 text-edge-green" />
        </div>
        <div>
          <Badge v="green" className="font-mono text-sm mb-1">+{a.profit_pct.toFixed(2)}% Arb</Badge>
          <h3 className="text-base font-bold text-ink-100">{a.event}</h3>
        </div>
      </div>

      <div className="space-y-2">
        {[
          { book: a.book_a, side: a.side_a, odds: a.odds_a },
          { book: a.book_b, side: a.side_b, odds: a.odds_b },
        ].map(({ book, side, odds }, i) => (
          <div key={i} className="flex items-center justify-between p-4 rounded-xl bg-ink-850 border border-ink-800">
            <div>
              <div className="text-xs font-bold text-ink-300">{book}</div>
              <div className="text-sm text-ink-400 mt-0.5">{side}</div>
            </div>
            <OddsChip odds={odds} />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-xl bg-edge-green/8 border border-edge-green/15 text-center">
          <div className="text-[9px] text-ink-500 uppercase tracking-wider">Profit %</div>
          <div className="font-mono font-bold text-xl text-edge-green mt-1">+{a.profit_pct.toFixed(2)}%</div>
        </div>
        <div className="p-3 rounded-xl bg-ink-850 border border-ink-800 text-center">
          <div className="text-[9px] text-ink-500 uppercase tracking-wider">Stake / $100</div>
          <div className="font-mono font-bold text-xl text-ink-200 mt-1">${a.stake_100.toFixed(0)}</div>
        </div>
      </div>
    </div>
  );
}

function BetDetail({ b }: { b: BetPayload }) {
  const isWin  = b.status === 'won';
  const isLoss = b.status === 'lost';

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 grid place-items-center rounded-xl bg-ink-850 border border-ink-800 shrink-0">
          <BookOpen className="w-5 h-5 text-ink-400" />
        </div>
        <div>
          <div className={clsx('px-2 py-0.5 rounded inline-flex text-[10px] font-bold uppercase tracking-wider border mb-1',
            isWin  ? 'bg-edge-green/15 text-edge-green border-edge-green/25' :
            isLoss ? 'bg-edge-red/15   text-edge-red   border-edge-red/25'   :
            b.status === 'push' ? 'bg-ink-700 text-ink-400 border-ink-600' :
            'bg-edge-gold/15 text-edge-gold border-edge-gold/25',
          )}>
            {b.status}
          </div>
          <h3 className="text-base font-bold text-ink-100">{b.side}</h3>
          <p className="text-xs text-ink-400">{b.event}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { l: 'Odds',  v: b.odds > 0 ? `+${b.odds}` : `${b.odds}`,  c: 'text-ink-200' },
          { l: 'Stake', v: `$${b.stake}`, c: 'text-ink-200' },
          { l: 'P&L',   v: b.pnl !== undefined ? `${b.pnl >= 0 ? '+' : ''}$${b.pnl}` : '—',
                         c: b.pnl !== undefined ? (b.pnl >= 0 ? 'text-edge-green' : 'text-edge-red') : 'text-ink-500' },
        ].map(({ l, v, c }) => (
          <div key={l} className="p-3 rounded-xl bg-ink-850 border border-ink-800 text-center">
            <div className="text-[9px] text-ink-500 uppercase tracking-wider">{l}</div>
            <div className={clsx('font-mono font-bold text-base mt-1', c)}>{v}</div>
          </div>
        ))}
      </div>

      {b.book && (
        <div className="flex items-center justify-between py-2.5 border-t border-ink-800">
          <span className="text-xs text-ink-500">Book</span>
          <span className="text-sm font-semibold text-ink-200">{b.book}</span>
        </div>
      )}
      {b.created_at && (
        <div className="flex items-center justify-between py-2.5 border-t border-ink-800">
          <span className="text-xs text-ink-500">Date</span>
          <span className="text-sm font-semibold text-ink-200">{b.created_at}</span>
        </div>
      )}
    </div>
  );
}

// ─── Main Drawer ──────────────────────────────────────────────────────────────

export default function DetailDrawer({ payload, onClose }: Props) {
  const TITLE_MAP: Record<string, string> = {
    pick: 'Pick Detail', arb: 'Arbitrage Detail', bet: 'Bet Detail',
    metric: 'Metric Detail', workflow: 'Workflow Detail',
  };

  return (
    <AnimatePresence>
      {payload && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            className="fixed right-0 top-0 bottom-0 w-full max-w-sm z-50
              bg-ink-925 border-l border-ink-800 shadow-2xl flex flex-col overflow-hidden"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-ink-800">
              <h2 className="text-sm font-semibold text-ink-200">
                {TITLE_MAP[payload.type] ?? payload.type}
              </h2>
              <button
                onClick={onClose}
                className="icon-btn"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5">
              {payload.type === 'pick'    && <PickDetail   p={payload.data as PickPayload} />}
              {payload.type === 'arb'     && <ArbDetail    a={payload.data as ArbPayload}  />}
              {payload.type === 'bet'     && <BetDetail    b={payload.data as BetPayload}  />}
              {payload.type === 'metric'  && (
                <div className="space-y-3">
                  <p className="text-lg font-bold text-ink-100">{(payload.data as MetricPayload).value}</p>
                  <p className="text-sm text-ink-400">{(payload.data as MetricPayload).label}</p>
                </div>
              )}
              {payload.type === 'workflow' && (
                <div className="space-y-3">
                  <p className="text-base font-bold text-ink-100">{(payload.data as WorkflowPayload).label}</p>
                  <StatusPill status={(payload.data as WorkflowPayload).status as any} />
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
