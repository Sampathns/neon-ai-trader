import type {
  BacktestResult,
  Candle,
  ModeStatus,
  NotificationItem,
  PositionRecord,
  ScannerItem,
  SignalDetail,
  TradingMode,
} from "../types/trading";

const STORAGE_KEY = "NEON_TRADER_API_BASE";

function resolveInitialBase(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && saved.trim()) return saved.replace(/\/+$/, "");
  } catch {
    // Ignore storage access errors
  }
  const envBase = (import.meta as any).env?.VITE_API_BASE_URL;
  if (envBase) return String(envBase).replace(/\/+$/, "");
  // Inside Capacitor APK, localhost refers to the phone itself; user can set server URL in-app
  return "/api/v1";
}

class NeonApiClient {
  private token: string | null = null;
  private apiBase: string = resolveInitialBase();

  getBaseUrl(): string {
    return this.apiBase;
  }

  setBaseUrl(url: string) {
    const clean = url.trim().replace(/\/+$/, "");
    this.apiBase = clean.endsWith("/api/v1") ? clean : `${clean}/api/v1`;
    try {
      localStorage.setItem(STORAGE_KEY, this.apiBase);
    } catch {
      // Ignore
    }
  }

  setToken(token: string) {
    this.token = token;
  }

  private headers(): HeadersInit {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) {
      h["Authorization"] = `Bearer ${this.token}`;
    }
    return h;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.apiBase}${path}`, {
      ...init,
      headers: { ...this.headers(), ...(init?.headers || {}) },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    return res.json() as Promise<T>;
  }

  async login(username: string, password: string): Promise<string> {
    const data = await this.request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.token = data.access_token;
    return data.access_token;
  }

  getModeStatus(): Promise<ModeStatus> {
    return this.request<ModeStatus>("/mode/status");
  }

  switchMode(target_mode: TradingMode, acknowledge_open_positions = false): Promise<any> {
    return this.request("/mode/switch", {
      method: "POST",
      body: JSON.stringify({ target_mode, acknowledge_open_positions }),
    });
  }

  enableRealTrading(payload: {
    broker_name: string;
    verified_account_last4: string;
    confirmation_phrase: string;
    risk_acknowledged: boolean;
  }): Promise<any> {
    return this.request("/mode/enable-real", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  toggleScanner(action: "start" | "stop"): Promise<any> {
    return this.request(`/automation/scanner/${action}`, { method: "POST" });
  }

  toggleAutoTrading(action: "enable" | "disable"): Promise<any> {
    return this.request(`/automation/auto-trading/${action}`, { method: "POST" });
  }

  emergencyStop(): Promise<any> {
    return this.request("/automation/emergency-stop", { method: "POST" });
  }

  cancelPendingOrders(): Promise<any> {
    return this.request("/automation/cancel-pending", { method: "POST" });
  }

  getScanner(timeframe = "1h"): Promise<{ items: ScannerItem[] }> {
    return this.request(`/market/scanner?timeframe=${encodeURIComponent(timeframe)}`);
  }

  getCandles(
    symbol: string,
    timeframe = "1h"
  ): Promise<{ symbol: string; data_status: string; candles: Candle[]; order_book: any }> {
    return this.request(`/market/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`);
  }

  getSignal(symbol: string, timeframe = "1h"): Promise<SignalDetail> {
    return this.request(`/analysis/signal/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`);
  }

  getPositions(): Promise<{ positions: PositionRecord[] }> {
    return this.request("/trading/positions");
  }

  getNotifications(): Promise<{ notifications: NotificationItem[] }> {
    return this.request("/notifications");
  }

  runBacktest(payload: {
    symbol: string;
    timeframe: string;
    strategy: string;
    initial_capital: number;
  }): Promise<BacktestResult> {
    return this.request<BacktestResult>("/backtesting/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

export const api = new NeonApiClient();
