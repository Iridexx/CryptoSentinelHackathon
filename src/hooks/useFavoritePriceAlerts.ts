export interface FavAlertData {
  coinId: string;
  coinName: string;
  coinSymbol: string;
  direction: 'up' | 'down';
  pct: number;
  currentPrice: number;
  refPrice: number;
}
