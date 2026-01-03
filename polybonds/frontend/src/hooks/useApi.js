import { useState, useEffect, useCallback } from 'react';

// Use environment variable for API URL, fallback to /api for local dev
// VITE_API_URL must be set in Vercel for production
const API_BASE = import.meta.env.VITE_API_URL || '/api';
console.log('API_BASE:', API_BASE); // Debug: check if env var is loaded

export function useApi(endpoint, options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { refreshInterval, enabled = true } = options;

  const fetchData = useCallback(async () => {
    if (!enabled) return;

    try {
      const response = await fetch(`${API_BASE}${endpoint}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const json = await response.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [endpoint, enabled]);

  useEffect(() => {
    fetchData();

    if (refreshInterval && enabled) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [fetchData, refreshInterval, enabled]);

  return { data, loading, error, refetch: fetchData };
}

export function usePortfolio() {
  return useApi('/portfolio', { refreshInterval: 10000 });
}

export function useOpportunities(limit = 20) {
  return useApi(`/opportunities?limit=${limit}`, { refreshInterval: 30000 });
}

export function usePositions() {
  return useApi('/positions', { refreshInterval: 10000 });
}

export function useTrades(limit = 20) {
  return useApi(`/trades?limit=${limit}`, { refreshInterval: 15000 });
}

export function useSettlements(limit = 20) {
  return useApi(`/settlements?limit=${limit}`, { refreshInterval: 30000 });
}

export async function triggerScan() {
  const response = await fetch(`${API_BASE}/scan`, { method: 'POST' });
  return response.json();
}

export async function executeTrade(marketId, amount) {
  const response = await fetch(`${API_BASE}/trade/${marketId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount_usd: amount })
  });
  return response.json();
}
