export function fmt$(n: number, decimals = 0): string {
  return n.toLocaleString('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function fmtPct(n: number, decimals = 1, plusSign = false): string {
  const s = `${Math.abs(n).toFixed(decimals)}%`;
  if (plusSign && n > 0) return `+${s}`;
  if (n < 0) return `-${s}`;
  return s;
}

export function fmtOdds(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

export function fmtAge(mins: number): string {
  if (mins < 60)  return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

export function sportKey(sport: string): string {
  return sport.toLowerCase()
    .replace(/americanfootball_|basketball_|baseball_|icehockey_/, '');
}

export const SPORT_COLORS: Record<string, string> = {
  nfl: 'badge-gold',
  nba: 'badge-red',
  mlb: 'badge-blue',
  nhl: 'badge-cyan',
};
