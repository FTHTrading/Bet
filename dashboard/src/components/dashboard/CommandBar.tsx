'use client';
import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Zap, Wifi, WifiOff, Activity, RefreshCw, Bell,
  Search, Command, Moon, Sun, ChevronDown, Cpu,
} from 'lucide-react';
import { StatusPill } from '@/components/ui';
import clsx from 'clsx';

const API = process.env.NEXT_PUBLIC_MCP_API_URL || 'http://localhost:8420';

type ConnState = 'live' | 'connecting' | 'offline';

interface CommandBarProps {
  onSearch?: (q: string) => void;
}

export default function CommandBar({ onSearch }: CommandBarProps) {
  const [conn, setConn]         = useState<ConnState>('connecting');
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [now, setNow]           = useState(new Date());
  const [searchOpen, setSearchOpen]   = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notifOpen, setNotifOpen]     = useState(false);
  const [spinning, setSpinning]       = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // Clock tick
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Connectivity probe
  useEffect(() => {
    let isMounted = true;
    const check = async () => {
      try {
        const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(4000) });
        if (!isMounted) return;
        setConn(r.ok ? 'live' : 'offline');
        if (r.ok) setLastSync(new Date());
      } catch {
        if (isMounted) setConn('offline');
      }
    };
    check();
    const t = setInterval(check, 15000);
    return () => { isMounted = false; clearInterval(t); };
  }, []);

  // ⌘K / Ctrl+K global shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(s => !s);
        setTimeout(() => searchRef.current?.focus(), 50);
      }
      if (e.key === 'Escape') setSearchOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleRefresh = () => {
    setSpinning(true);
    window.dispatchEvent(new Event('kalishi:refresh'));
    setTimeout(() => setSpinning(false), 900);
  };

  const fmtTime = (d: Date) =>
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  const fmtDate = (d: Date) =>
    d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  const fmtSince = (d: Date | null) => {
    if (!d) return 'never';
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 60) return `${s}s ago`;
    return `${Math.round(s / 60)}m ago`;
  };

  return (
    <header className="command-bar sticky top-0 z-50">
      {/* Left: Identity */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="w-7 h-7 grid place-items-center rounded-lg bg-gradient-to-br from-edge-green/30 to-edge-blue/20 border border-edge-green/25">
            <Zap className="w-3.5 h-3.5 text-edge-green" strokeWidth={2.5} />
          </span>
          <div>
            <div className="text-xs font-bold tracking-widest text-ink-100 uppercase leading-none">
              Kalishi Edge
            </div>
            <div className="text-[9px] font-medium text-ink-500 tracking-widest uppercase leading-none mt-0.5">
              AI Command Center
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="w-px h-6 bg-ink-800" />

        {/* Clock */}
        <div className="text-right hidden sm:block">
          <div className="font-mono text-xs font-semibold text-ink-200 leading-none">
            {fmtTime(now)}
          </div>
          <div className="text-[9px] text-ink-500 leading-none mt-0.5 tracking-wide">
            {fmtDate(now)}
          </div>
        </div>
      </div>

      {/* Center: Search bar */}
      <div className="hidden md:flex flex-1 justify-center px-6">
        <button
          className={clsx(
            'flex items-center gap-2 w-full max-w-sm px-3 py-1.5 rounded-lg',
            'bg-ink-850 border border-ink-750 text-ink-400 text-xs',
            'hover:border-ink-600 hover:text-ink-300 transition-colors duration-150',
            searchOpen && 'hidden',
          )}
          onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 50); }}
        >
          <Search className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1 text-left">Search picks, markets…</span>
          <kbd className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-ink-800 border border-ink-700 text-ink-500">
            ⌘K
          </kbd>
        </button>

        <AnimatePresence>
          {searchOpen && (
            <motion.div
              className="w-full max-w-sm"
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ duration: 0.12 }}
            >
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-edge-green/70" />
                <input
                  ref={searchRef}
                  type="text"
                  value={searchQuery}
                  onChange={e => { setSearchQuery(e.target.value); onSearch?.(e.target.value); }}
                  placeholder="Search picks, markets, teams…"
                  className="w-full pl-9 pr-4 py-1.5 rounded-lg bg-ink-850 border border-edge-green/30 text-xs text-ink-100
                    placeholder:text-ink-500 outline-none ring-0 focus:border-edge-green/50 transition-colors"
                  onBlur={() => !searchQuery && setSearchOpen(false)}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Right: Status cluster */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Connection status */}
        <StatusPill status={conn} />

        {/* Last sync */}
        <div className="hidden lg:flex items-center gap-1.5 text-ink-500 text-[10px]">
          <Activity className="w-3 h-3" />
          <span className="font-mono">{fmtSince(lastSync)}</span>
        </div>

        {/* Mode badge */}
        <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full
          bg-edge-gold/10 border border-edge-gold/25 text-[10px] font-bold tracking-widest
          text-edge-gold uppercase">
          <Cpu className="w-2.5 h-2.5" />
          Live
        </span>

        {/* Divider */}
        <div className="w-px h-4 bg-ink-800" />

        {/* Refresh */}
        <button
          className="icon-btn"
          onClick={handleRefresh}
          title="Refresh all panels"
        >
          <RefreshCw className={clsx('w-3.5 h-3.5', spinning && 'animate-spin')} />
        </button>

        {/* Notifications */}
        <div className="relative">
          <button
            className="icon-btn relative"
            onClick={() => setNotifOpen(s => !s)}
            title="Notifications"
          >
            <Bell className="w-3.5 h-3.5" />
            <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-edge-red rounded-full" />
          </button>

          <AnimatePresence>
            {notifOpen && (
              <motion.div
                className="absolute right-0 top-full mt-2 w-72 glass-panel p-0 overflow-hidden"
                initial={{ opacity: 0, y: -8, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.97 }}
                transition={{ duration: 0.15 }}
              >
                <div className="px-4 py-3 border-b border-ink-800">
                  <span className="text-xs font-semibold text-ink-200">System Alerts</span>
                </div>
                <div className="p-3 space-y-1.5">
                  {[
                    { color: 'text-edge-green', msg: 'Arb scanner returned 2 opportunities' },
                    { color: 'text-edge-gold',  msg: 'Steam detected: NFL line shifted 3pts' },
                    { color: 'text-edge-blue',  msg: 'Daily picks refresh complete' },
                  ].map(({ color, msg }, i) => (
                    <div key={i} className="flex items-start gap-2 text-[11px]">
                      <span className={clsx('mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 bg-current', color)} />
                      <span className="text-ink-300 leading-relaxed">{msg}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}
