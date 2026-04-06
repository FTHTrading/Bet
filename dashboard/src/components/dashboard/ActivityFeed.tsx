'use client';
import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Flame, Bell, Zap, Target, GitMerge, Filter } from 'lucide-react';
import { Badge } from '@/components/ui';
import clsx from 'clsx';

// ─── Types ────────────────────────────────────────────────────────────────────

type EventType = 'pick' | 'arb' | 'steam' | 'system' | 'alert';

interface FeedEvent {
  id: string;
  type: EventType;
  title: string;
  detail: string;
  at: Date;
}

const ICONS: Record<EventType, React.ElementType> = {
  pick:   Target,
  arb:    GitMerge,
  steam:  Flame,
  system: Activity,
  alert:  Bell,
};

const COLORS: Record<EventType, string> = {
  pick:   'text-edge-green  bg-edge-green/10  border-edge-green/20',
  arb:    'text-edge-green  bg-edge-green/10  border-edge-green/20',
  steam:  'text-orange-400  bg-orange-500/10  border-orange-500/20',
  system: 'text-edge-blue   bg-edge-blue/10   border-edge-blue/20',
  alert:  'text-edge-gold   bg-edge-gold/10   border-edge-gold/20',
};

const SEED_EVENTS: FeedEvent[] = [
  { id: 'e1', type: 'pick',   title: 'New Pick: Chiefs -6.5',           detail: 'Confidence 82% · +8.4% edge',        at: new Date(Date.now() - 5 * 60_000) },
  { id: 'e2', type: 'steam',  title: 'Steam: Eagles ML line',           detail: '+4pts shift · 68% sharp money',      at: new Date(Date.now() - 12 * 60_000) },
  { id: 'e3', type: 'arb',    title: 'Arb Found: +1.83%',               detail: '49ers vs Seahawks · DK vs FD',       at: new Date(Date.now() - 21 * 60_000) },
  { id: 'e4', type: 'system', title: 'Daily picks refresh complete',    detail: '4 picks generated for today',        at: new Date(Date.now() - 35 * 60_000) },
  { id: 'e5', type: 'alert',  title: 'API Rate limit warning',          detail: 'Odds API near hourly limit (88%)',   at: new Date(Date.now() - 58 * 60_000) },
  { id: 'e6', type: 'pick',   title: 'Pick closed: Celtics -3',         detail: '✓ Won · +$100 · ROI +8.3%',          at: new Date(Date.now() - 90 * 60_000) },
];

function fmtAge(at: Date) {
  const s = Math.floor((Date.now() - at.getTime()) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

interface Props {
  maxHeight?: number;
}

export default function ActivityFeed({ maxHeight = 420 }: Props) {
  const [events, setEvents] = useState<FeedEvent[]>(SEED_EVENTS);
  const [filter, setFilter] = useState<EventType | 'all'>('all');
  const [paused, setPaused] = useState(false);
  const API = process.env.NEXT_PUBLIC_MCP_API_URL || 'http://localhost:8420';
  const feedRef = useRef<HTMLDivElement>(null);

  // Simulate incoming events
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => {
      const types: EventType[] = ['pick', 'arb', 'steam', 'system', 'alert'];
      const mock: Record<EventType, { title: string; detail: string }[]> = {
        pick:   [{ title: 'New Value Pick Generated', detail: 'Running AI analysis...' }],
        arb:    [{ title: 'Arb scanner cycle complete', detail: 'Checked 12 books · 0 found' }],
        steam:  [{ title: 'Line movement detected', detail: 'NFL total moved 0.5pts' }],
        system: [{ title: 'Health check passed', detail: 'All 8 endpoints responding' }],
        alert:  [{ title: 'Low confidence pick filtered', detail: 'Below 55% threshold' }],
      };
      const type = types[Math.floor(Math.random() * types.length)];
      const pool = mock[type];
      const item = pool[Math.floor(Math.random() * pool.length)];
      const ev: FeedEvent = { id: `live-${Date.now()}`, type, ...item, at: new Date() };
      setEvents(prev => [ev, ...prev].slice(0, 50));
    }, 18_000);
    return () => clearInterval(t);
  }, [paused]);

  const filtered = filter === 'all' ? events : events.filter(e => e.type === filter);

  return (
    <div className="glass-panel p-0 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 grid place-items-center rounded-md bg-edge-blue/15 border border-edge-blue/20">
            <Activity className="w-3.5 h-3.5 text-edge-blue" />
          </div>
          <span className="text-xs font-semibold text-ink-300 uppercase tracking-widest">Live Feed</span>
          <span className="w-1.5 h-1.5 rounded-full bg-edge-green animate-pulse" />
        </div>
        <button
          onClick={() => setPaused(p => !p)}
          className={clsx(
            'text-[9px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border transition-colors',
            paused
              ? 'bg-edge-gold/10 border-edge-gold/25 text-edge-gold'
              : 'bg-ink-800 border-ink-700 text-ink-500 hover:text-ink-300',
          )}
        >
          {paused ? 'PAUSED' : 'LIVE'}
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-ink-800 overflow-x-auto">
        {(['all', 'pick', 'arb', 'steam', 'system', 'alert'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              'px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider whitespace-nowrap transition-all',
              filter === f
                ? 'bg-edge-green/15 text-edge-green border border-edge-green/25'
                : 'text-ink-600 hover:text-ink-400',
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Feed */}
      <div
        ref={feedRef}
        className="flex-1 overflow-y-auto"
        style={{ maxHeight }}
      >
        <AnimatePresence initial={false}>
          {filtered.map((ev, i) => {
            const Icon = ICONS[ev.type];
            return (
              <motion.div
                key={ev.id}
                initial={{ opacity: 0, height: 0, y: -8 }}
                animate={{ opacity: 1, height: 'auto', y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.25 }}
                className="border-b border-ink-800/50 last:border-0"
              >
                <div className="flex items-start gap-3 px-4 py-3 hover:bg-ink-850/50 transition-colors group">
                  <div className={clsx(
                    'w-6 h-6 grid place-items-center rounded-md border shrink-0 mt-0.5',
                    COLORS[ev.type],
                  )}>
                    <Icon className="w-3 h-3" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-ink-200 leading-tight">{ev.title}</p>
                    <p className="text-[10px] text-ink-500 mt-0.5 leading-relaxed">{ev.detail}</p>
                  </div>
                  <span className="text-[9px] font-mono text-ink-600 shrink-0 mt-0.5">{fmtAge(ev.at)}</span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {filtered.length === 0 && (
          <div className="py-8 text-center text-xs text-ink-600">
            No events matching filter
          </div>
        )}
      </div>
    </div>
  );
}
