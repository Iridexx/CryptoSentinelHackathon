export interface Coin {
  id: string;
  symbol: string;
  name: string;
  image: string;
  current_price: number;
  price_change_percentage_24h: number;
  price_change_percentage_1h_in_currency?: number;
  price_change_percentage_7d_in_currency?: number;
  market_cap: number;
  market_cap_rank: number | null;
  total_volume: number;
  high_24h: number;
  low_24h: number;
}

export type AlertDirection = 'above' | 'below';

export interface PriceAlert {
  id: string;
  coinId: string;
  coinName: string;
  coinSymbol: string;
  coinImage: string;
  direction: AlertDirection;
  threshold: number;
  percentChange?: number;
  note?: string;
  triggered: boolean;
  createdAt: number;
}

export interface AlertHistoryEntry {
  id: string;
  coinId: string;
  coinName: string;
  coinSymbol: string;
  coinImage: string;
  direction: AlertDirection;
  threshold: number;
  triggeredPrice: number;
  triggeredAt: number;
}

export interface RangeAlert {
  id: string;
  coinId: string;
  coinName: string;
  coinSymbol: string;
  coinImage: string;
  minPrice: number;
  maxPrice: number;
  note?: string;
  isInsideRange: boolean | null;
  lastNotifiedAt: number | null;
  createdAt: number;
}
