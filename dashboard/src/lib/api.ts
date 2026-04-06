'use client';
import { useState, useEffect, useCallback } from 'react';

export const API = process.env.NEXT_PUBLIC_MCP_API_URL || 'http://localhost:8420';
export const WS_BASE = API.replace(/^http/, 'ws');

export function useApi<T>(endpoint: string, initialValue: T, intervalMs = 0) {
  const [data, setData]       = useState<T>(initialValue);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const res = await fetch(`${API}${endpoint}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(null);
      setLastFetch(new Date());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    fetch_();
    if (intervalMs > 0) {
      const id = setInterval(fetch_, intervalMs);
      return () => clearInterval(id);
    }
  }, [fetch_, intervalMs]);

  return { data, loading, error, refetch: fetch_, lastFetch };
}
