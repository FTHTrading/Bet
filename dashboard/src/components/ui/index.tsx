'use client';
import React from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';

// ─── GlassPanel ───────────────────────────────────────────────────────────────

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: 'green' | 'blue' | 'gold' | 'red' | 'purple' | 'cyan' | 'none';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  animate?: boolean;
  onClick?: () => void;
}

const GLOW_COLORS: Record<string, string> = {
  green:  'hover:border-edge-green/25 hover:shadow-[0_0_0_1px_rgba(0,232,122,0.12),0_16px_48px_rgba(0,0,0,0.65)]',
  blue:   'hover:border-edge-blue/25  hover:shadow-[0_0_0_1px_rgba(59,130,246,0.15),0_16px_48px_rgba(0,0,0,0.65)]',
  gold:   'hover:border-edge-gold/25  hover:shadow-[0_0_0_1px_rgba(245,158,11,0.15),0_16px_48px_rgba(0,0,0,0.65)]',
  red:    'hover:border-edge-red/25   hover:shadow-[0_0_0_1px_rgba(255,77,109,0.15),0_16px_48px_rgba(0,0,0,0.65)]',
  purple: 'hover:border-purple-500/25 hover:shadow-[0_0_0_1px_rgba(168,85,247,0.15),0_16px_48px_rgba(0,0,0,0.65)]',
  cyan:   'hover:border-edge-cyan/25  hover:shadow-[0_0_0_1px_rgba(6,182,212,0.15),0_16px_48px_rgba(0,0,0,0.65)]',
  none:   '',
};

const PAD = { none: '', sm: 'p-3', md: 'p-5', lg: 'p-6' };

export function GlassPanel({
  children, className, hover = true, glow = 'none', padding = 'md', animate = false, onClick,
}: GlassPanelProps) {
  const base = clsx(
    'glass-panel relative overflow-hidden',
    PAD[padding],
    hover && 'hover:-translate-y-px transition-all duration-300',
    glow !== 'none' && GLOW_COLORS[glow],
    onClick && 'cursor-pointer',
    className,
  );

  if (animate) {
    return (
      <motion.div
        className={base}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        onClick={onClick}
      >
        {children}
      </motion.div>
    );
  }

  return <div className={base} onClick={onClick}>{children}</div>;
}

// ─── StatusPill ───────────────────────────────────────────────────────────────

type PillVariant = 'live' | 'connecting' | 'offline' | 'running' | 'success' | 'warning' | 'error' | 'idle';

interface StatusPillProps {
  status: PillVariant;
  label?: string;
  showDot?: boolean;
  size?: 'xs' | 'sm';
}

const PILL_STYLES: Record<PillVariant, { dot: string; text: string; bg: string; border: string }> = {
  live:       { dot: 'bg-edge-green animate-pulse', text: 'text-edge-green',  bg: 'bg-edge-green/8',   border: 'border-edge-green/20' },
  connecting: { dot: 'bg-edge-gold  animate-pulse', text: 'text-edge-gold',   bg: 'bg-edge-gold/8',    border: 'border-edge-gold/20' },
  offline:    { dot: 'bg-edge-red',                 text: 'text-edge-red',    bg: 'bg-edge-red/8',     border: 'border-edge-red/20' },
  running:    { dot: 'bg-edge-blue  animate-pulse', text: 'text-edge-blue',   bg: 'bg-edge-blue/8',    border: 'border-edge-blue/20' },
  success:    { dot: 'bg-edge-green',               text: 'text-edge-green',  bg: 'bg-edge-green/8',   border: 'border-edge-green/20' },
  warning:    { dot: 'bg-edge-gold',                text: 'text-edge-gold',   bg: 'bg-edge-gold/8',    border: 'border-edge-gold/20' },
  error:      { dot: 'bg-edge-red',                 text: 'text-edge-red',    bg: 'bg-edge-red/8',     border: 'border-edge-red/20' },
  idle:       { dot: 'bg-ink-500',                  text: 'text-ink-400',     bg: 'bg-ink-800',        border: 'border-ink-700' },
};

export function StatusPill({ status, label, showDot = true, size = 'xs' }: StatusPillProps) {
  const s = PILL_STYLES[status];
  return (
    <div className={clsx(
      'flex items-center gap-1.5 rounded-full border px-2.5 py-0.5',
      s.bg, s.border,
      size === 'xs' ? 'text-[10px]' : 'text-xs',
    )}>
      {showDot && <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', s.dot)} />}
      <span className={clsx('font-semibold tracking-wider uppercase', s.text)}>
        {label ?? status}
      </span>
    </div>
  );
}

// ─── Badge Variants ───────────────────────────────────────────────────────────

type BadgeVariant = 'green' | 'blue' | 'gold' | 'red' | 'purple' | 'cyan' | 'ink' | 'orange';

const BADGE_STYLES: Record<BadgeVariant, string> = {
  green:  'bg-edge-green/15 text-edge-green   border border-edge-green/30',
  blue:   'bg-edge-blue/15  text-edge-blue    border border-edge-blue/30',
  gold:   'bg-edge-gold/15  text-edge-gold    border border-edge-gold/30',
  red:    'bg-edge-red/15   text-edge-red     border border-edge-red/30',
  purple: 'bg-purple-500/12 text-purple-400   border border-purple-500/30',
  cyan:   'bg-edge-cyan/15  text-edge-cyan    border border-edge-cyan/30',
  ink:    'bg-ink-800       text-ink-400      border border-ink-700',
  orange: 'bg-orange-500/12 text-orange-400   border border-orange-500/25',
};

export function Badge({ v, children, className }: {
  v: BadgeVariant; children: React.ReactNode; className?: string;
}) {
  return (
    <span className={clsx(
      'inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold leading-none tracking-wide',
      BADGE_STYLES[v], className,
    )}>
      {children}
    </span>
  );
}

// ─── Sport Pill ───────────────────────────────────────────────────────────────

const SPORT_BADGE: Record<string, BadgeVariant> = {
  nfl: 'gold', nba: 'red', mlb: 'blue', nhl: 'cyan',
  ncaab: 'purple', ncaaf: 'orange', mls: 'green', soccer: 'green',
};

export function SportPill({ sport }: { sport: string }) {
  const key = sport.toLowerCase()
    .replace(/americanfootball_|basketball_|baseball_|icehockey_/, '');
  return <Badge v={SPORT_BADGE[key] ?? 'ink'} className="uppercase tracking-widest">{key}</Badge>;
}

// ─── Verdict Badge ────────────────────────────────────────────────────────────

export function VerdictBadge({ verdict }: { verdict: string }) {
  const v = (verdict ?? '').toUpperCase();
  if (v.includes('EXCELLENT') || v.includes('STRONG')) return <Badge v="green">{verdict}</Badge>;
  if (v.includes('GOOD'))     return <Badge v="blue">{verdict}</Badge>;
  if (v.includes('MARGINAL')) return <Badge v="gold">{verdict}</Badge>;
  return <Badge v="red">{verdict}</Badge>;
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton rounded', className)} />;
}

export function SkeletonRows({ n = 3 }: { n?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

// ─── EmptyState ───────────────────────────────────────────────────────────────

import { Activity } from 'lucide-react';

export function EmptyState({ msg, icon: Icon = Activity }: {
  msg: string;
  icon?: React.ElementType;
}) {
  return (
    <div className="py-12 flex flex-col items-center gap-3 text-ink-500">
      <Icon className="w-8 h-8 opacity-25" />
      <p className="text-sm text-center max-w-xs leading-relaxed">{msg}</p>
    </div>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

import { Loader2 } from 'lucide-react';

export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sz = size === 'sm' ? 'w-4 h-4' : size === 'lg' ? 'w-7 h-7' : 'w-5 h-5';
  return (
    <div className="flex items-center justify-center py-8">
      <Loader2 className={clsx(sz, 'animate-spin text-edge-green/50')} />
    </div>
  );
}

// ─── OddsChip ─────────────────────────────────────────────────────────────────

export function OddsChip({ odds }: { odds: number }) {
  return (
    <span className={clsx(
      'font-mono font-semibold text-sm',
      odds > 0 ? 'text-edge-green' : 'text-ink-200',
    )}>
      {odds > 0 ? `+${odds}` : odds}
    </span>
  );
}

// ─── Section Header ───────────────────────────────────────────────────────────

export function SectionHeader({
  icon: Icon, iconCls, title, children,
}: {
  icon: React.ElementType;
  iconCls: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="section-title">
      <div className={clsx('section-title-icon', iconCls)}>
        <Icon className="w-4 h-4" />
      </div>
      <span className="section-title-text">{title}</span>
      {children}
    </div>
  );
}
