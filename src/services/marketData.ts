import { Capacitor, CapacitorHttp } from '@capacitor/core';
import type { Coin } from '../types';

export type ProviderName = 'cmc' | 'coingecko';

interface MarketAsset {
  id: string;
  symbol: string;
  name: string;
  image_url: string | null;
  price: number;
  percent_change_1h: number | null;
  percent_change_24h: number | null;
  percent_change_7d: number | null;
  market_cap: number | null;
  market_cap_rank: number | null;
  volume_24h: number | null;
  high_24h: number | null;
  low_24h: number | null;
}

interface MarketListResponse {
  provider: ProviderName;
  currency: string;
  items: MarketAsset[];
}

export interface OHLCVItem {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

interface OHLCVResponse {
  provider: ProviderName;
  asset_id: string;
  currency: string;
  interval: string | null;
  items: OHLCVItem[];
}

export interface ProviderRuntimeStatus {
  name: ProviderName;
  configured: boolean;
  cache_entries: number;
  credits_used: number;
  requests_made: number;
  requests_per_minute: number;
}

export interface ProviderSelectionResponse {
  active: ProviderName;
  providers: ProviderRuntimeStatus[];
  cmc_mcp: {
    enabled: boolean;
    configured: boolean;
    server_url: string;
    auth_header: string;
  };
  selection_scope: 'process';
}

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const READ_TOKEN = import.meta.env.VITE_API_READ_TOKEN as string | undefined;

function requireBackend(): string {
  if (!BACKEND_URL) throw new Error('Backend market data URL is not configured');
  if (!READ_TOKEN) throw new Error('Read-only market data token is not configured');
  return BACKEND_URL;
}

function headers(token = READ_TOKEN): Record<string, string> {
  if (!token) throw new Error('API token is not configured');
  return { Authorization: `Bearer ${token}`, Accept: 'application/json' };
}

async function request<T>(
  path: string,
  options: { method?: 'GET' | 'PUT'; body?: unknown; token?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const url = `${requireBackend()}${path}`;
  const method = options.method ?? 'GET';
  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.request({
      method,
      url,
      headers: {
        ...headers(options.token),
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
      data: options.body,
      connectTimeout: 20_000,
      readTimeout: 60_000,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`Market data API: ${response.status}`);
    }
    return response.data as T;
  }

  const response = await fetch(url, {
    method,
    headers: {
      ...headers(options.token),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });
  if (!response.ok) throw new Error(`Market data API: ${response.status}`);
  return response.json() as Promise<T>;
}

function toCoin(asset: MarketAsset): Coin {
  return {
    id: asset.id,
    symbol: asset.symbol.toLowerCase(),
    name: asset.name,
    image: asset.image_url ?? '',
    current_price: asset.price,
    price_change_percentage_24h: asset.percent_change_24h ?? 0,
    price_change_percentage_1h_in_currency: asset.percent_change_1h ?? undefined,
    price_change_percentage_7d_in_currency: asset.percent_change_7d ?? undefined,
    market_cap: asset.market_cap ?? 0,
    market_cap_rank: asset.market_cap_rank,
    total_volume: asset.volume_24h ?? 0,
    high_24h: asset.high_24h ?? 0,
    low_24h: asset.low_24h ?? 0,
  };
}

export async function fetchMarkets(
  limit: number,
  page: number,
  currency: string,
  signal?: AbortSignal,
  ids?: string[],
): Promise<Coin[]> {
  const params = new URLSearchParams({
    currency,
    limit: String(limit),
    page: String(page),
  });
  if (ids?.length) params.set('ids', ids.join(','));
  const response = await request<MarketListResponse>(`/api/v1/market-data/markets?${params}`, { signal });
  return response.items.map(toCoin);
}

export async function searchMarkets(
  query: string,
  currency: string,
  signal?: AbortSignal,
): Promise<Coin[]> {
  const params = new URLSearchParams({ q: query, currency, limit: '25' });
  const response = await request<MarketListResponse>(`/api/v1/market-data/search?${params}`, { signal });
  return response.items.map(toCoin);
}

export async function fetchOHLCV(
  assetId: string,
  currency: string,
  days: number,
  signal?: AbortSignal,
): Promise<OHLCVItem[]> {
  const params = new URLSearchParams({ asset_id: assetId, currency, days: String(days) });
  const response = await request<OHLCVResponse>(`/api/v1/market-data/ohlcv?${params}`, { signal });
  return response.items;
}

export function getProviderStatus(): Promise<ProviderSelectionResponse> {
  return request<ProviderSelectionResponse>('/api/v1/market-data/provider');
}

export function selectProvider(provider: ProviderName, adminToken: string): Promise<ProviderSelectionResponse> {
  return request<ProviderSelectionResponse>('/api/v1/market-data/provider', {
    method: 'PUT',
    body: { provider },
    token: adminToken,
  });
}
