'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Settings, ChevronDown, ChevronUp, PlayCircle, RotateCcw,
  Cpu, Wifi, WifiOff, CheckCircle, XCircle, Clock, Loader2,
  Activity, Zap, BarChart2, Search, BookOpen, RefreshCw,
} from 'lucide-react';
import { GlassPanel, StatusPill, Badge } from '@/components/ui';
import clsx from 'clsx';

const API = process.env.NEXT_PUBLIC_MCP_API_URL || 'http://localhost:8420';

// ─── Workflow Definitions ────────────────────────────────────────────────────

type WfStatus = 'idle' | 'running' | 'success' | 'error';

interface WorkflowDef {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  iconColor: string;
  endpoint: string;
  lastRun?: string;
  status: WfStatus;
}

const WORKFLOWS: WorkflowDef[] = [
  { id: 'daily_picks', label: 'Daily Picks', description: 'Generate AI value picks', icon: Target, iconColor: 'text-edge-green  bg-edge-green/10  border-edge-green/20', endpoint: '/picks/generate', status: 'idle', lastRun: '2h ago' },
  { id: 'arb_scan',    label: 'Arb Scan',    description: 'Scan 8+ books for arb',    icon: Search,  iconColor: 'text-edge-blue   bg-edge-blue/10   border-edge-blue/20',  endpoint: '/arb/scan',       status: 'idle', lastRun: '14m ago' },
  { id: 'middle_scan', label: 'Middles',     description: 'Detect middle opportunities', icon: BarChart2, iconColor: 'text-edge-cyan  bg-edge-cyan/10  border-edge-cyan/20', endpoint: '/middles/scan',   status: 'idle', lastRun: '1h ago' },
  { id: 'live_mon',    label: 'Live Monitor', description: 'Monitor live game lines',  icon: Activity, iconColor: 'text-orange-400 bg-orange-500/10 border-orange-500/20',  endpoint: '/monitor/live',   status: 'idle', lastRun: '5m ago' },
  { id: 'mcp_server',  label: 'MCP Server',  description: 'Restart edge server',      icon: Cpu,      iconColor: 'text-purple-400  bg-purple-500/10  border-purple-500/20', endpoint: '/server/restart', status: 'idle' },
];

// ─── API Endpoint Health ──────────────────────────────────────────────────────

interface EndpointDef {
  label: string;
  path: string;
  method: 'GET' | 'POST';
  group: string;
}

const ENDPOINTS: EndpointDef[] = [
  { label: 'Health',         path: '/health',              method: 'GET',  group: 'Core' },
  { label: 'Bankroll',       path: '/bankroll',            method: 'GET',  group: 'Core' },
  { label: 'Picks Today',    path: '/picks/today',         method: 'GET',  group: 'Picks' },
  { label: 'Generate Picks', path: '/picks/generate',      method: 'POST', group: 'Picks' },
  { label: 'Arb Live',       path: '/arb/live',            method: 'GET',  group: 'Arb' },
  { label: 'Arb Scan',       path: '/arb/scan',            method: 'POST', group: 'Arb' },
  { label: 'Arb Auto',       path: '/arb/auto',            method: 'POST', group: 'Arb' },
  { label: 'Sharp Moves',    path: '/sharp/moves',         method: 'GET',  group: 'Intel' },
  { label: 'Bets',           path: '/bets',                method: 'GET',  group: 'Bets' },
  { label: 'PnL',            path: '/pnl',                 method: 'GET',  group: 'Bets' },
  { label: 'Kalshi Markets', path: '/kalshi/markets',      method: 'GET',  group: 'Kalshi' },
  { label: 'Kalshi Balance', path: '/kalshi/balance',      method: 'GET',  group: 'Kalshi' },
  { label: 'Kalshi Orders',  path: '/kalshi/orders',       method: 'GET',  group: 'Kalshi' },
  { label: 'Kalshi Auto',    path: '/kalshi/auto',         method: 'POST', group: 'Kalshi' },
  { label: 'AI Chat',        path: '/ai/chat',             method: 'POST', group: 'AI' },
  { label: 'Equity Data',    path: '/performance/equity',  method: 'GET',  group: 'Perf' },
];

type PingStatus = 'pending' | 'ok' | 'slow' | 'error';

interface EndpointHealth {
  path: string;
  status: PingStatus;
  latency?: number;
}

// ─── Workflow Card ────────────────────────────────────────────────────────────

import { Target } from 'lucide-react';

function WorkflowCard({ wf }: { wf: WorkflowDef }) {
  const [status, setStatus] = useState<WfStatus>(wf.status);
  const [history, setHistory] = useState<Array<{ at: Date; ok: boolean }>>([]);

  const run = useCallback(async () => {
    if (status === 'running') return;
    setStatus('running');
    const start = Date.now();
    try {
      const r = await fetch(`${API}${wf.endpoint}`, {
        method: wf.endpoint.includes('restart') ? 'POST' : 'POST',
        signal: AbortSignal.timeout(30_000),
      });
      const ok = r.status < 500;
      setStatus(ok ? 'success' : 'error');
      setHistory(h => [{ at: new Date(), ok }, ...h].slice(0, 5));
    } catch {
      setStatus('error');
      setHistory(h => [{ at: new Date(), ok: false }, ...h].slice(0, 5));
    }
    setTimeout(() => setStatus('idle'), 7000);
  }, [status, wf.endpoint]);

  const pillStatus: 'idle' | 'running' | 'success' | 'error' =
    status === 'running' ? 'running' :
    status === 'success' ? 'success' :
    status === 'error'   ? 'error'   : 'idle';

  return (
    <div className={clsx(
      'group flex items-start gap-3 p-4 rounded-xl border transition-all duration-200',
      status === 'running' ? 'bg-edge-blue/7 border-edge-blue/18' :
      status === 'success' ? 'bg-edge-green/7 border-edge-green/18' :
      status === 'error'   ? 'bg-edge-red/7   border-edge-red/18' :
      'bg-ink-900/60 border-ink-800 hover:border-ink-700',
    )}>
      <div className={clsx(
        'w-9 h-9 grid place-items-center rounded-xl border shrink-0',
        wf.iconColor,
      )}>
        {status === 'running'
          ? <Loader2 className="w-4 h-4 animate-spin" />
          : <wf.icon className="w-4 h-4" />
        }
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-semibold text-ink-200">{wf.label}</span>
          <StatusPill status={pillStatus} size="xs" />
        </div>
        <p className="text-[10px] text-ink-500 mt-0.5">{wf.description}</p>
        {wf.lastRun && status === 'idle' && (
          <p className="text-[9px] text-ink-600 mt-1">Last: {wf.lastRun}</p>
        )}
        {status === 'running' && (
          <p className="text-[9px] text-edge-blue mt-1 animate-pulse">Running…</p>
        )}

        {/* Mini history dots */}
        {history.length > 0 && (
          <div className="flex items-center gap-1 mt-1.5">
            {history.slice(0, 5).map((h, i) => (
              <span
                key={i}
                className={clsx('w-1.5 h-1.5 rounded-full', h.ok ? 'bg-edge-green' : 'bg-edge-red')}
                title={h.at.toLocaleTimeString()}
              />
            ))}
          </div>
        )}
      </div>

      <button
        onClick={run}
        disabled={status === 'running'}
        className={clsx(
          'shrink-0 w-7 h-7 grid place-items-center rounded-lg border transition-all',
          'bg-ink-850 border-ink-700 text-ink-500 hover:text-ink-200 hover:border-ink-600',
          'disabled:opacity-30',
        )}
        title={`Run ${wf.label}`}
      >
        <PlayCircle className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// ─── API Health Table ─────────────────────────────────────────────────────────

function ApiHealthTable() {
  const [health, setHealth] = useState<EndpointHealth[]>(
    ENDPOINTS.map(e => ({ path: e.path, status: 'pending' as PingStatus }))
  );
  const [scanning, setScanning] = useState(false);

  const scan = useCallback(async () => {
    setScanning(true);
    const getOnly = ENDPOINTS.filter(e => e.method === 'GET');
    const results = await Promise.allSettled(
      getOnly.map(async e => {
        const t0 = Date.now();
        const r = await fetch(`${API}${e.path}`, { signal: AbortSignal.timeout(4000) });
        return { path: e.path, ok: r.ok, latency: Date.now() - t0 };
      })
    );
    setHealth(prev => {
      const map = new Map(prev.map(h => [h.path, h]));
      results.forEach((r, i) => {
        const path = getOnly[i].path;
        if (r.status === 'fulfilled') {
          const lat = r.value.latency;
          map.set(path, {
            path, latency: lat,
            status: r.value.ok ? (lat > 800 ? 'slow' : 'ok') : 'error',
          });
        } else {
          map.set(path, { path, status: 'error' });
        }
      });
      return ENDPOINTS.map(e => map.get(e.path) ?? { path: e.path, status: 'pending' });
    });
    setScanning(false);
  }, []);

  useEffect(() => { scan(); }, []);

  const STATUS_DOT: Record<PingStatus, string> = {
    pending: 'bg-ink-600',
    ok:      'bg-edge-green',
    slow:    'bg-edge-gold',
    error:   'bg-edge-red animate-pulse',
  };

  const groups = [...new Set(ENDPOINTS.map(e => e.group))];

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-[9px] font-semibold text-ink-500 uppercase tracking-widest">
          {ENDPOINTS.length} endpoints
        </span>
        <button
          onClick={scan}
          disabled={scanning}
          className="flex items-center gap-1 text-[10px] text-ink-500 hover:text-ink-300 transition-colors"
        >
          <RefreshCw className={clsx('w-3 h-3', scanning && 'animate-spin')} />
          {scanning ? 'Scanning…' : 'Scan all'}
        </button>
      </div>

      <div className="space-y-2">
        {groups.map(group => {
          const eps = ENDPOINTS.filter(e => e.group === group);
          return (
            <div key={group}>
              <div className="text-[8px] font-bold text-ink-600 uppercase tracking-widest px-1 mb-1">
                {group}
              </div>
              <div className="space-y-0.5">
                {eps.map(ep => {
                  const h = health.find(x => x.path === ep.path);
                  return (
                    <div key={ep.path} className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-ink-850 transition-colors">
                      <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', STATUS_DOT[h?.status ?? 'pending'])} />
                      <span className="flex-1 text-[10px] text-ink-400">{ep.label}</span>
                      <span className="text-[8px] font-mono text-ink-600">{ep.path}</span>
                      {h?.latency && (
                        <span className={clsx('text-[9px] font-mono', h.latency > 800 ? 'text-edge-gold' : 'text-ink-500')}>
                          {h.latency}ms
                        </span>
                      )}
                      <span className={clsx(
                        'text-[8px] font-bold px-1 rounded',
                        ep.method === 'GET' ? 'bg-edge-blue/10 text-edge-blue' : 'bg-edge-gold/10 text-edge-gold',
                      )}>
                        {ep.method}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── BackOffice main export ───────────────────────────────────────────────────

export default function BackOffice() {
  const [open, setOpen]     = useState(false);
  const [activePane, setActivePane] = useState<'workflows' | 'health'>('workflows');

  const okCount = 0; // will be computed from health data in future

  return (
    <div className="glass-panel p-0 overflow-hidden">
      {/* Collapsible header */}
      <button
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-ink-850/50 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 grid place-items-center rounded-md bg-purple-500/12 border border-purple-500/20">
            <Settings className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <span className="text-xs font-semibold text-ink-300 uppercase tracking-widest">Back Office</span>
          <Badge v="ink">Workflows · Health</Badge>
        </div>
        {open
          ? <ChevronUp className="w-4 h-4 text-ink-500" />
          : <ChevronDown className="w-4 h-4 text-ink-500" />
        }
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="border-t border-ink-800">
              {/* Sub-tab bar */}
              <div className="flex items-center gap-0 px-2 pt-2 border-b border-ink-800">
                {(['workflows', 'health'] as const).map(p => (
                  <button
                    key={p}
                    onClick={() => setActivePane(p)}
                    className={clsx(
                      'px-4 py-2 text-xs font-medium transition-all capitalize border-b-2 -mb-px',
                      activePane === p
                        ? 'border-edge-green text-edge-green'
                        : 'border-transparent text-ink-500 hover:text-ink-300',
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>

              <div className="p-5">
                {activePane === 'workflows' && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {WORKFLOWS.map(wf => <WorkflowCard key={wf.id} wf={wf} />)}
                  </div>
                )}
                {activePane === 'health' && <ApiHealthTable />}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
