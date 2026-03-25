import customtkinter as ctk
import ccxt
import threading
import time
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplfinance as mpf
import os
import json
from datetime import datetime, timezone
import numpy as np
from dotenv import load_dotenv

load_dotenv()  # Lädt Werte aus .env Datei

# ==============================================================
# SVEN'S TRADING IMPERIUM – 3 COINS PAPER EDITION
# BTC/USDC · ETH/USDC · SOL/USDC
# ==============================================================
# FEATURES:
#   ✅ PaperExchange  – Echte Logik, kein echtes Geld
#   ✅ TradeCache     – RAM + Disk, überlebt Abstürze & Internet-Ausfälle
#   ✅ Auto-Restore   – Gewinn/Verlust werden nach Absturz wiederhergestellt
#   ✅ Balance-Save   – Paper-Kontostand überlebt Neustarts
#   ✅ 6 Tabs         – Cockpit · Strategien · Charts · Handel · Viewer · Analyse
#   ✅ Profit Factor  – Max Drawdown · Heute-P&L · Per-Coin Stats
#   ✅ Markt-Regime   – TREND↑ / TREND↓ / SEITWÄRTS / VOLATIL
#   ✅ 3 Strategien   – Whale / Swing / Scalping
#   ✅ Telegram       – Kauf/Verkauf Benachrichtigungen
# ==============================================================

# ── TELEGRAM ──────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── COINS ─────────────────────────────────────────────────────
COINS = ['BTC/USDC', 'ETH/USDC', 'SOL/USDC']

# ── FARBEN ────────────────────────────────────────────────────
CLR_BG     = "#0a0a0b"
CLR_CARD   = "#141417"
CLR_ACCENT = "#f1c40f"
CLR_GREEN  = "#00ff88"
CLR_RED    = "#ff4655"
CLR_BLUE   = "#4fa3e0"
CLR_PURPLE = "#9b59b6"
CLR_ORANGE = "#ff9500"

# ── DATEIEN ───────────────────────────────────────────────────
LOG_FILE         = "trades_log_3coins.json"
LOG_FILE_TMP     = "trades_log_3coins.tmp"
LOG_BACKUP       = "trades_log_3coins_backup.json"
PAPER_STATE_FILE = "paper_balance.json"

# ── STRATEGIEN ────────────────────────────────────────────────
STRATEGIES = {
    "🐋 WHALE (Empfohlen)": {
        "description": "Kauft bei starkem Aufwärtstrend mit Bestätigung.\nMACD + RSI + CVD müssen grün sein.\nHält Positionen länger, mehr Gewinn pro Trade.",
        "rsi_buy": 45, "rsi_sell": 72, "sl": 4.0, "tp": 8.0, "trail": 1.5,
        "pos_size": 25, "min_score": 5, "timeframe": "5m",
        "macd": True, "ema": True, "cvd": True, "vwap": True,
        "logic": "MACD Pflicht + RSI + CVD (mind. 3/4 Signale)"
    },
    "📈 SWING (Mittel)": {
        "description": "Mittelfristige Trades, 15m Kerzen.\nRSI unter 40 als Einstieg, Trailing Stop enger.\nGut für Seitwärtsmärkte.",
        "rsi_buy": 40, "rsi_sell": 68, "sl": 3.5, "tp": 6.0, "trail": 1.0,
        "pos_size": 20, "min_score": 4, "timeframe": "15m",
        "macd": True, "ema": True, "cvd": False, "vwap": True,
        "logic": "RSI + EMA + VWAP (mind. 2/3 Signale)"
    },
    "⚡ SCALPING (Schnell)": {
        "description": "Viele kleine Gewinne, 1m Kerzen.\nSehr enger Stop-Loss, schnelle Ein/Ausstiege.\nNur für erfahrene Trader!",
        "rsi_buy": 50, "rsi_sell": 65, "sl": 1.5, "tp": 2.5, "trail": 0.5,
        "pos_size": 15, "min_score": 3, "timeframe": "1m",
        "macd": True, "ema": False, "cvd": True, "vwap": False,
        "logic": "MACD + CVD (Schnell-Signale)"
    },
}


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# TRADE CACHE – RAM + Disk, überlebt Abstürze & Internet-Ausfälle
# ══════════════════════════════════════════════════════════════
class TradeCache:
    """
    Alle Trades werden sofort im RAM gespeichert UND alle 30s auf Disk
    gesichert. Bei Verkauf sofort speichern. Startet der Bot neu, werden
    alle Trades geladen und Gewinn/Verlust automatisch wiederhergestellt.
    """
    def __init__(self, max_size=10000):
        self._cache       = []
        self._lock        = threading.Lock()
        self._dirty       = False
        self._max_size    = max_size
        self._stats_cache = None
        self._stats_dirty = True
        self._load_from_disk()
        threading.Thread(target=self._auto_save_loop, daemon=True).start()

    def _load_from_disk(self):
        if not os.path.exists(LOG_FILE):
            return
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    with self._lock:
                        self._cache = json.loads(content)[-self._max_size:]
            print(f"[Cache] ✅ {len(self._cache)} Trades geladen")
        except Exception as e:
            print(f"[Cache] ⚠️ Ladefehler: {e}")
            if os.path.exists(LOG_FILE):
                os.rename(LOG_FILE, f"{LOG_FILE}.broken_{int(time.time())}")

    def _save_to_disk(self):
        if not self._dirty:
            return
        try:
            with self._lock:
                data = list(self._cache)
            content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
            with open(LOG_FILE_TMP, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(LOG_FILE_TMP, LOG_FILE)
            self._dirty = False
        except Exception as e:
            print(f"[Cache] ❌ Speicherfehler: {e}")

    def _auto_save_loop(self):
        """Speichert alle 30 Sekunden wenn nötig."""
        while True:
            time.sleep(30)
            if self._dirty:
                self._save_to_disk()

    def backup(self):
        try:
            with self._lock:
                data = list(self._cache)
            with open(LOG_BACKUP, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            print(f"[Cache] 💾 Backup erstellt: {len(data)} Trades")
        except Exception:
            pass

    def add(self, trade: dict):
        if "time" not in trade:
            trade["time"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._cache.append(trade)
            if len(self._cache) > self._max_size:
                self._cache = self._cache[-self._max_size:]
        self._dirty       = True
        self._stats_dirty = True
        # Bei Verkauf: sofort speichern (Absturz-Schutz!)
        if trade.get("type") in ("SELL", "MANUAL_SELL"):
            self._save_to_disk()

    def get_all(self):
        with self._lock:
            return list(self._cache)

    def get_sells(self):
        with self._lock:
            return [t for t in self._cache if t.get("type") == "SELL"]

    def get_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            return [t for t in self._cache if str(t.get("time", "")).startswith(today)]

    def get_by_coin(self, coin):
        with self._lock:
            return [t for t in self._cache if t.get("coin") == coin]

    def count(self):
        with self._lock:
            return len(self._cache)

    def clear(self):
        self.backup()
        with self._lock:
            self._cache = []
        self._dirty       = True
        self._stats_dirty = True
        self._save_to_disk()

    def get_stats(self, coin=None) -> dict:
        if not self._stats_dirty and self._stats_cache and coin is None:
            return self._stats_cache
        sells = self.get_sells()
        if coin:
            sells = [t for t in sells if t.get("coin") == coin]
        pnls   = [t.get("pnl", 0) for t in sells]
        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        winrate = len(wins) / len(sells) * 100 if sells else 0.0
        best_s = cur_s = 0
        for p in pnls:
            if p > 0:
                cur_s += 1; best_s = max(best_s, cur_s)
            else:
                cur_s = 0
        tw = sum(wins); tl = abs(sum(losses))
        pf = round(tw / tl, 2) if tl > 0 else 999.0
        peak = running = max_dd = 0.0
        for p in pnls:
            running += p
            if running > peak: peak = running
            dd = peak - running
            if dd > max_dd: max_dd = dd
        today_pnl = sum(t.get("pnl", 0) for t in self.get_today() if t.get("type") == "SELL")
        stats = {
            "total_trades":  len(self.get_all()),
            "sell_trades":   len(sells),
            "wins":          len(wins),
            "losses":        len(losses),
            "winrate":       round(winrate, 1),
            "total_pnl":     round(sum(pnls), 2),
            "avg_win":       round(tw / len(wins),    2) if wins   else 0.0,
            "avg_loss":      round(sum(losses) / len(losses), 2) if losses else 0.0,
            "best_trade":    round(max(pnls), 2) if pnls else 0.0,
            "worst_trade":   round(min(pnls), 2) if pnls else 0.0,
            "best_streak":   best_s,
            "profit_factor": pf,
            "max_drawdown":  round(max_dd, 2),
            "today_pnl":     round(today_pnl, 2),
        }
        if coin is None:
            self._stats_cache = stats; self._stats_dirty = False
        return stats

    def get_pnl_series(self):
        return [t.get("pnl", 0) for t in self.get_sells()]

    def get_cumulative_pnl(self):
        total = 0.0; result = []
        for p in self.get_pnl_series():
            total += p; result.append(round(total, 2))
        return result

    def get_hourly_pnl(self) -> dict:
        hourly = {}
        for t in self.get_sells():
            h = str(t.get("time", ""))[11:13] + ":00"
            hourly[h] = hourly.get(h, 0) + t.get("pnl", 0)
        return dict(sorted(hourly.items()))

    def get_coin_stats(self) -> dict:
        return {c: self.get_stats(coin=c) for c in ["BTC/USDC", "ETH/USDC", "SOL/USDC"]}

    # ── Absturz-Wiederherstellung ──────────────────────────────
    def calc_session_profit(self) -> float:
        """Gesamt-PnL aller Verkäufe – wird nach Neustart wiederhergestellt."""
        return sum(t.get("pnl", 0) for t in self.get_sells())

    def calc_daily_loss(self) -> float:
        """Tagesverlust (nur negative PnL von heute) – nach Neustart wiederhergestellt."""
        today = datetime.now().strftime("%Y-%m-%d")
        sells = [t for t in self.get_sells() if str(t.get("time", "")).startswith(today)]
        return abs(sum(t.get("pnl", 0) for t in sells if t.get("pnl", 0) < 0))


# ══════════════════════════════════════════════════════════════
# PAPER EXCHANGE – Simuliert Käufe/Verkäufe ohne echtes Geld
# ══════════════════════════════════════════════════════════════
class PaperExchange:
    """
    Paper-Trading Exchange. Echte Handelslogik, kein echtes Geld.
    Balance wird in paper_balance.json gespeichert und überlebt Neustarts.
    """
    def __init__(self, symbols, base='USDC', initial_balance=10000.0, data_client=None):
        self.base        = base
        self.symbols     = symbols
        self.data_client = data_client
        self._lock       = threading.Lock()
        self.balances    = {
            'total': {base: initial_balance},
            'free':  {base: initial_balance}
        }
        for sym in symbols:
            asset = sym.split('/')[0]
            self.balances['total'][asset] = 0.0
            self.balances['free'][asset]  = 0.0
        self._load_state()

    def _load_state(self):
        """Lädt gespeicherte Balance beim Start."""
        if not os.path.exists(PAPER_STATE_FILE):
            return
        try:
            with open(PAPER_STATE_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            with self._lock:
                self.balances = saved
            print(f"[Paper] ✅ Balance geladen: {self.balances['total'].get('USDC', 0):.2f} USDC")
        except Exception as e:
            print(f"[Paper] ⚠️ Balance-Ladefehler: {e}")

    def _save_state(self):
        """Speichert aktuelle Balance sicher auf Disk."""
        try:
            with self._lock:
                data = {k: dict(v) for k, v in self.balances.items()}
            tmp = PAPER_STATE_FILE + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, PAPER_STATE_FILE)
        except Exception as e:
            print(f"[Paper] ❌ Balance-Speicherfehler: {e}")

    def fetch_balance(self):
        with self._lock:
            return {k: dict(v) for k, v in self.balances.items()}

    def _get_price(self, coin):
        if self.data_client is None:
            raise ValueError("Kein Marktdaten-Client verfügbar")
        return self.data_client.fetch_ticker(coin)['last']

    def fetch_ticker(self, coin):
        """Kompatibilitäts-Wrapper (für Schnellhandel)."""
        return {'last': self._get_price(coin)}

    def create_market_buy_order(self, coin, amount, params=None):
        params = params or {}
        quote  = params.get('quoteOrderQty')
        if quote is None:
            raise ValueError("PaperExchange: quoteOrderQty fehlt")
        price = self._get_price(coin)
        asset = coin.split('/')[0]
        base  = coin.split('/')[1]
        qty   = quote / price
        with self._lock:
            free_base = self.balances['free'].get(base, 0.0)
            if free_base < quote:
                raise ValueError(f"PaperExchange: zu wenig {base} (frei: {free_base:.2f})")
            self.balances['free'][base]    -= quote
            self.balances['total'][base]   -= quote
            self.balances['free'][asset]    = self.balances['free'].get(asset, 0.0)  + qty
            self.balances['total'][asset]   = self.balances['total'].get(asset, 0.0) + qty
        self._save_state()
        return {'symbol': coin, 'side': 'buy', 'price': price, 'amount': qty, 'cost': quote}

    def create_market_sell_order(self, coin, qty):
        price = self._get_price(coin)
        asset = coin.split('/')[0]
        base  = coin.split('/')[1]
        quote = qty * price
        with self._lock:
            free_asset = self.balances['free'].get(asset, 0.0)
            if free_asset < qty * 0.9999:   # kleine Float-Toleranz
                raise ValueError(f"PaperExchange: zu wenig {asset} (frei: {free_asset:.8f})")
            self.balances['free'][asset]    -= qty
            self.balances['total'][asset]   -= qty
            self.balances['free'][base]      = self.balances['free'].get(base, 0.0)  + quote
            self.balances['total'][base]     = self.balances['total'].get(base, 0.0) + quote
        self._save_state()
        return {'symbol': coin, 'side': 'sell', 'price': price, 'amount': qty, 'cost': quote}

    def reset_balance(self, initial_balance=10000.0):
        """Setzt Paper-Balance auf den Startwert zurück."""
        with self._lock:
            self.balances = {
                'total': {self.base: initial_balance},
                'free':  {self.base: initial_balance}
            }
            for sym in self.symbols:
                asset = sym.split('/')[0]
                self.balances['total'][asset] = 0.0
                self.balances['free'][asset]  = 0.0
        self._save_state()


# ── INDIKATOREN ───────────────────────────────────────────────
def calc_cvd(df: pd.DataFrame) -> pd.Series:
    """CVD: Steigend = Käufer dominieren → Bullisch"""
    delta = df['Volume'].copy()
    delta[df['Close'] < df['Open']] *= -1
    return delta.cumsum()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP: Kurs über VWAP = Käufer zahlen über Durchschnitt"""
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    return (typical * df['Volume']).cumsum() / df['Volume'].cumsum()


def calc_stoch_rsi(rsi_series: pd.Series, period=14) -> pd.Series:
    """StochRSI: Sensitiver als RSI, erkennt Wendepunkte früher"""
    min_r = rsi_series.rolling(period).min()
    max_r = rsi_series.rolling(period).max()
    return (rsi_series - min_r) / (max_r - min_r + 1e-10) * 100


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Berechnet alle Indikatoren in einem Durchgang."""
    df['RSI']      = ta.rsi(df['Close'], length=14)
    df['StochRSI'] = calc_stoch_rsi(df['RSI'])
    df['EMA20']    = ta.ema(df['Close'], length=20)
    df['EMA50']    = ta.ema(df['Close'], length=50)
    df['ATR']      = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['CVD']      = calc_cvd(df)
    df['VWAP']     = calc_vwap(df)
    macd_df = ta.macd(df['Close'])
    if macd_df is not None:
        df['MACD']        = macd_df.iloc[:, 0]
        df['MACD_signal'] = macd_df.iloc[:, 2]
        df['MACD_hist']   = macd_df.iloc[:, 1]
    adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
    if adx_df is not None:
        df['ADX'] = adx_df.iloc[:, 0]
    df['Vol_avg']  = df['Volume'].rolling(20).mean()
    df['Vol_high'] = df['Volume'] > df['Vol_avg'] * 1.2
    return df


# ══════════════════════════════════════════════════════════════
# HAUPTKLASSE
# ══════════════════════════════════════════════════════════════
class SvensImperium(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("⚡ SVEN'S IMPERIUM – 3 COINS PAPER EDITION")
        self.geometry("1620x1050")
        self.configure(fg_color=CLR_BG)

        # Trade-Status
        self.highest_prices   = {c: 0.0   for c in COINS}
        self.entry_prices     = {c: 0.0   for c in COINS}
        self.active_trades    = {c: False  for c in COINS}
        self.is_running       = False
        self.price_cache      = {c: 0.0   for c in COINS}
        self.last_df          = {c: None  for c in COINS}
        self.current_strategy = "🐋 WHALE (Empfohlen)"

        # ── TradeCache laden (überlebt Abstürze!) ──────────────
        self.cache = TradeCache()

        # ── PnL & Tagesverlust aus Cache wiederherstellen ──────
        self.session_profit = self.cache.calc_session_profit()
        self.daily_loss     = self.cache.calc_daily_loss()

        # ── Marktdaten-Client (nur lesend, kein API-Key nötig) ─
        self.data_client = None
        self._init_data_client()

        # ── Paper-Exchange (simuliert Trades) ──────────────────
        self.exchange = PaperExchange(
            COINS, base='USDC', initial_balance=10000.0,
            data_client=self.data_client
        )

        # ── UI-Variablen ───────────────────────────────────────
        self.trade_count       = ctk.StringVar(value="3")
        self.sl_active         = ctk.BooleanVar(value=True)
        self.sl_val            = ctk.StringVar(value="4.0")
        self.tp_active         = ctk.BooleanVar(value=False)
        self.tp_val            = ctk.StringVar(value="8.0")
        self.trail_active      = ctk.BooleanVar(value=True)
        self.trail_val         = ctk.StringVar(value="1.5")
        self.rsi_active        = ctk.BooleanVar(value=True)
        self.rsi_buy_val       = ctk.StringVar(value="45")
        self.rsi_sell_val      = ctk.StringVar(value="72")
        self.ema_active        = ctk.BooleanVar(value=True)
        self.macd_active       = ctk.BooleanVar(value=True)
        self.cvd_active        = ctk.BooleanVar(value=True)
        self.vwap_active       = ctk.BooleanVar(value=True)
        self.daily_loss_active = ctk.BooleanVar(value=True)
        self.daily_loss_val    = ctk.StringVar(value="30.0")
        self.pos_size_pct      = ctk.StringVar(value="25")
        self.min_score_var     = ctk.StringVar(value="5")
        self.timeframe_var     = ctk.StringVar(value="5m")
        self.manual_coin_var   = ctk.StringVar(value="BTC/USDC")
        self.manual_amount_var = ctk.StringVar(value="20")

        self.chart_figs = {}; self.chart_canvases = {}; self.chart_axes = {}
        self.mc_axes    = {}; self.mc_canvases    = {}

        self.setup_ui()

        # Sekündlicher Preis-Ticker
        threading.Thread(target=self._price_ticker, daemon=True).start()

        # Wiederhergestellte Stats nach kurzer Verzögerung in UI eintragen
        self.after(500, self._restore_ui_stats)

    # ──────────────────────────────────────────────────────────
    # DATEN-CLIENT (kein API-Key nötig für Paper-Mode)
    # ──────────────────────────────────────────────────────────
    def _init_data_client(self):
        try:
            self.data_client = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 10000,
            })
            print("✅ Marktdaten-Client verbunden (Paper-Mode, kein API-Key)")
        except Exception as e:
            print(f"⚠️ Marktdaten-Fehler: {e}")
            self.data_client = None

    # ──────────────────────────────────────────────────────────
    # ABSTURZ-WIEDERHERSTELLUNG
    # ──────────────────────────────────────────────────────────
    def _restore_ui_stats(self):
        """Stellt gespeicherte Werte nach Neustart/Absturz wieder her."""
        prof_color = CLR_GREEN if self.session_profit >= 0 else CLR_RED
        self.ui(self.card_profit, text=f"{self.session_profit:,.2f} $", text_color=prof_color)
        self.ui(self.card_daily_loss, text=f"{self.daily_loss:,.2f} $",
                text_color=CLR_RED if self.daily_loss > 0 else "#888")
        try:
            bal  = self.exchange.fetch_balance()
            usdc = bal['total'].get('USDC', 0.0)
            self.ui(self.card_bal, text=f"{usdc:,.2f} USDC")
        except Exception:
            pass
        if self.session_profit != 0 or self.daily_loss != 0:
            self.add_log(f"♻️ Wiederhergestellt: Gewinn={self.session_profit:+.2f}$ | Verlust heute={self.daily_loss:.2f}$")

    # ──────────────────────────────────────────────────────────
    # PREIS-TICKER
    # ──────────────────────────────────────────────────────────
    def _price_ticker(self):
        while True:
            if self.data_client:
                try:
                    for i, coin in enumerate(COINS):
                        ticker = self.data_client.fetch_ticker(coin)
                        price  = ticker['last']
                        self.price_cache[coin] = price
                        self.ui(getattr(self, f"price_{i}"), text=f"{price:,.2f} $")
                except Exception:
                    pass
            time.sleep(1)

    # ══════════════════════════════════════════════════════════
    # UI AUFBAU
    # ══════════════════════════════════════════════════════════
    def setup_ui(self):
        # HEADER
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(pady=8, padx=30, fill="x")
        ctk.CTkLabel(header, text="⚡ SVEN'S IMPERIUM – 3 COINS PAPER",
                     font=("Bahnschrift", 28, "bold"), text_color=CLR_ACCENT).pack(side="left")
        ctk.CTkLabel(header, text="BTC · ETH · SOL  |  CVD · VWAP · StochRSI · Whale/Swing/Scalping",
                     font=("Arial", 11), text_color="#555").pack(side="left", padx=12)
        ctk.CTkLabel(header, text="📄 PAPER TRADING – Kein echtes Geld",
                     font=("Arial", 11, "bold"), text_color=CLR_BLUE).pack(side="right", padx=10)

        # STAT CARDS
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=30, pady=4)
        self.card_bal        = self.stat_card(stats, "PAPER SALDO",    "–",       "#fff")
        self.card_profit     = self.stat_card(stats, "SESSION GEWINN", "0.00 $",  CLR_GREEN)
        self.card_slots      = self.stat_card(stats, "OFFENE TRADES",  "0 / 3",   CLR_ACCENT)
        self.card_daily_loss = self.stat_card(stats, "TAGESVERLUST",   "0.00 $",  CLR_RED)
        self.card_cvd        = self.stat_card(stats, "CVD SIGNAL",     "–",       CLR_BLUE)
        self.card_strategy   = self.stat_card(stats, "STRATEGIE",      "WHALE",   CLR_PURPLE)

        # TABS
        self.tabs = ctk.CTkTabview(
            self, fg_color=CLR_BG,
            segmented_button_fg_color=CLR_CARD,
            segmented_button_selected_color=CLR_ACCENT,
            segmented_button_selected_hover_color="#d4ac0d",
            segmented_button_unselected_color=CLR_CARD,
            segmented_button_unselected_hover_color="#222",
            text_color="#000", text_color_disabled="#888"
        )
        self.tabs.pack(expand=True, fill="both", padx=20, pady=4)
        for tab in ["📈  COCKPIT", "🧠  STRATEGIEN", "📊  MULTI-CHARTS",
                    "⚡  SCHNELLHANDEL", "📋  TRADE-VIEWER", "💰  ANALYSE"]:
            self.tabs.add(tab)

        self._build_cockpit_tab(self.tabs.tab("📈  COCKPIT"))
        self._build_strategy_tab(self.tabs.tab("🧠  STRATEGIEN"))
        self._build_multi_charts_tab(self.tabs.tab("📊  MULTI-CHARTS"))
        self._build_schnellhandel_tab(self.tabs.tab("⚡  SCHNELLHANDEL"))
        self._build_trade_viewer_tab(self.tabs.tab("📋  TRADE-VIEWER"))
        self._build_analyse_tab(self.tabs.tab("💰  ANALYSE"))

        # LOG
        self.log = ctk.CTkTextbox(self, height=95, fg_color="#000",
                                  text_color=CLR_GREEN, font=("Consolas", 11))
        self.log.pack(fill="x", padx=30, pady=(0, 8))
        self.tabs.configure(command=self._on_tab_change)

    # ─────────────────────────────────────────────
    # TAB 1: COCKPIT
    # ─────────────────────────────────────────────
    def _build_cockpit_tab(self, parent):
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(expand=True, fill="both")
        grid.grid_columnconfigure((0, 1, 2), weight=1)
        grid.grid_rowconfigure(0, weight=1)

        for i, coin in enumerate(COINS):
            card = ctk.CTkFrame(grid, fg_color=CLR_CARD, corner_radius=15)
            card.grid(row=0, column=i, padx=8, pady=5, sticky="nsew")
            ctk.CTkLabel(card, text=coin, font=("Arial", 17, "bold"), text_color="#fff").pack(pady=5)

            setattr(self, f"price_{i}", ctk.CTkLabel(card, text="–",
                    font=("Arial", 22, "bold"), text_color=CLR_ACCENT))
            getattr(self, f"price_{i}").pack()

            setattr(self, f"profit_{i}", ctk.CTkLabel(card, text="Warte...",
                    font=("Arial", 12), text_color="#888"))
            getattr(self, f"profit_{i}").pack(pady=1)

            setattr(self, f"signal_{i}", ctk.CTkLabel(card, text="",
                    font=("Arial", 10), text_color=CLR_BLUE))
            getattr(self, f"signal_{i}").pack(pady=1)

            setattr(self, f"cvd_{i}", ctk.CTkLabel(card, text="CVD: –",
                    font=("Arial", 10), text_color=CLR_PURPLE))
            getattr(self, f"cvd_{i}").pack(pady=1)

            fig, ax = plt.subplots(figsize=(4, 2.0), dpi=85)
            fig.patch.set_facecolor(CLR_CARD)
            ax.set_facecolor(CLR_CARD); ax.set_axis_off()
            canvas = FigureCanvasTkAgg(fig, master=card)
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
            self.chart_figs[coin]     = fig
            self.chart_axes[coin]     = ax
            self.chart_canvases[coin] = canvas

        # KONTROLL-PANEL
        ctrl = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=15)
        ctrl.pack(fill="x", pady=(5, 0))

        r1 = ctk.CTkFrame(ctrl, fg_color="transparent"); r1.pack(fill="x", padx=15, pady=(10, 4))
        self._add_ctrl(r1, "TRADES:", self.trade_count, 45)
        self._add_check_entry(r1, "STOP-LOSS %",   self.sl_active,         self.sl_val,         55)
        self._add_check_entry(r1, "TAKE-PROFIT %", self.tp_active,         self.tp_val,         55)
        self._add_check_entry(r1, "TRAILING %",    self.trail_active,      self.trail_val,      55)
        self._add_check_entry(r1, "MAX VERLUST $", self.daily_loss_active, self.daily_loss_val, 65)

        r2 = ctk.CTkFrame(ctrl, fg_color="transparent"); r2.pack(fill="x", padx=15, pady=(4, 4))
        CB = dict(text_color="#fff", checkmark_color="#000", fg_color=CLR_ACCENT, hover_color=CLR_GREEN)
        EN = dict(fg_color="#1e1e22", text_color="#fff", border_color="#333")
        ctk.CTkCheckBox(r2, text="RSI KAUF <", variable=self.rsi_active, **CB).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(r2, textvariable=self.rsi_buy_val,  width=40, **EN).pack(side="left")
        ctk.CTkLabel(r2, text="VERKAUF >", text_color="#aaa").pack(side="left", padx=(5, 2))
        ctk.CTkEntry(r2, textvariable=self.rsi_sell_val, width=40, **EN).pack(side="left")
        ctk.CTkCheckBox(r2, text="EMA 50",  variable=self.ema_active,  **CB).pack(side="left", padx=8)
        ctk.CTkCheckBox(r2, text="MACD",    variable=self.macd_active, **CB).pack(side="left", padx=5)
        ctk.CTkCheckBox(r2, text="CVD",     variable=self.cvd_active,  **CB).pack(side="left", padx=5)
        ctk.CTkCheckBox(r2, text="VWAP",    variable=self.vwap_active, **CB).pack(side="left", padx=5)
        ctk.CTkLabel(r2, text="MIN SCORE:", text_color="#aaa").pack(side="left", padx=(10, 2))
        ctk.CTkEntry(r2, textvariable=self.min_score_var, width=40, **EN).pack(side="left")
        ctk.CTkLabel(r2, text="TIMEFRAME:", text_color="#aaa").pack(side="left", padx=(10, 2))
        ctk.CTkOptionMenu(r2, values=["1m", "3m", "5m", "15m", "1h"],
                          variable=self.timeframe_var,
                          fg_color=CLR_CARD, button_color="#333",
                          text_color="#fff", width=70).pack(side="left", padx=3)

        r3 = ctk.CTkFrame(ctrl, fg_color="transparent"); r3.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(r3, text="POS.SIZE %:", text_color=CLR_ACCENT,
                     font=("Arial", 12, "bold")).pack(side="left", padx=(0, 3))
        ctk.CTkEntry(r3, textvariable=self.pos_size_pct, width=45, **EN).pack(side="left")

        self.btn_run = ctk.CTkButton(ctrl, text="▶  STARTEN", fg_color=CLR_GREEN,
                                     text_color="#000", font=("Arial", 16, "bold"),
                                     width=145, command=self.toggle)
        self.btn_run.pack(side="right", padx=20, pady=10)

        ctk.CTkButton(ctrl, text="♻️ PAPER RESET",
                      fg_color="#1a1a1a", text_color=CLR_ORANGE,
                      font=("Arial", 12), width=160,
                      command=self._reset_paper).pack(side="right", padx=5, pady=10)

    def _reset_paper(self):
        """Setzt Paper-Balance auf 10.000 USDC zurück."""
        if self.is_running:
            self.add_log("⚠️ Bot zuerst stoppen!"); return
        self.exchange.reset_balance(10000.0)
        for coin in COINS:
            self.active_trades[coin]  = False
            self.entry_prices[coin]   = 0.0
            self.highest_prices[coin] = 0.0
        self.add_log("♻️ Paper-Balance zurückgesetzt auf 10.000 USDC")
        self.ui(self.card_bal, text="10000.00 USDC")

    # ─────────────────────────────────────────────
    # TAB 2: STRATEGIEN
    # ─────────────────────────────────────────────
    def _build_strategy_tab(self, parent):
        ctk.CTkLabel(parent, text="🧠 HANDELSSTRATEGIEN – Wähle deinen Stil",
                     font=("Arial", 20, "bold"), text_color=CLR_ACCENT).pack(pady=(15, 5))
        ctk.CTkLabel(parent,
                     text="Jede Strategie optimiert Indikatoren, Stop-Loss und Timeframe automatisch",
                     font=("Arial", 12), text_color="#666").pack(pady=(0, 15))

        cards_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20)
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.strategy_btns = {}
        for col, (name, cfg) in enumerate(STRATEGIES.items()):
            card = ctk.CTkFrame(cards_frame, fg_color=CLR_CARD, corner_radius=15)
            card.grid(row=0, column=col, padx=10, pady=5, sticky="nsew")
            ctk.CTkLabel(card, text=name, font=("Arial", 16, "bold"),
                         text_color=CLR_ACCENT).pack(pady=(12, 5))
            ctk.CTkLabel(card, text=cfg["description"], font=("Arial", 11),
                         text_color="#aaa", wraplength=300, justify="left").pack(padx=15, pady=5)

            params = ctk.CTkFrame(card, fg_color="#0d0d10", corner_radius=8)
            params.pack(fill="x", padx=12, pady=8)
            for label, val, color in [
                ("RSI Kauf:",    f"< {cfg['rsi_buy']}",  CLR_GREEN),
                ("RSI Verkauf:", f"> {cfg['rsi_sell']}", CLR_RED),
                ("Stop-Loss:",   f"{cfg['sl']}%",        CLR_RED),
                ("Take-Profit:", f"{cfg['tp']}%",        CLR_GREEN),
                ("Trailing:",    f"{cfg['trail']}%",     CLR_BLUE),
                ("Timeframe:",   cfg['timeframe'],        CLR_ACCENT),
                ("Min. Score:",  f"{cfg['min_score']}/10",CLR_PURPLE),
                ("Logik:",       cfg['logic'],            "#777"),
            ]:
                row = ctk.CTkFrame(params, fg_color="transparent"); row.pack(fill="x", padx=8, pady=1)
                ctk.CTkLabel(row, text=label, font=("Arial", 10), text_color="#666",
                             width=90, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=val,   font=("Arial", 10, "bold"),
                             text_color=color).pack(side="left")

            chips = ctk.CTkFrame(card, fg_color="transparent"); chips.pack(pady=5)
            for ind, active in [("MACD", cfg['macd']), ("EMA",  cfg['ema']),
                                  ("CVD",  cfg['cvd']),  ("VWAP", cfg['vwap']),
                                  ("RSI",  True),        ("StochRSI", True)]:
                bg = CLR_GREEN if active else "#2a2a2a"
                tc = "#000"    if active else "#555"
                ctk.CTkLabel(chips, text=f" {ind} ", font=("Arial", 10, "bold"),
                             fg_color=bg, text_color=tc, corner_radius=6,
                             width=55, height=22).pack(side="left", padx=3)

            btn = ctk.CTkButton(card, text="✅ DIESE STRATEGIE LADEN",
                                fg_color=CLR_PURPLE, text_color="#fff",
                                font=("Arial", 12, "bold"), width=200,
                                command=lambda n=name, c=cfg: self._load_strategy(n, c))
            btn.pack(pady=(8, 15))
            self.strategy_btns[name] = btn

        # Indikator-Erklärung
        explain = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=12)
        explain.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(explain, text="📖 INDIKATOR ERKLÄRUNG – Warum welcher Indikator?",
                     font=("Arial", 13, "bold"), text_color=CLR_ACCENT).pack(pady=(10, 5), padx=15, anchor="w")
        exp_grid = ctk.CTkFrame(explain, fg_color="transparent")
        exp_grid.pack(fill="x", padx=15, pady=(0, 10))
        for nm, clr, txt in [
            ("MACD (Pflicht)", CLR_GREEN,  "Zeigt ob ein neuer Aufwärtstrend beginnt. MACD > Signal = Kaufsignal. Wichtigster Indikator!"),
            ("RSI",            CLR_BLUE,   "0-100 Skala. Unter 45 = überverkauft = günstig kaufen. Über 70 = überkauft = verkaufen."),
            ("EMA 50",         CLR_ORANGE, "Trendlinie. Kurs über EMA50 = Aufwärtstrend bestätigt. Kurs darunter = Abwärtstrend."),
            ("CVD",            CLR_PURPLE, "Kaufdruck-Messer. Steigt CVD? Mehr Käufer als Verkäufer = stark bullisch."),
            ("VWAP",           CLR_ACCENT, "Fairer Preis. Kurs über VWAP = Käufer zahlen Aufpreis = Bullisch."),
            ("StochRSI",       "#aaa",     "Schnellere RSI-Version. Unter 20 = stark überverkauft = Wendesignal!"),
            ("Volumen",        CLR_GREEN,  "Bestätigt jedes Signal. Kauf ohne hohes Volumen = schwaches Signal."),
            ("NICHT empfohlen:", CLR_RED,  "Bollinger Bands + ADX allein = redundant. Zu viele Filter = Bot kauft nie!"),
        ]:
            row = ctk.CTkFrame(exp_grid, fg_color="transparent"); row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"• {nm}", font=("Arial", 11, "bold"),
                         text_color=clr, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=txt, font=("Arial", 10),
                         text_color="#888", anchor="w").pack(side="left", padx=5)

    def _load_strategy(self, name: str, cfg: dict):
        self.current_strategy = name
        self.rsi_buy_val.set(str(cfg['rsi_buy']))
        self.rsi_sell_val.set(str(cfg['rsi_sell']))
        self.sl_val.set(str(cfg['sl']))
        self.tp_val.set(str(cfg['tp']))
        self.trail_val.set(str(cfg['trail']))
        self.pos_size_pct.set(str(cfg['pos_size']))
        self.min_score_var.set(str(cfg['min_score']))
        self.timeframe_var.set(cfg['timeframe'])
        self.macd_active.set(cfg['macd'])
        self.ema_active.set(cfg['ema'])
        self.cvd_active.set(cfg['cvd'])
        self.vwap_active.set(cfg['vwap'])
        short = name.split(" ")[1].replace("(Empfohlen)", "").strip()
        self.ui(self.card_strategy, text=short)
        self.add_log(f"✅ Strategie geladen: {name}")
        self.add_log(f"   RSI: <{cfg['rsi_buy']} Kauf | >{cfg['rsi_sell']} Verkauf | SL:{cfg['sl']}% | TF:{cfg['timeframe']}")

    # ─────────────────────────────────────────────
    # TAB 3: MULTI-CHARTS
    # ─────────────────────────────────────────────
    def _build_multi_charts_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=10)
        top.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(top, text="📊 MULTI-CHART ANSICHT – 3 Coins × 2 Timeframes",
                     font=("Arial", 13, "bold"), text_color=CLR_ACCENT).pack(side="left", padx=15, pady=8)
        ctk.CTkButton(top, text="🔄 AKTUALISIEREN", fg_color=CLR_BLUE, text_color="#fff",
                      font=("Arial", 12), width=180,
                      command=self._refresh_multi_charts).pack(side="left", padx=10)
        self.mc_auto_btn = ctk.CTkButton(top, text="▶ AUTO 30s", fg_color=CLR_GREEN,
                                          text_color="#000", font=("Arial", 11, "bold"), width=110,
                                          command=self._toggle_mc_auto)
        self.mc_auto_btn.pack(side="right", padx=15)

        chart_frame = ctk.CTkFrame(parent, fg_color="transparent")
        chart_frame.pack(expand=True, fill="both", padx=10, pady=5)
        chart_frame.grid_columnconfigure((0, 1, 2), weight=1)
        chart_frame.grid_rowconfigure((0, 1), weight=1)

        self._mc_auto_running = False
        for col, coin in enumerate(COINS):
            for row, tf in enumerate(["5m", "1h"]):
                key  = f"{coin}_{tf}"
                card = ctk.CTkFrame(chart_frame, fg_color=CLR_CARD, corner_radius=10)
                card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                ctk.CTkLabel(card, text=f"{coin}  [{tf}]",
                             font=("Arial", 12, "bold"), text_color=CLR_ACCENT).pack(pady=(5, 0))
                fig, axes = plt.subplots(3, 1, figsize=(4, 3.0), dpi=82,
                                          gridspec_kw={'height_ratios': [3, 1, 1]})
                fig.patch.set_facecolor(CLR_CARD)
                fig.subplots_adjust(hspace=0.04, left=0.05, right=0.98, top=0.97, bottom=0.05)
                for ax in axes:
                    ax.set_facecolor(CLR_CARD)
                    ax.tick_params(colors='#444', labelsize=6)
                    for spine in ax.spines.values(): spine.set_color('#222')
                canvas = FigureCanvasTkAgg(fig, master=card)
                canvas.get_tk_widget().pack(fill="both", expand=True, padx=3, pady=3)
                self.mc_axes[key]     = axes
                self.mc_canvases[key] = (fig, canvas)

        self._refresh_multi_charts()

    def _toggle_mc_auto(self):
        self._mc_auto_running = not self._mc_auto_running
        if self._mc_auto_running:
            self.mc_auto_btn.configure(text="⏹ AUTO STOP", fg_color=CLR_RED)
            def _loop():
                while self._mc_auto_running:
                    self._refresh_multi_charts(); time.sleep(30)
            threading.Thread(target=_loop, daemon=True).start()
        else:
            self.mc_auto_btn.configure(text="▶ AUTO 30s", fg_color=CLR_GREEN)

    def _refresh_multi_charts(self):
        if self.data_client is None: return
        def _run():
            for coin in COINS:
                for tf in ["5m", "1h"]:
                    try:
                        bars = self.data_client.fetch_ohlcv(coin, tf, limit=80)
                        df   = pd.DataFrame(bars, columns=['Date','Open','High','Low','Close','Volume'])
                        df['Date'] = pd.to_datetime(df['Date'], unit='ms')
                        df.set_index('Date', inplace=True)
                        df = calc_all_indicators(df)
                        self._draw_multi_chart(coin, tf, df)
                    except Exception as e:
                        print(f"Multi-Chart {coin} {tf}: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _draw_multi_chart(self, coin, tf, df):
        def _draw():
            key = f"{coin}_{tf}"
            axes = self.mc_axes.get(key)
            fc   = self.mc_canvases.get(key)
            if axes is None or fc is None: return
            fig, canvas = fc
            ax_p, ax_c, ax_r = axes
            ax_p.clear(); ax_c.clear(); ax_r.clear()
            n = len(df); idx = range(n)
            closes, opens = df['Close'].values, df['Open'].values
            highs,  lows  = df['High'].values,  df['Low'].values
            for j in idx:
                col = CLR_GREEN if closes[j] >= opens[j] else CLR_RED
                ax_p.plot([j, j], [lows[j], highs[j]], color=col, linewidth=0.7)
                ax_p.bar(j, abs(closes[j]-opens[j]), bottom=min(closes[j], opens[j]),
                         color=col, width=0.6, alpha=0.9)
            for k2, col, ls in [('EMA20', CLR_BLUE, '-'), ('EMA50', CLR_ORANGE, '-'), ('VWAP', CLR_PURPLE, '--')]:
                if k2 in df.columns:
                    ax_p.plot(idx, df[k2].values, color=col, linewidth=0.8, linestyle=ls, alpha=0.75)
            for ax in [ax_p, ax_c, ax_r]:
                ax.set_facecolor(CLR_CARD)
                ax.tick_params(colors='#444', labelsize=5)
                for sp in ax.spines.values(): sp.set_color('#222')
                ax.set_xlim(0, n)
            ax_p.set_xticklabels([])
            if 'CVD' in df.columns:
                cvd = df['CVD'].values
                ax_c.bar(idx, cvd, color=[CLR_GREEN if c > 0 else CLR_RED for c in cvd], alpha=0.7, width=0.8)
                ax_c.axhline(0, color='#444', linewidth=0.5)
                ax_c.set_ylabel("CVD", color='#555', fontsize=5)
                ax_c.set_xticklabels([])
            if 'RSI' in df.columns:
                rsi = df['RSI'].values
                ax_r.plot(idx, rsi, color=CLR_BLUE, linewidth=1.0)
                ax_r.axhline(70, color=CLR_RED,   linewidth=0.6, linestyle='--', alpha=0.7)
                ax_r.axhline(30, color=CLR_GREEN, linewidth=0.6, linestyle='--', alpha=0.7)
                ax_r.fill_between(idx, rsi, 70, where=[r > 70 for r in rsi], color=CLR_RED,   alpha=0.2)
                ax_r.fill_between(idx, rsi, 30, where=[r < 30 for r in rsi], color=CLR_GREEN, alpha=0.2)
                ax_r.set_ylim(0, 100)
                ax_r.set_ylabel("RSI", color='#555', fontsize=5)
            fig.canvas.draw_idle()
        self.after(0, _draw)

    # ─────────────────────────────────────────────
    # TAB 4: SCHNELLHANDEL (Paper-Modus)
    # ─────────────────────────────────────────────
    def _build_schnellhandel_tab(self, parent):
        ctk.CTkLabel(parent, text="⚡ PAPER SCHNELLHANDEL – Manuell kaufen & verkaufen",
                     font=("Arial", 18, "bold"), text_color=CLR_ACCENT).pack(pady=(15, 5))
        ctk.CTkLabel(parent, text="Simulierte Trades · Paper-Balance · Kein echtes Geld",
                     font=("Arial", 11), text_color=CLR_BLUE).pack(pady=(0, 15))

        sel = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=15)
        sel.pack(padx=50, pady=5, fill="x")

        row1 = ctk.CTkFrame(sel, fg_color="transparent"); row1.pack(pady=12, padx=20)
        ctk.CTkLabel(row1, text="COIN:", text_color="#fff",
                     font=("Arial", 14, "bold")).pack(side="left", padx=8)
        ctk.CTkOptionMenu(row1, values=COINS, variable=self.manual_coin_var,
                          fg_color=CLR_CARD, button_color="#333", text_color="#fff",
                          width=160, font=("Arial", 13)).pack(side="left", padx=8)
        ctk.CTkLabel(row1, text="BETRAG (USDC):", text_color="#fff",
                     font=("Arial", 14, "bold")).pack(side="left", padx=15)
        ctk.CTkEntry(row1, textvariable=self.manual_amount_var, width=100,
                     fg_color="#1e1e22", text_color="#fff", border_color="#333",
                     font=("Arial", 15)).pack(side="left", padx=8)

        schnell = ctk.CTkFrame(sel, fg_color="transparent"); schnell.pack(pady=(0, 8))
        ctk.CTkLabel(schnell, text="Schnell:", text_color="#777",
                     font=("Arial", 11)).pack(side="left", padx=8)
        for amt in [10, 20, 50, 100, 200, 500]:
            ctk.CTkButton(schnell, text=f"{amt}$", width=60, height=26,
                          fg_color="#1e1e22", text_color="#ccc", hover_color="#333",
                          command=lambda a=amt: self.manual_amount_var.set(str(a))).pack(side="left", padx=2)

        self.sh_price_lbl = ctk.CTkLabel(sel, text="Preis: –",
                                          font=("Arial", 13), text_color=CLR_ACCENT)
        self.sh_price_lbl.pack(pady=3)
        self.sh_balance_lbl = ctk.CTkLabel(sel, text="Paper Saldo: –",
                                            font=("Arial", 11), text_color="#888")
        self.sh_balance_lbl.pack(pady=(0, 8))

        btns = ctk.CTkFrame(parent, fg_color="transparent"); btns.pack(pady=15)
        ctk.CTkButton(btns, text="🟢  KAUFEN",
                      font=("Arial", 20, "bold"), fg_color=CLR_GREEN, text_color="#000",
                      width=200, height=65, corner_radius=15,
                      command=self._manual_buy).pack(side="left", padx=15)
        ctk.CTkButton(btns, text="🔴  VERKAUFEN",
                      font=("Arial", 20, "bold"), fg_color=CLR_RED, text_color="#fff",
                      width=200, height=65, corner_radius=15,
                      command=self._manual_sell).pack(side="left", padx=15)
        ctk.CTkButton(btns, text="💰  ALLE VERKAUFEN",
                      font=("Arial", 16, "bold"), fg_color="#6b0000", text_color="#fff",
                      width=200, height=65, corner_radius=15,
                      command=self._manual_sell_all).pack(side="left", padx=15)

        ctk.CTkButton(parent, text="🔄 PREISE AKTUALISIEREN", fg_color="#222",
                      text_color="#fff", font=("Arial", 11), width=200,
                      command=self._update_sh_info).pack(pady=5)

        ctk.CTkLabel(parent, text="LOG:", font=("Arial", 10),
                     text_color="#555").pack(anchor="w", padx=50, pady=(8, 2))
        self.sh_log = ctk.CTkTextbox(parent, height=140, fg_color="#0a0a0a",
                                     text_color=CLR_GREEN, font=("Consolas", 11))
        self.sh_log.pack(fill="x", padx=50, pady=(0, 10))

        self.manual_coin_var.trace_add("write", lambda *_: self._update_sh_info())
        self._update_sh_info()

    def _update_sh_info(self):
        def _run():
            if self.data_client is None: return
            try:
                coin  = self.manual_coin_var.get()
                price = self.data_client.fetch_ticker(coin)['last']
                bal   = self.exchange.fetch_balance()
                usdc  = bal['total'].get('USDC', 0.0)
                asset = coin.split('/')[0]
                qty   = bal['total'].get(asset, 0.0)
                self.ui(self.sh_price_lbl, text=f"Preis: {price:,.2f} $")
                self.ui(self.sh_balance_lbl,
                        text=f"📄 Paper USDC: {usdc:.2f}  |  🪙 {asset}: {qty:.6f} ({qty*price:.2f} USDC)")
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _manual_buy(self):
        def _run():
            if self.data_client is None:
                self._sh_log("❌ Kein Marktdaten-Client"); return
            try:
                coin   = self.manual_coin_var.get()
                amount = float(self.manual_amount_var.get())
                if amount < 11:
                    self._sh_log("❌ Mindestbetrag: 11 USDC"); return
                self.exchange.create_market_buy_order(coin, None, {'quoteOrderQty': amount * 0.98})
                price = self.data_client.fetch_ticker(coin)['last']
                self._sh_log(f"✅ PAPER KAUF: {coin} | {amount:.2f} USDC @ {price:,.2f}$")
                self.cache.add({"type": "MANUAL_BUY", "coin": coin, "price": price,
                                "amount": amount, "time": datetime.now(timezone.utc).isoformat()})
                self._update_sh_info()
            except Exception as e:
                self._sh_log(f"❌ Kauf-Fehler: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _manual_sell(self):
        def _run():
            if self.data_client is None:
                self._sh_log("❌ Kein Marktdaten-Client"); return
            try:
                coin  = self.manual_coin_var.get()
                asset = coin.split('/')[0]
                bal   = self.exchange.fetch_balance()
                qty   = bal['free'].get(asset, 0.0)
                price = self.data_client.fetch_ticker(coin)['last']
                if qty * price < 11:
                    self._sh_log(f"❌ Zu wenig {asset}"); return
                self.exchange.create_market_sell_order(coin, qty)
                self._sh_log(f"✅ PAPER VERKAUF: {qty:.6f} {asset} @ {price:,.2f}$")
                self.cache.add({"type": "MANUAL_SELL", "coin": coin, "price": price,
                                "qty": qty, "time": datetime.now(timezone.utc).isoformat()})
                self._update_sh_info()
            except Exception as e:
                self._sh_log(f"❌ Verkauf-Fehler: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _manual_sell_all(self):
        def _run():
            if self.data_client is None:
                self._sh_log("❌ Kein Marktdaten-Client"); return
            try:
                bal  = self.exchange.fetch_balance()
                sold = 0
                for coin in COINS:
                    asset = coin.split('/')[0]
                    qty   = bal['free'].get(asset, 0.0)
                    price = self.data_client.fetch_ticker(coin)['last']
                    if qty * price >= 11:
                        self.exchange.create_market_sell_order(coin, qty)
                        self._sh_log(f"✅ {asset}: {qty:.6f} @ {price:,.2f}$ verkauft")
                        self.active_trades[coin] = False
                        sold += 1
                self._sh_log(f"📦 {sold} Coin(s) verkauft")
                self._update_sh_info()
            except Exception as e:
                self._sh_log(f"❌ Fehler: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _sh_log(self, msg):
        ts = time.strftime('%H:%M:%S')
        def _up():
            self.sh_log.configure(state="normal")
            self.sh_log.insert("end", f"[{ts}] {msg}\n")
            self.sh_log.configure(state="disabled")
            self.sh_log.see("end")
        self.after(0, _up)

    # ─────────────────────────────────────────────
    # TAB 5: TRADE-VIEWER
    # ─────────────────────────────────────────────
    def _build_trade_viewer_tab(self, parent):
        stat_row = ctk.CTkFrame(parent, fg_color="transparent")
        stat_row.pack(fill="x", pady=(8, 4), padx=10)
        self.tv_total_trades = self._tv_stat(stat_row, "GESAMT",      "0",       "#fff")
        self.tv_wins         = self._tv_stat(stat_row, "GEWINNER",    "0",       CLR_GREEN)
        self.tv_losses       = self._tv_stat(stat_row, "VERLIERER",   "0",       CLR_RED)
        self.tv_winrate      = self._tv_stat(stat_row, "WINRATE",     "0 %",     CLR_ACCENT)
        self.tv_total_pnl    = self._tv_stat(stat_row, "GESAMT P&L",  "0.00 $",  CLR_GREEN)
        self.tv_best         = self._tv_stat(stat_row, "BESTER",      "0.00 $",  CLR_GREEN)
        self.tv_worst        = self._tv_stat(stat_row, "SCHLECHTEST", "0.00 $",  CLR_RED)

        fr = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=10)
        fr.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(fr, text="FILTER:", text_color="#aaa").pack(side="left", padx=10)
        self.tv_filter_coin = ctk.CTkOptionMenu(fr, values=["Alle"] + COINS,
                                                 fg_color=CLR_CARD, button_color="#333",
                                                 text_color="#fff", width=130,
                                                 command=lambda _: self.refresh_trade_viewer())
        self.tv_filter_coin.pack(side="left", padx=5, pady=6)
        self.tv_filter_type = ctk.CTkOptionMenu(fr, values=["Alle", "Nur Käufe", "Nur Verkäufe"],
                                                 fg_color=CLR_CARD, button_color="#333",
                                                 text_color="#fff", width=130,
                                                 command=lambda _: self.refresh_trade_viewer())
        self.tv_filter_type.pack(side="left", padx=5)
        ctk.CTkButton(fr, text="🔄", fg_color="#333", text_color="#fff", width=50,
                      command=self.refresh_trade_viewer).pack(side="left", padx=5)
        ctk.CTkButton(fr, text="🗑️ LEEREN", fg_color="#2a1010", text_color=CLR_RED,
                      font=("Arial", 11), width=110,
                      command=self.clear_trade_log).pack(side="left", padx=5)

        cols  = ["#", "ZEIT", "TYP", "COIN", "PREIS", "MENGE/USDC", "P&L", "GRUND"]
        col_w = [35,  145,    80,    110,    100,     120,           90,    220]
        hdr = ctk.CTkFrame(parent, fg_color="#1a1a1f", corner_radius=8)
        hdr.pack(fill="x", padx=10, pady=(4, 0))
        for c, w in zip(cols, col_w):
            ctk.CTkLabel(hdr, text=c, width=w, font=("Arial", 11, "bold"),
                         text_color=CLR_ACCENT, anchor="w").pack(side="left", padx=4, pady=5)

        self.tv_scroll = ctk.CTkScrollableFrame(parent, fg_color="#0d0d10", corner_radius=8)
        self.tv_scroll.pack(expand=True, fill="both", padx=10, pady=(0, 8))
        self.tv_rows_frame = self.tv_scroll

    def _tv_stat(self, parent, title, value, color):
        card = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=10)
        card.pack(side="left", expand=True, padx=4, fill="both")
        ctk.CTkLabel(card, text=title, font=("Arial", 9), text_color="#666").pack(pady=(5, 0))
        lbl = ctk.CTkLabel(card, text=value, font=("Arial", 18, "bold"), text_color=color)
        lbl.pack(pady=(2, 6))
        return lbl

    # ─────────────────────────────────────────────
    # TAB 6: ANALYSE
    # ─────────────────────────────────────────────
    def _build_analyse_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(top, text="💰 GEWINN & VERLUST ANALYSE",
                     font=("Arial", 18, "bold"), text_color=CLR_ACCENT).pack(side="left", padx=15)
        ctk.CTkButton(top, text="🔄 AKTUALISIEREN", fg_color=CLR_BLUE, text_color="#fff",
                      font=("Arial", 12), width=170, command=self._refresh_analyse).pack(side="left", padx=10)

        self.an_stat_row = ctk.CTkFrame(parent, fg_color="transparent")
        self.an_stat_row.pack(fill="x", padx=10, pady=5)
        self.an_total_pnl = self._tv_stat(self.an_stat_row, "GESAMT P&L",  "0.00 $", CLR_GREEN)
        self.an_trades    = self._tv_stat(self.an_stat_row, "TRADES",       "0",      "#fff")
        self.an_winrate   = self._tv_stat(self.an_stat_row, "GEWINNRATE",   "0 %",    CLR_ACCENT)
        self.an_avg_win   = self._tv_stat(self.an_stat_row, "Ø GEWINN",     "0.00 $", CLR_GREEN)
        self.an_avg_loss  = self._tv_stat(self.an_stat_row, "Ø VERLUST",    "0.00 $", CLR_RED)
        self.an_best      = self._tv_stat(self.an_stat_row, "BESTER TRADE", "0.00 $", CLR_GREEN)
        self.an_streak    = self._tv_stat(self.an_stat_row, "SERIE",        "0",      CLR_PURPLE)

        self.an_stat_row2 = ctk.CTkFrame(parent, fg_color="transparent")
        self.an_stat_row2.pack(fill="x", padx=10, pady=(0, 5))
        self.an_pf    = self._tv_stat(self.an_stat_row2, "PROFIT FACTOR", "–",      CLR_GREEN)
        self.an_dd    = self._tv_stat(self.an_stat_row2, "MAX DRAWDOWN",  "–",      CLR_RED)
        self.an_today = self._tv_stat(self.an_stat_row2, "HEUTE P&L",     "0.00 $", CLR_ACCENT)
        self.an_btc   = self._tv_stat(self.an_stat_row2, "BTC Winrate",   "– %",    CLR_ORANGE)
        self.an_eth   = self._tv_stat(self.an_stat_row2, "ETH Winrate",   "– %",    CLR_BLUE)
        self.an_sol   = self._tv_stat(self.an_stat_row2, "SOL Winrate",   "– %",    CLR_PURPLE)

        chart_frame = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=12)
        chart_frame.pack(expand=True, fill="both", padx=10, pady=5)
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4.5), dpi=85)
        fig.patch.set_facecolor(CLR_CARD)
        self.an_fig  = fig
        self.an_axes = (ax1, ax2, ax3)
        canvas = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        self.an_canvas = canvas
        self._refresh_analyse()

    def _refresh_analyse(self):
        stats      = self.cache.get_stats()
        pnls       = self.cache.get_pnl_series()
        cum_pnl    = self.cache.get_cumulative_pnl()
        hourly     = self.cache.get_hourly_pnl()
        coin_stats = self.cache.get_coin_stats()

        self.ui(self.an_total_pnl, text=f"{stats['total_pnl']:+.2f} $",
                text_color=CLR_GREEN if stats['total_pnl'] >= 0 else CLR_RED)
        self.ui(self.an_trades,  text=str(stats['sell_trades']))
        self.ui(self.an_winrate, text=f"{stats['winrate']:.1f} %",
                text_color=CLR_GREEN if stats['winrate'] >= 50 else CLR_RED)
        self.ui(self.an_avg_win,  text=f"+{stats['avg_win']:.2f} $")
        self.ui(self.an_avg_loss, text=f"{stats['avg_loss']:.2f} $")
        self.ui(self.an_best,     text=f"+{stats['best_trade']:.2f} $")
        self.ui(self.an_streak,   text=str(stats['best_streak']))
        self.ui(self.an_pf,    text=f"{stats['profit_factor']:.2f}",
                text_color=CLR_GREEN if stats['profit_factor'] > 1 else CLR_RED)
        self.ui(self.an_dd,    text=f"-{stats['max_drawdown']:.2f} $", text_color=CLR_RED)
        self.ui(self.an_today, text=f"{stats['today_pnl']:+.2f} $",
                text_color=CLR_GREEN if stats['today_pnl'] >= 0 else CLR_RED)
        for attr, coin in [('an_btc', 'BTC/USDC'), ('an_eth', 'ETH/USDC'), ('an_sol', 'SOL/USDC')]:
            cs = coin_stats.get(coin, {})
            wr = cs.get('winrate', 0)
            self.ui(getattr(self, attr), text=f"{wr:.0f} %",
                    text_color=CLR_GREEN if wr >= 50 else CLR_RED)

        def _draw():
            ax1, ax2, ax3 = self.an_axes
            ax1.clear(); ax2.clear(); ax3.clear()
            for ax in self.an_axes:
                ax.set_facecolor(CLR_CARD)
                ax.tick_params(colors='#666', labelsize=8)
                for sp in ax.spines.values(): sp.set_color('#333')

            if cum_pnl:
                ax1.plot(cum_pnl, color=CLR_GREEN, linewidth=2)
                ax1.fill_between(range(len(cum_pnl)), cum_pnl, 0,
                                  where=[p >= 0 for p in cum_pnl], color=CLR_GREEN, alpha=0.2)
                ax1.fill_between(range(len(cum_pnl)), cum_pnl, 0,
                                  where=[p < 0  for p in cum_pnl], color=CLR_RED,   alpha=0.2)
                ax1.axhline(0, color='#444', linewidth=0.8)
            ax1.set_title("KUMULATIVER P&L", color='#aaa', fontsize=10, pad=5)

            if pnls:
                ax2.bar(range(len(pnls)), pnls,
                        color=[CLR_GREEN if p > 0 else CLR_RED for p in pnls], alpha=0.8, width=0.6)
                ax2.axhline(0, color='#444', linewidth=0.8)
            ax2.set_title("P&L PRO TRADE", color='#aaa', fontsize=10, pad=5)

            if hourly:
                hours  = list(hourly.keys()); values = list(hourly.values())
                bars = ax3.bar(range(len(hours)), values,
                               color=[CLR_GREEN if v > 0 else CLR_RED for v in values],
                               alpha=0.85, width=0.7)
                ax3.axhline(0, color='#444', linewidth=0.8)
                ax3.set_xticks(range(len(hours)))
                ax3.set_xticklabels(hours, rotation=45, fontsize=6, color='#888')
                if values:
                    best_idx = values.index(max(values))
                    bars[best_idx].set_edgecolor(CLR_ACCENT)
                    bars[best_idx].set_linewidth(2)
            ax3.set_title("P&L NACH UHRZEIT  ⭐=Beste Stunde", color='#aaa', fontsize=10, pad=5)

            self.an_fig.tight_layout(pad=2.0)
            self.an_canvas.draw()
        self.after(0, _draw)

    # ══════════════════════════════════════════
    # TAB EVENT
    # ══════════════════════════════════════════
    def _on_tab_change(self):
        tab = self.tabs.get()
        if   "TRADE-VIEWER"  in tab: self.refresh_trade_viewer()
        elif "ANALYSE"       in tab: self._refresh_analyse()
        elif "MULTI-CHARTS"  in tab: self._refresh_multi_charts()
        elif "SCHNELLHANDEL" in tab: self._update_sh_info()

    # ══════════════════════════════════════════
    # UI HELPERS
    # ══════════════════════════════════════════
    def _add_ctrl(self, parent, label, var, w):
        ctk.CTkLabel(parent, text=label, text_color="#fff",
                     font=("Arial", 12, "bold")).pack(side="left", padx=(0, 3))
        ctk.CTkEntry(parent, textvariable=var, width=w,
                     fg_color="#1e1e22", text_color="#fff",
                     border_color="#333").pack(side="left", padx=(0, 10))

    def _add_check_entry(self, parent, label, boolvar, strvar, w):
        ctk.CTkCheckBox(parent, text=label, variable=boolvar, text_color="#fff",
                        checkmark_color="#000", fg_color=CLR_ACCENT,
                        hover_color=CLR_GREEN).pack(side="left", padx=(10, 2))
        ctk.CTkEntry(parent, textvariable=strvar, width=w,
                     fg_color="#1e1e22", text_color="#fff",
                     border_color="#333").pack(side="left", padx=(0, 5))

    def stat_card(self, master, title, value, color):
        card = ctk.CTkFrame(master, fg_color=CLR_CARD, corner_radius=12)
        card.pack(side="left", expand=True, padx=5, fill="both")
        ctk.CTkLabel(card, text=title, font=("Arial", 9), text_color="#777").pack(pady=(5, 0))
        lbl = ctk.CTkLabel(card, text=value, font=("Arial", 20, "bold"), text_color=color)
        lbl.pack(pady=5)
        return lbl

    def add_log(self, message):
        ts = time.strftime('%H:%M:%S')
        def _up():
            self.log.configure(state="normal")
            self.log.insert("end", f"[{ts}] {message}\n")
            self.log.configure(state="disabled")
            self.log.see("end")
        self.after(0, _up)

    def ui(self, widget, **kwargs):
        self.after(0, lambda: widget.configure(**kwargs))

    # ══════════════════════════════════════════
    # TRADE-VIEWER
    # ══════════════════════════════════════════
    def refresh_trade_viewer(self):
        for w in self.tv_rows_frame.winfo_children(): w.destroy()
        trades = self.cache.get_all()
        if not trades:
            ctk.CTkLabel(self.tv_rows_frame, text="Noch keine Trades.",
                         text_color="#555", font=("Arial", 14)).pack(pady=40)
            return
        cf = self.tv_filter_coin.get()
        tf = self.tv_filter_type.get()
        if cf != "Alle":
            trades = [t for t in trades if t.get("coin") == cf]
        if tf == "Nur Käufe":
            trades = [t for t in trades if "BUY" in t.get("type", "")]
        elif tf == "Nur Verkäufe":
            trades = [t for t in trades if "SELL" in t.get("type", "")]

        sells     = [t for t in trades if t.get("type") == "SELL"]
        pnls      = [t.get("pnl", 0) for t in sells]
        total_pnl = sum(pnls)
        wins      = [p for p in pnls if p > 0]
        losses    = [p for p in pnls if p <= 0]
        winrate   = len(wins) / len(sells) * 100 if sells else 0

        self.ui(self.tv_total_trades, text=str(len(trades)))
        self.ui(self.tv_wins,    text=str(len(wins)))
        self.ui(self.tv_losses,  text=str(len(losses)))
        self.ui(self.tv_winrate, text=f"{winrate:.1f} %",
                text_color=CLR_GREEN if winrate >= 50 else CLR_RED)
        self.ui(self.tv_total_pnl, text=f"{total_pnl:+.2f} $",
                text_color=CLR_GREEN if total_pnl >= 0 else CLR_RED)
        self.ui(self.tv_best,  text=f"{max(pnls, default=0):+.2f} $", text_color=CLR_GREEN)
        self.ui(self.tv_worst, text=f"{min(pnls, default=0):+.2f} $", text_color=CLR_RED)

        col_w = [35, 145, 80, 110, 100, 120, 90, 220]
        for idx, t in enumerate(reversed(trades)):
            tt    = t.get("type", "?")
            pnl   = t.get("pnl", None)
            ts    = str(t.get("time", ""))[:19].replace("T", " ")
            coin  = t.get("coin", "-")
            price = f"{t.get('price', 0):,.2f} $"
            qty_s = (f"{t.get('qty', 0):.5f}" if "SELL" in tt
                     else f"{t.get('amount', 0):.2f} USDC")
            pnl_s  = f"{pnl:+.2f} $" if pnl is not None else "-"
            reason = str(t.get("reason", t.get("signal", "-")))[:32]

            row_bg = "#111116" if idx % 2 == 0 else "#0f0f13"
            row = ctk.CTkFrame(self.tv_rows_frame, fg_color=row_bg, corner_radius=4)
            row.pack(fill="x", pady=1, padx=2)
            pc = (CLR_GREEN if pnl and pnl > 0 else CLR_RED) if pnl is not None else "#888"
            tc = CLR_GREEN if "BUY" in tt else CLR_RED
            for val, col, w in zip(
                [str(len(trades) - idx), ts, tt, coin, price, qty_s, pnl_s, reason],
                ["#777", "#ccc", tc, "#fff", CLR_ACCENT, "#ccc", pc, "#999"], col_w
            ):
                ctk.CTkLabel(row, text=val, width=w, font=("Consolas", 11),
                             text_color=col, anchor="w").pack(side="left", padx=4, pady=4)

    def clear_trade_log(self):
        self.cache.clear()
        self.add_log("🗑️ Trade-Log geleert (Backup erstellt).")
        self.refresh_trade_viewer()

    # ══════════════════════════════════════════
    # START / STOPP
    # ══════════════════════════════════════════
    def toggle(self):
        if self.data_client is None:
            self.add_log("❌ Kein Marktdaten-Client – Neustart nötig!"); return
        self.is_running = not self.is_running
        self.btn_run.configure(
            text="⏹  STOPP" if self.is_running else "▶  STARTEN",
            fg_color=CLR_RED if self.is_running else CLR_GREEN
        )
        if self.is_running:
            # Tagesverlust aus Cache (Absturz-Schutz!)
            self.daily_loss = self.cache.calc_daily_loss()
            threading.Thread(target=self.run, daemon=True).start()
        else:
            self.add_log("⏹️ Bot gestoppt.")
            send_telegram("⏹ 3-Coins Paper-Bot gestoppt.")

    # ══════════════════════════════════════════
    # HAUPTLOOP – 10 SEKUNDEN CHECK-INTERVALL
    # ══════════════════════════════════════════
    def run(self):
        tf = self.timeframe_var.get()
        self.add_log(f"🚀 Paper-Bot startet | Strategie: {self.current_strategy} | TF: {tf}")
        send_telegram(f"🚀 3-Coins Paper-Bot gestartet (BTC/ETH/SOL)\nStrategie: {self.current_strategy}")

        while self.is_running:
            try:
                # ── Daily Loss Guard ──────────────────────────
                if self.daily_loss_active.get():
                    max_loss = float(self.daily_loss_val.get())
                    if self.daily_loss >= max_loss:
                        self.add_log(f"🛡️ TAGESVERLUST-LIMIT ({max_loss:.0f}$) – Bot stoppt!")
                        send_telegram(f"⚠️ Tagesverlust {max_loss}$ erreicht! Bot gestoppt.")
                        self.is_running = False
                        self.after(0, lambda: self.btn_run.configure(
                            text="▶  STARTEN", fg_color=CLR_GREEN))
                        break

                bal  = self.exchange.fetch_balance()
                usdc = bal['total'].get('USDC', 0.0)
                self.ui(self.card_bal, text=f"{usdc:,.2f} USDC")
                self.ui(self.card_daily_loss, text=f"{self.daily_loss:,.2f} $",
                        text_color=CLR_RED if self.daily_loss > 0 else "#888")
                active_count = sum(1 for c in COINS if self.active_trades[c])
                self.ui(self.card_slots, text=f"{active_count} / {self.trade_count.get()}")

                pos_pct      = float(self.pos_size_pct.get()) / 100
                share        = usdc * pos_pct
                total_cvd_up = 0

                for i, coin in enumerate(COINS):
                    if not self.is_running: break
                    if self.data_client is None: continue
                    try:
                        bars = self.data_client.fetch_ohlcv(coin, tf, limit=120)
                        df   = pd.DataFrame(bars, columns=['Date','Open','High','Low','Close','Volume'])
                        df['Date'] = pd.to_datetime(df['Date'], unit='ms')
                        df.set_index('Date', inplace=True)
                        df = calc_all_indicators(df)
                        self.last_df[coin] = df

                        cvd_val  = df['CVD'].iloc[-1]
                        cvd_prev = df['CVD'].iloc[-5]
                        cvd_up   = cvd_val > cvd_prev
                        if cvd_up: total_cvd_up += 1
                        self.ui(getattr(self, f"cvd_{i}"),
                                text=f"CVD: {'▲' if cvd_up else '▼'} {cvd_val:+.0f}",
                                text_color=CLR_GREEN if cvd_up else CLR_RED)

                        price   = df['Close'].iloc[-1]
                        regime  = self._detect_market_regime(df)
                        a_share = self._adapt_position_size(share, regime)
                        self.check_logic(coin, df, price, a_share, i, bal, regime)

                        def draw_chart(coin=coin, df=df):
                            ax = self.chart_axes[coin]
                            ax.clear(); ax.set_axis_off()
                            try:
                                mpf.plot(df.tail(60), type='candle', ax=ax,
                                         style=mpf.make_mpf_style(
                                             base_mpl_style='dark_background',
                                             marketcolors=mpf.make_marketcolors(
                                                 up=CLR_GREEN, down=CLR_RED),
                                             facecolor=CLR_CARD))
                                self.chart_canvases[coin].draw()
                            except Exception:
                                pass
                        self.after(0, draw_chart)

                    except Exception as e:
                        self.add_log(f"Loop {coin}: {e}")

                sig = ("🔥 KAUFDRUCK" if total_cvd_up >= 2
                       else "⚖️ NEUTRAL" if total_cvd_up == 1 else "❄️ VERKAUFDRUCK")
                self.ui(self.card_cvd, text=sig,
                        text_color=CLR_GREEN if total_cvd_up >= 2
                        else (CLR_ACCENT if total_cvd_up == 1 else CLR_RED))

                time.sleep(10)

            except Exception as e:
                self.add_log(f"Fehler: {e}")
                time.sleep(10)

    # ══════════════════════════════════════════
    # MARKT-REGIME ERKENNUNG
    # ══════════════════════════════════════════
    def _detect_market_regime(self, df) -> str:
        try:
            ema20   = df['EMA20'].iloc[-1]
            ema50   = df['EMA50'].iloc[-1]
            adx     = df['ADX'].iloc[-1]   if 'ADX' in df.columns else 20
            atr     = df['ATR'].iloc[-1]   if 'ATR' in df.columns else 0
            price   = df['Close'].iloc[-1]
            atr_pct = (atr / price) * 100
            if   atr_pct > 3.0:                                return "VOLATIL"
            elif adx > 25 and ema20 > ema50 and price > ema20: return "TREND↑"
            elif adx > 25 and ema20 < ema50 and price < ema20: return "TREND↓"
            else:                                               return "SEITWÄRTS"
        except Exception:
            return "UNBEKANNT"

    def _adapt_position_size(self, base, regime):
        return base * {"TREND↑": 1.0, "SEITWÄRTS": 0.7,
                        "VOLATIL": 0.4, "TREND↓": 0.0,
                        "UNBEKANNT": 0.5}.get(regime, 0.5)

    def _calc_signal_score(self, rsi, stoch_rsi, macd_bull, ema_ok,
                            vol_high, cvd_bull, vwap_ok, regime) -> int:
        s = 0
        if macd_bull:            s += 3
        if rsi < 35:             s += 3
        elif rsi < 45:           s += 2
        if ema_ok:               s += 1
        if vol_high:             s += 1
        if cvd_bull:             s += 1
        if vwap_ok:              s += 1
        if stoch_rsi < 20:       s += 1
        if regime == "TREND↑":   s += 1
        if regime == "VOLATIL":  s -= 2
        if regime == "TREND↓":   s  = 0
        return max(0, min(10, s))

    # ══════════════════════════════════════════
    # KAUF/VERKAUF LOGIK
    # ══════════════════════════════════════════
    def check_logic(self, coin, df, price, share, idx, balance, regime="UNBEKANNT"):
        rsi       = df['RSI'].iloc[-1]       if 'RSI'       in df.columns else 50.0
        stoch_rsi = df['StochRSI'].iloc[-1]  if 'StochRSI'  in df.columns else 50.0
        ema       = df['EMA50'].iloc[-1]     if 'EMA50'     in df.columns else price
        vwap      = df['VWAP'].iloc[-1]      if 'VWAP'      in df.columns else price
        macd_bull = (df['MACD'].iloc[-1] > df['MACD_signal'].iloc[-1]) if 'MACD' in df.columns else True
        vol_high  = bool(df['Vol_high'].iloc[-1]) if 'Vol_high' in df.columns else False
        cvd_bull  = df['CVD'].iloc[-1] > df['CVD'].iloc[-5]  if 'CVD'  in df.columns else False
        ema_ok    = price > ema
        vwap_ok   = price > vwap

        score  = self._calc_signal_score(rsi, stoch_rsi, macd_bull, ema_ok,
                                         vol_high, cvd_bull, vwap_ok, regime)
        filled = "█" * score; empty = "░" * (10 - score)
        sc     = CLR_GREEN if score >= 7 else (CLR_ACCENT if score >= 4 else CLR_RED)

        def _upd(idx=idx):
            w = getattr(self, f"signal_{idx}")
            w.configure(
                text=(f"{regime}  ·  RSI:{rsi:.0f}  StRSI:{stoch_rsi:.0f}  "
                      f"MACD:{'▲' if macd_bull else '▼'}  VOL:{'🔥' if vol_high else '💤'}\n"
                      f"Signal: {filled}{empty} {score}/10"),
                text_color=sc)
        self.after(0, _upd)

        min_score = int(self.min_score_var.get())

        # ── VERKAUFEN ─────────────────────────────────────
        if self.active_trades[coin]:
            entry  = self.entry_prices[coin]
            p_diff = ((price / entry) - 1) * 100
            self.ui(getattr(self, f"profit_{idx}"),
                    text=f"Live: {p_diff:+.2f}%  |  Einstand: {entry:.2f}$",
                    text_color=CLR_GREEN if p_diff >= 0 else CLR_RED)

            if price > self.highest_prices[coin]:
                self.highest_prices[coin] = price

            sell_reason = None
            if self.sl_active.get()    and p_diff <= -float(self.sl_val.get()):
                sell_reason = f"🛑 STOP-LOSS {p_diff:.2f}%"
            if not sell_reason and self.tp_active.get() and p_diff >= float(self.tp_val.get()):
                sell_reason = f"🎯 TAKE-PROFIT +{p_diff:.2f}%"
            if not sell_reason and self.rsi_active.get() and rsi > float(self.rsi_sell_val.get()):
                sell_reason = f"📈 RSI OVERBOUGHT ({rsi:.0f})"
            if not sell_reason and not macd_bull and p_diff > 1.5:
                sell_reason = f"📉 MACD BEARISH +{p_diff:.2f}%"
            if not sell_reason and not cvd_bull and p_diff > 2.0:
                sell_reason = f"📉 CVD BEARISH +{p_diff:.2f}%"
            if not sell_reason and self.trail_active.get() and p_diff > 0.2:
                stop_p = self.highest_prices[coin] * (1 - float(self.trail_val.get()) / 100)
                if price <= stop_p:
                    sell_reason = f"💰 TRAILING STOP +{p_diff:.2f}%"
            if sell_reason:
                self._execute_sell(coin, price, idx, balance, sell_reason)

        # ── KAUFEN ────────────────────────────────────────
        else:
            self.ui(getattr(self, f"profit_{idx}"), text="Warte auf Signal", text_color="#555")
            if sum(1 for c in COINS if self.active_trades[c]) >= int(self.trade_count.get()):
                return
            if self.daily_loss_active.get() and self.daily_loss >= float(self.daily_loss_val.get()):
                return
            if regime == "TREND↓" or share < 11.0:
                return
            if self.macd_active.get() and not macd_bull:
                return

            rsi_ok   = rsi < float(self.rsi_buy_val.get())
            n_ok     = sum([rsi_ok, ema_ok, vol_high, cvd_bull])
            sig_info = (f"MACD{'✅' if macd_bull else '❌'} RSI{'✅' if rsi_ok else '❌'} "
                        f"EMA{'✅' if ema_ok else '❌'} VOL{'✅' if vol_high else '❌'} "
                        f"CVD{'✅' if cvd_bull else '❌'} | {score}/10 | {regime}")

            if n_ok >= 2 and score >= min_score:
                self.add_log(f"🎯 KAUF {coin}: {sig_info}")
                self._execute_buy(coin, price, share, idx, sig_info, score, regime)
            elif n_ok == 1:
                self.add_log(f"⏳ {coin} fast bereit: {sig_info}")

    def _execute_buy(self, coin, price, share, idx,
                     signal_info="", score=0, regime=""):
        try:
            self.exchange.create_market_buy_order(coin, None, {'quoteOrderQty': share * 0.98})
            self.active_trades[coin]  = True
            self.entry_prices[coin]   = price
            self.highest_prices[coin] = price
            msg = f"🛒 PAPER KAUF: {coin} @ {price:,.2f}$ | {share*0.98:.2f}$ | Score:{score}/10 | {regime}"
            self.add_log(msg)
            send_telegram(f"🛒 KAUF (PAPER) {coin}\n{price:,.2f}$ | Score:{score}/10\n{regime}")
            self.cache.add({
                "type": "BUY", "coin": coin, "price": price,
                "amount": share * 0.98, "score": score, "regime": regime,
                "signal": signal_info, "time": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            self.add_log(f"Kauf Fehler {coin}: {e}")

    def _execute_sell(self, coin, price, idx, balance, reason):
        try:
            asset = coin.split('/')[0]
            qty   = balance['free'].get(asset, 0.0)
            if qty <= 0: return
            self.exchange.create_market_sell_order(coin, qty)
            entry  = self.entry_prices[coin]
            pnl    = (qty * price) - (qty * entry)
            p_diff = ((price / entry) - 1) * 100

            self.session_profit += pnl
            if pnl < 0:
                self.daily_loss += abs(pnl)
                self.ui(self.card_daily_loss, text=f"{self.daily_loss:,.2f} $", text_color=CLR_RED)
            self.ui(self.card_profit, text=f"{self.session_profit:,.2f} $",
                    text_color=CLR_GREEN if self.session_profit >= 0 else CLR_RED)
            self.active_trades[coin] = False

            self.add_log(f"{reason} → {coin} | P&L: {pnl:+.2f}$ ({p_diff:+.2f}%)")
            send_telegram(
                f"{'✅' if pnl > 0 else '❌'} VERKAUF (PAPER) {coin}\n"
                f"{price:,.2f}$\nP&L: {pnl:+.2f}$ ({p_diff:+.2f}%)\nGrund: {reason}"
            )
            # Sofort auf Disk speichern (Absturz-Schutz!)
            self.cache.add({
                "type": "SELL", "coin": coin, "price": price, "qty": qty,
                "pnl": pnl, "pnl_pct": round(p_diff, 2), "reason": reason,
                "time": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            self.add_log(f"Verkauf Fehler {coin}: {e}")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = SvensImperium()
    app.mainloop()
