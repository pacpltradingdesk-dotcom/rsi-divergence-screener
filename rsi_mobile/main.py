"""
RSI Divergence x Order Block — Mobile Screener (Kivy/KivyMD)
=============================================================
Self-contained Android app. No pandas/numpy — pure Python math.
Uses Yahoo Finance public API via requests.
"""

import json
import threading
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

from kivy.lang import Builder
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, ListProperty

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineListItem
from kivymd.uix.spinner import MDSpinner
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.datatables import MDDataTable
from kivymd.uix.chip import MDChip
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.floatlayout import MDFloatLayout

# ─── Timeframe config ────────────────────────────────────────────────────────
TF_CONFIG = {
    "1H":      {"interval": "1h",  "range": "60d"},
    "Daily":   {"interval": "1d",  "range": "1y"},
    "Weekly":  {"interval": "1wk", "range": "2y"},
    "Monthly": {"interval": "1mo", "range": "5y"},
}

# ─── Stock lists ─────────────────────────────────────────────────────────────
NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "ITC", "INFY", "INDIGO", "JSWSTEEL", "JIOFIN", "KOTAKBANK",
    "LT", "M&M", "MARUTI", "MAXHEALTH", "NTPC", "NESTLEIND", "ONGC", "POWERGRID", "RELIANCE",
    "SBILIFE", "SHRIRAMFIN", "SBIN", "SUNPHARMA", "TCS", "TATACONSUM", "TMPV", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

BANK_NIFTY = [
    "AUBANK", "AXISBANK", "BANKBARODA", "CANBK", "FEDERALBNK", "HDFCBANK", "ICICIBANK",
    "IDFCFIRSTB", "INDUSINDBK", "KOTAKBANK", "PNB", "SBIN", "UNIONBANK", "YESBANK",
]

NIFTY_IT = [
    "COFORGE", "HCLTECH", "INFY", "LTIM", "MPHASIS", "OFSS", "PERSISTENT", "TCS", "TECHM",
    "WIPRO",
]

NIFTY_PHARMA = [
    "ABBOTINDIA", "AJANTPHARM", "ALKEM", "AUROPHARMA", "BIOCON", "CIPLA", "DIVISLAB",
    "DRREDDY", "GLAND", "GLENMARK", "IPCALAB", "JBCHEPHARM", "LAURUSLABS", "LUPIN", "MANKIND",
    "PPLPHARMA", "SUNPHARMA", "TORNTPHARM", "WOCKPHARMA", "ZYDUSLIFE",
]

NIFTY_AUTO = [
    "ASHOKLEY", "BAJAJ-AUTO", "BHARATFORG", "BOSCHLTD", "EICHERMOT", "EXIDEIND", "HEROMOTOCO",
    "M&M", "MARUTI", "MOTHERSON", "SONACOMS", "TVSMOTOR", "TMPV", "TIINDIA", "UNOMINDA",
]

PRESET_WATCHLISTS = {
    "Nifty 50":     NIFTY_50,
    "Bank Nifty":   BANK_NIFTY,
    "Nifty IT":     NIFTY_IT,
    "Nifty Pharma": NIFTY_PHARMA,
    "Nifty Auto":   NIFTY_AUTO,
}

# ═══════════════════════════════════════════════════════════════════════════════
# PURE PYTHON ANALYTICS (no pandas/numpy)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_yahoo_data(symbol, interval, range_str):
    """Fetch OHLCV via Yahoo Finance v8 chart API. Returns (bars, error_msg).
    Tries query1 then query2 as fallback. Uses full browser User-Agent."""
    ua = (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    data = None

    for host in hosts:
        url = (
            f"https://{host}/v8/finance/chart/{quote(symbol)}"
            f"?interval={interval}&range={range_str}"
        )
        req = Request(url, headers={"User-Agent": ua})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            break
        except Exception as e:
            last_err = str(e)
            continue

    if data is None:
        return None, f"Network error: {last_err}"

    try:
        chart = data.get("chart", {})
        err = chart.get("error")
        if err:
            return None, f"API error: {err.get('description', str(err))}"
        result = chart["result"][0]
        timestamps = result["timestamp"]
        q = result["indicators"]["quote"][0]
        opens = q["open"]
        highs = q["high"]
        lows = q["low"]
        closes = q["close"]
    except (KeyError, IndexError, TypeError) as e:
        return None, f"Parse error: {e}"

    bars = []
    for i in range(len(timestamps)):
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        if o is None or h is None or l is None or c is None:
            continue
        bars.append({"open": o, "high": h, "low": l, "close": c})

    if len(bars) <= 30:
        return None, f"Only {len(bars)} bars (need >30)"
    return bars, None


def calc_rsi(closes, length=14):
    """Wilder-smoothed RSI — pure Python."""
    if len(closes) < length + 1:
        return [50.0] * len(closes)

    rsi = [50.0] * len(closes)
    gains = []
    losses = []

    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))

    # First average (SMA)
    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    for i in range(length, len(gains)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length

        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def find_pivots(highs, lows, left=5, right=5):
    """Return indices of confirmed pivot highs and pivot lows on PRICE.
    Used for Order Block detection."""
    n = len(highs)
    ph_idx, pl_idx = [], []

    for i in range(left, n - right):
        is_ph = True
        for j in range(i - left, i + right + 1):
            if j != i and highs[j] >= highs[i]:
                is_ph = False
                break
        if is_ph:
            ph_idx.append(i)

        is_pl = True
        for j in range(i - left, i + right + 1):
            if j != i and lows[j] <= lows[i]:
                is_pl = False
                break
        if is_pl:
            pl_idx.append(i)

    return ph_idx, pl_idx


def find_rsi_pivots(rsi_values, left=5, right=5):
    """Return indices of confirmed pivot highs and pivot lows on RSI.
    Matches TradingView: ta.pivothigh(osc, lbL, lbR) / ta.pivotlow(osc, lbL, lbR)"""
    n = len(rsi_values)
    ph_idx, pl_idx = [], []

    for i in range(left, n - right):
        is_ph = True
        for j in range(i - left, i + right + 1):
            if j != i and rsi_values[j] >= rsi_values[i]:
                is_ph = False
                break
        if is_ph:
            ph_idx.append(i)

        is_pl = True
        for j in range(i - left, i + right + 1):
            if j != i and rsi_values[j] <= rsi_values[i]:
                is_pl = False
                break
        if is_pl:
            pl_idx.append(i)

    return ph_idx, pl_idx


def detect_divergences(bars, rsi, rsi_ph_idx, rsi_pl_idx, range_lower=5, range_upper=60):
    """
    Matches TradingView RSI Divergence Indicator exactly.
    Pivots are on RSI — price compared at those same bar indices.

    Regular Bullish:  Price Lower-Low  + RSI Higher-Low  (at RSI pivot lows)
    Hidden Bullish:   Price Higher-Low + RSI Lower-Low   (at RSI pivot lows)
    Regular Bearish:  Price Higher-High + RSI Lower-High  (at RSI pivot highs)
    Hidden Bearish:   Price Lower-High + RSI Higher-High  (at RSI pivot highs)
    """
    reg_bull, hid_bull = [], []
    reg_bear, hid_bear = [], []

    for k in range(1, len(rsi_pl_idx)):
        ci, pi = rsi_pl_idx[k], rsi_pl_idx[k - 1]
        if not (range_lower <= (ci - pi) <= range_upper):
            continue
        if bars[ci]["low"] < bars[pi]["low"] and rsi[ci] > rsi[pi]:
            reg_bull.append(ci)
        if bars[ci]["low"] > bars[pi]["low"] and rsi[ci] < rsi[pi]:
            hid_bull.append(ci)

    for k in range(1, len(rsi_ph_idx)):
        ci, pi = rsi_ph_idx[k], rsi_ph_idx[k - 1]
        if not (range_lower <= (ci - pi) <= range_upper):
            continue
        if bars[ci]["high"] > bars[pi]["high"] and rsi[ci] < rsi[pi]:
            reg_bear.append(ci)
        if bars[ci]["high"] < bars[pi]["high"] and rsi[ci] > rsi[pi]:
            hid_bear.append(ci)

    return reg_bull, reg_bear, hid_bull, hid_bear


def detect_order_blocks(bars, ph_idx, pl_idx):
    """Detect bullish & bearish order blocks."""
    n = len(bars)
    ph_set = set(ph_idx)
    pl_set = set(pl_idx)
    last_ph_val = None
    last_pl_val = None
    bull_obs, bear_obs = [], []

    for i in range(n):
        if i in ph_set:
            last_ph_val = bars[i]["high"]
        if i in pl_set:
            last_pl_val = bars[i]["low"]
        if i == 0:
            continue

        if last_ph_val is not None and bars[i]["high"] > last_ph_val and bars[i - 1]["high"] <= last_ph_val:
            for j in range(i - 1, max(i - 30, -1), -1):
                if bars[j]["close"] < bars[j]["open"]:
                    bull_obs.append({"high": bars[j]["high"], "low": bars[j]["low"], "bar": j, "breakout": i})
                    break

        if last_pl_val is not None and bars[i]["low"] < last_pl_val and bars[i - 1]["low"] >= last_pl_val:
            for j in range(i - 1, max(i - 30, -1), -1):
                if bars[j]["close"] > bars[j]["open"]:
                    bear_obs.append({"high": bars[j]["high"], "low": bars[j]["low"], "bar": j, "breakout": i})
                    break

    return bull_obs, bear_obs


def check_proximity(price, ob_list, threshold):
    """True if price near any recent OB midpoint."""
    for ob in reversed(ob_list[-10:]):
        mid = (ob["high"] + ob["low"]) / 2.0
        if mid > 0 and abs(price - mid) / mid <= threshold:
            return True
    return False


def scan_one(symbol, tf_label, rsi_len, pivot_len, ob_prox_pct):
    """Scan a single symbol x timeframe. Returns (result_dict, error_str).
    Always returns a result when data is available, even if no divergence.
    Uses RSI pivots for divergence (matching TradingView indicator)
    and price pivots for Order Block detection."""
    cfg = TF_CONFIG[tf_label]
    yahoo_symbol = symbol + ".NS"
    try:
        bars, fetch_err = fetch_yahoo_data(yahoo_symbol, cfg["interval"], cfg["range"])
        if bars is None:
            return None, fetch_err or "No data"

        needed = rsi_len + pivot_len * 2 + 10
        if len(bars) < needed:
            return None, f"Only {len(bars)} bars (need {needed})"

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]

        rsi = calc_rsi(closes, rsi_len)

        # RSI Pivots — for divergence (matches TradingView)
        rsi_ph_idx, rsi_pl_idx = find_rsi_pivots(rsi, pivot_len, pivot_len)

        # Price Pivots — for Order Block detection
        price_ph_idx, price_pl_idx = find_pivots(highs, lows, pivot_len, pivot_len)

        current_close = closes[-1]
        current_rsi = rsi[-1]

        # Default result (no signal)
        result = {
            "symbol": symbol,
            "timeframe": tf_label,
            "signal": "None",
            "div_type": "",
            "validated": False,
            "near_ob": False,
            "rsi": round(current_rsi, 1),
            "price": round(current_close, 2),
            "ob_zone": "",
        }

        if len(rsi_ph_idx) < 2 and len(rsi_pl_idx) < 2:
            return result, None

        # Divergences (RSI pivot based, with range check)
        reg_bull, reg_bear, hid_bull, hid_bear = detect_divergences(
            bars, rsi, rsi_ph_idx, rsi_pl_idx, range_lower=5, range_upper=60
        )

        # Recency: divergence must be within last pivot_len*5 bars
        # (~25 bars = ~1 month on daily; was pivot_len+3 which was only ~8 bars)
        threshold = len(bars) - pivot_len * 5
        has_reg_bull = len(reg_bull) > 0 and reg_bull[-1] >= threshold
        has_hid_bull = len(hid_bull) > 0 and hid_bull[-1] >= threshold
        has_reg_bear = len(reg_bear) > 0 and reg_bear[-1] >= threshold
        has_hid_bear = len(hid_bear) > 0 and hid_bear[-1] >= threshold

        # Order Blocks (price pivot based)
        bull_obs, bear_obs = detect_order_blocks(bars, price_ph_idx, price_pl_idx)

        near_bull_ob = check_proximity(current_close, bull_obs, ob_prox_pct)
        near_bear_ob = check_proximity(current_close, bear_obs, ob_prox_pct)

        # Pick strongest recent divergence
        signal = "None"
        div_type = ""
        candidates = []
        if has_reg_bull:
            candidates.append(("Bullish", "Regular", reg_bull[-1]))
        if has_hid_bull:
            candidates.append(("Bullish", "Hidden", hid_bull[-1]))
        if has_reg_bear:
            candidates.append(("Bearish", "Regular", reg_bear[-1]))
        if has_hid_bear:
            candidates.append(("Bearish", "Hidden", hid_bear[-1]))

        validated = False
        if candidates:
            candidates.sort(key=lambda x: -x[2])
            signal = candidates[0][0]
            div_type = candidates[0][1]

            if signal == "Bullish" and near_bull_ob:
                validated = True
            elif signal == "Bearish" and near_bear_ob:
                validated = True

        ob_zone = ""
        if validated and signal == "Bullish" and bull_obs:
            ob = bull_obs[-1]
            ob_zone = f"{ob['low']:.2f} - {ob['high']:.2f}"
        elif validated and signal == "Bearish" and bear_obs:
            ob = bear_obs[-1]
            ob_zone = f"{ob['low']:.2f} - {ob['high']:.2f}"

        result.update({
            "signal": signal,
            "div_type": div_type,
            "validated": validated,
            "near_ob": near_bull_ob or near_bear_ob,
            "ob_zone": ob_zone,
        })
        return result, None
    except Exception as e:
        return None, f"Error: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# KV LAYOUT
# ═══════════════════════════════════════════════════════════════════════════════

KV = '''
#:import Snackbar kivymd.uix.snackbar.Snackbar

<ResultCard>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: dp(12), dp(8)
    spacing: dp(4)
    md_bg_color: self.bg_color
    radius: [dp(10)]
    elevation: 2
    MDBoxLayout:
        size_hint_y: None
        height: dp(28)
        spacing: dp(8)
        MDLabel:
            text: root.symbol_text
            font_style: "H6"
            bold: True
            size_hint_x: 0.35
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
        MDLabel:
            text: root.tf_text
            halign: "center"
            size_hint_x: 0.15
            theme_text_color: "Custom"
            text_color: 0.6, 0.6, 0.7, 1
            font_style: "Caption"
        MDLabel:
            text: root.div_type_text
            halign: "center"
            size_hint_x: 0.2
            theme_text_color: "Custom"
            text_color: root.div_type_color
            font_style: "Caption"
            bold: True
        MDLabel:
            text: root.signal_text
            halign: "right"
            size_hint_x: 0.3
            bold: True
            theme_text_color: "Custom"
            text_color: root.signal_color
    MDBoxLayout:
        size_hint_y: None
        height: dp(22)
        spacing: dp(8)
        MDLabel:
            text: root.price_text
            font_style: "Caption"
            theme_text_color: "Custom"
            text_color: 0.8, 0.8, 0.85, 1
        MDLabel:
            text: root.rsi_text
            halign: "center"
            font_style: "Caption"
            theme_text_color: "Custom"
            text_color: root.rsi_color
        MDLabel:
            text: root.action_text
            halign: "right"
            font_style: "Caption"
            bold: True
            theme_text_color: "Custom"
            text_color: root.action_color
    MDLabel:
        text: root.ob_text
        font_style: "Caption"
        size_hint_y: None
        height: dp(18) if root.ob_text else 0
        opacity: 1 if root.ob_text else 0
        theme_text_color: "Custom"
        text_color: 0.9, 0.8, 0.2, 1


MDScreen:
    md_bg_color: 0.04, 0.04, 0.08, 1

    MDBoxLayout:
        orientation: "vertical"

        # ─── Top Bar ───
        MDBoxLayout:
            size_hint_y: None
            height: dp(56)
            md_bg_color: 0.07, 0.07, 0.12, 1
            padding: dp(16), 0
            MDLabel:
                text: "RSI Div x OB Screener"
                font_style: "H6"
                bold: True
                theme_text_color: "Custom"
                text_color: 0, 0.83, 0.67, 1
                valign: "center"
            MDLabel:
                id: last_scan_label
                text: ""
                halign: "right"
                font_style: "Caption"
                theme_text_color: "Custom"
                text_color: 0.4, 0.4, 0.5, 1
                valign: "center"

        MDScrollView:
            MDBoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: dp(12)
                spacing: dp(12)

                # ─── Watchlist Presets ───
                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(14)
                    spacing: dp(8)
                    md_bg_color: 0.1, 0.1, 0.18, 1
                    radius: [dp(10)]

                    MDLabel:
                        text: "WATCHLIST"
                        font_style: "Overline"
                        theme_text_color: "Custom"
                        text_color: 0.43, 0.43, 0.51, 1
                        size_hint_y: None
                        height: dp(20)

                    MDBoxLayout:
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(6)
                        MDRaisedButton:
                            text: "Nifty 50"
                            font_size: "12sp"
                            md_bg_color: 0.07, 0.07, 0.12, 1
                            on_release: app.load_preset("Nifty 50")
                        MDRaisedButton:
                            text: "Bank Nifty"
                            font_size: "12sp"
                            md_bg_color: 0.07, 0.07, 0.12, 1
                            on_release: app.load_preset("Bank Nifty")
                        MDRaisedButton:
                            text: "IT"
                            font_size: "12sp"
                            md_bg_color: 0.07, 0.07, 0.12, 1
                            on_release: app.load_preset("Nifty IT")

                    MDBoxLayout:
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(6)
                        MDRaisedButton:
                            text: "Pharma"
                            font_size: "12sp"
                            md_bg_color: 0.07, 0.07, 0.12, 1
                            on_release: app.load_preset("Nifty Pharma")
                        MDRaisedButton:
                            text: "Auto"
                            font_size: "12sp"
                            md_bg_color: 0.07, 0.07, 0.12, 1
                            on_release: app.load_preset("Nifty Auto")
                        MDRaisedButton:
                            text: "Clear"
                            font_size: "12sp"
                            md_bg_color: 0.3, 0.1, 0.1, 1
                            on_release: app.clear_symbols()

                    MDTextField:
                        id: symbols_input
                        hint_text: "Symbols (comma separated)"
                        mode: "rectangle"
                        multiline: True
                        size_hint_y: None
                        height: dp(70)
                        font_size: "13sp"
                        text_color_normal: 0.8, 0.8, 0.85, 1
                        text_color_focus: 1, 1, 1, 1
                        hint_text_color_normal: 0.4, 0.4, 0.5, 1
                        line_color_normal: 0.2, 0.2, 0.3, 1
                        line_color_focus: 0, 0.83, 0.67, 1

                # ─── Settings ───
                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(14)
                    spacing: dp(8)
                    md_bg_color: 0.1, 0.1, 0.18, 1
                    radius: [dp(10)]

                    MDLabel:
                        text: "SETTINGS"
                        font_style: "Overline"
                        theme_text_color: "Custom"
                        text_color: 0.43, 0.43, 0.51, 1
                        size_hint_y: None
                        height: dp(20)

                    MDBoxLayout:
                        size_hint_y: None
                        height: dp(50)
                        spacing: dp(8)

                        MDTextField:
                            id: rsi_len
                            hint_text: "RSI Len"
                            text: "14"
                            mode: "rectangle"
                            input_filter: "int"
                            size_hint_x: 0.33
                            font_size: "14sp"
                            line_color_normal: 0.2, 0.2, 0.3, 1
                            line_color_focus: 0, 0.83, 0.67, 1
                        MDTextField:
                            id: pivot_len
                            hint_text: "Pivot Len"
                            text: "5"
                            mode: "rectangle"
                            input_filter: "int"
                            size_hint_x: 0.33
                            font_size: "14sp"
                            line_color_normal: 0.2, 0.2, 0.3, 1
                            line_color_focus: 0, 0.83, 0.67, 1
                        MDTextField:
                            id: ob_prox
                            hint_text: "OB Prox %"
                            text: "1.0"
                            mode: "rectangle"
                            size_hint_x: 0.33
                            font_size: "14sp"
                            line_color_normal: 0.2, 0.2, 0.3, 1
                            line_color_focus: 0, 0.83, 0.67, 1

                    MDLabel:
                        text: "TIMEFRAMES"
                        font_style: "Overline"
                        theme_text_color: "Custom"
                        text_color: 0.43, 0.43, 0.51, 1
                        size_hint_y: None
                        height: dp(20)

                    MDBoxLayout:
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(4)

                        MDBoxLayout:
                            spacing: dp(2)
                            MDCheckbox:
                                id: tf_1h
                                active: True
                                size_hint: None, None
                                size: dp(36), dp(36)
                                selected_color: 0, 0.83, 0.67, 1
                            MDLabel:
                                text: "1H"
                                font_style: "Caption"
                                valign: "center"
                                theme_text_color: "Custom"
                                text_color: 0.8, 0.8, 0.85, 1

                        MDBoxLayout:
                            spacing: dp(2)
                            MDCheckbox:
                                id: tf_daily
                                active: True
                                size_hint: None, None
                                size: dp(36), dp(36)
                                selected_color: 0, 0.83, 0.67, 1
                            MDLabel:
                                text: "Daily"
                                font_style: "Caption"
                                valign: "center"
                                theme_text_color: "Custom"
                                text_color: 0.8, 0.8, 0.85, 1

                        MDBoxLayout:
                            spacing: dp(2)
                            MDCheckbox:
                                id: tf_weekly
                                active: True
                                size_hint: None, None
                                size: dp(36), dp(36)
                                selected_color: 0, 0.83, 0.67, 1
                            MDLabel:
                                text: "Wkly"
                                font_style: "Caption"
                                valign: "center"
                                theme_text_color: "Custom"
                                text_color: 0.8, 0.8, 0.85, 1

                        MDBoxLayout:
                            spacing: dp(2)
                            MDCheckbox:
                                id: tf_monthly
                                active: True
                                size_hint: None, None
                                size: dp(36), dp(36)
                                selected_color: 0, 0.83, 0.67, 1
                            MDLabel:
                                text: "Mthly"
                                font_style: "Caption"
                                valign: "center"
                                theme_text_color: "Custom"
                                text_color: 0.8, 0.8, 0.85, 1

                # ─── Scan Button ───
                MDRaisedButton:
                    id: scan_btn
                    text: "SCAN NOW"
                    size_hint_x: 1
                    size_hint_y: None
                    height: dp(50)
                    font_size: "16sp"
                    md_bg_color: 0, 0.83, 0.67, 1
                    text_color: 0, 0, 0, 1
                    on_release: app.start_scan()

                # ─── Status ───
                MDLabel:
                    id: scan_status
                    text: ""
                    halign: "center"
                    font_style: "Caption"
                    theme_text_color: "Custom"
                    text_color: 0.43, 0.43, 0.51, 1
                    size_hint_y: None
                    height: dp(24)

                # ─── Stats Row ───
                MDBoxLayout:
                    id: stats_row
                    size_hint_y: None
                    height: dp(60)
                    spacing: dp(8)
                    opacity: 0

                    MDCard:
                        md_bg_color: 0.1, 0.1, 0.18, 1
                        radius: [dp(8)]
                        padding: dp(8)
                        MDBoxLayout:
                            orientation: "vertical"
                            MDLabel:
                                id: stat_scanned
                                text: "0"
                                halign: "center"
                                font_style: "H6"
                                bold: True
                                theme_text_color: "Custom"
                                text_color: 0.29, 0.62, 1, 1
                            MDLabel:
                                text: "Scanned"
                                halign: "center"
                                font_style: "Overline"
                                theme_text_color: "Custom"
                                text_color: 0.43, 0.43, 0.51, 1

                    MDCard:
                        md_bg_color: 0.1, 0.1, 0.18, 1
                        radius: [dp(8)]
                        padding: dp(8)
                        MDBoxLayout:
                            orientation: "vertical"
                            MDLabel:
                                id: stat_signals
                                text: "0"
                                halign: "center"
                                font_style: "H6"
                                bold: True
                                theme_text_color: "Custom"
                                text_color: 0, 0.83, 0.67, 1
                            MDLabel:
                                text: "Signals"
                                halign: "center"
                                font_style: "Overline"
                                theme_text_color: "Custom"
                                text_color: 0.43, 0.43, 0.51, 1

                    MDCard:
                        md_bg_color: 0.1, 0.1, 0.18, 1
                        radius: [dp(8)]
                        padding: dp(8)
                        MDBoxLayout:
                            orientation: "vertical"
                            MDLabel:
                                id: stat_validated
                                text: "0"
                                halign: "center"
                                font_style: "H6"
                                bold: True
                                theme_text_color: "Custom"
                                text_color: 1, 0.84, 0, 1
                            MDLabel:
                                text: "Validated"
                                halign: "center"
                                font_style: "Overline"
                                theme_text_color: "Custom"
                                text_color: 0.43, 0.43, 0.51, 1

                # ─── Filter Buttons ───
                MDBoxLayout:
                    id: filter_row
                    size_hint_y: None
                    height: dp(36)
                    spacing: dp(6)

                    MDRaisedButton:
                        text: "All"
                        font_size: "11sp"
                        md_bg_color: 0.18, 0.35, 0.55, 1
                        on_release: app.set_filter("all")
                    MDRaisedButton:
                        text: "Signals"
                        font_size: "11sp"
                        md_bg_color: 0.07, 0.07, 0.12, 1
                        on_release: app.set_filter("signals")
                    MDRaisedButton:
                        text: "Validated"
                        font_size: "11sp"
                        md_bg_color: 0.07, 0.07, 0.12, 1
                        on_release: app.set_filter("validated")
                    MDRaisedButton:
                        text: "Bull"
                        font_size: "11sp"
                        md_bg_color: 0.07, 0.07, 0.12, 1
                        on_release: app.set_filter("bullish")
                    MDRaisedButton:
                        text: "Bear"
                        font_size: "11sp"
                        md_bg_color: 0.07, 0.07, 0.12, 1
                        on_release: app.set_filter("bearish")
                    MDRaisedButton:
                        text: "Hidden"
                        font_size: "11sp"
                        md_bg_color: 0.07, 0.07, 0.12, 1
                        on_release: app.set_filter("hidden")

                # ─── Results ───
                MDBoxLayout:
                    id: results_container
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(6)

                    MDLabel:
                        id: empty_label
                        text: "Add symbols and tap SCAN NOW"
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: 0.43, 0.43, 0.51, 1
                        size_hint_y: None
                        height: dp(80)

                # Bottom padding
                Widget:
                    size_hint_y: None
                    height: dp(40)


<ResultCard>:
    size_hint_y: None
    height: self.minimum_height
'''


class ResultCard(MDCard):
    """A single result row card."""
    symbol_text = StringProperty("")
    tf_text = StringProperty("")
    signal_text = StringProperty("")
    signal_color = ListProperty([0.6, 0.6, 0.7, 1])
    div_type_text = StringProperty("")
    div_type_color = ListProperty([0.4, 0.4, 0.5, 1])
    price_text = StringProperty("")
    rsi_text = StringProperty("")
    rsi_color = ListProperty([0.8, 0.8, 0.85, 1])
    action_text = StringProperty("")
    action_color = ListProperty([0.4, 0.4, 0.5, 1])
    ob_text = StringProperty("")
    bg_color = ListProperty([0.1, 0.1, 0.18, 1])


class RSIScreenerApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_results = []
        self.scan_errors = []
        self.current_filter = "all"
        self.scanning = False

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        return Builder.load_string(KV)

    def load_preset(self, name):
        symbols = PRESET_WATCHLISTS.get(name, [])
        self.root.ids.symbols_input.text = ", ".join(symbols)
        Snackbar(text=f"Loaded {name} ({len(symbols)} symbols)").open()

    def clear_symbols(self):
        self.root.ids.symbols_input.text = ""

    def start_scan(self):
        if self.scanning:
            return

        symbols_text = self.root.ids.symbols_input.text.strip()
        symbols = [s.strip().upper() for s in symbols_text.replace("\n", ",").split(",") if s.strip()]

        if not symbols:
            Snackbar(text="Enter at least one symbol!").open()
            return

        timeframes = []
        if self.root.ids.tf_1h.active:
            timeframes.append("1H")
        if self.root.ids.tf_daily.active:
            timeframes.append("Daily")
        if self.root.ids.tf_weekly.active:
            timeframes.append("Weekly")
        if self.root.ids.tf_monthly.active:
            timeframes.append("Monthly")

        if not timeframes:
            Snackbar(text="Select at least one timeframe!").open()
            return

        try:
            rsi_len = int(self.root.ids.rsi_len.text or "14")
            pivot_len = int(self.root.ids.pivot_len.text or "5")
            ob_prox = float(self.root.ids.ob_prox.text or "1.0") / 100.0
        except ValueError:
            Snackbar(text="Invalid settings values!").open()
            return

        self.scanning = True
        self.root.ids.scan_btn.text = "Scanning..."
        self.root.ids.scan_btn.disabled = True
        total = len(symbols) * len(timeframes)
        self.root.ids.scan_status.text = f"Scanning {len(symbols)} symbols x {len(timeframes)} TFs..."

        thread = threading.Thread(
            target=self._run_scan_thread,
            args=(symbols, timeframes, rsi_len, pivot_len, ob_prox, total),
            daemon=True,
        )
        thread.start()

    def _run_scan_thread(self, symbols, timeframes, rsi_len, pivot_len, ob_prox, total):
        """Run scan in background thread, post results to UI thread."""
        results = []
        errors = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {}
            for sym in symbols:
                for tf in timeframes:
                    fut = pool.submit(scan_one, sym, tf, rsi_len, pivot_len, ob_prox)
                    futures[fut] = (sym, tf)

            done_count = 0
            for future in as_completed(futures):
                result, err = future.result()
                if result is not None:
                    results.append(result)
                elif err:
                    sym, tf = futures[future]
                    errors.append(f"{sym}({tf}): {err}")
                done_count += 1
                if done_count % 5 == 0:
                    pct = int(done_count / total * 100)
                    Clock.schedule_once(lambda dt, p=pct: self._update_progress(p))

        results.sort(key=lambda x: (not x["validated"], x["signal"] == "None", x["symbol"], x["timeframe"]))

        signals_count = sum(1 for r in results if r["signal"] != "None")
        validated_count = sum(1 for r in results if r["validated"])

        Clock.schedule_once(lambda dt: self._scan_complete(
            results, total, signals_count, validated_count, errors
        ))

    def _update_progress(self, pct):
        self.root.ids.scan_status.text = f"Scanning... {pct}%"

    def _scan_complete(self, results, total, signals, validated, errors=None):
        self.all_results = results
        self.scan_errors = errors or []
        self.scanning = False

        self.root.ids.scan_btn.text = "SCAN NOW"
        self.root.ids.scan_btn.disabled = False

        fetched = len(results)
        failed = len(self.scan_errors)
        if failed > 0:
            self.root.ids.scan_status.text = (
                f"Done - {signals} signal(s), {validated} validated | {failed} failed"
            )
        else:
            self.root.ids.scan_status.text = f"Done - {signals} signal(s), {validated} validated"

        self.root.ids.stats_row.opacity = 1
        self.root.ids.stat_scanned.text = str(fetched)
        self.root.ids.stat_signals.text = str(signals)
        self.root.ids.stat_validated.text = str(validated)

        now = datetime.now().strftime("%H:%M:%S")
        self.root.ids.last_scan_label.text = f"Last: {now}"

        # Show first error as snackbar if ALL failed (likely API issue)
        if failed > 0 and fetched == 0 and self.scan_errors:
            Snackbar(text=f"All fetches failed: {self.scan_errors[0]}").open()

        self.render_results()

    def set_filter(self, f):
        self.current_filter = f
        # Update button colors
        filter_row = self.root.ids.filter_row
        labels = {"all": "All", "signals": "Signals", "validated": "Validated", "bullish": "Bull", "bearish": "Bear", "hidden": "Hidden"}
        for child in filter_row.children:
            if hasattr(child, "text"):
                if child.text == labels.get(f, ""):
                    child.md_bg_color = [0.18, 0.35, 0.55, 1]
                else:
                    child.md_bg_color = [0.07, 0.07, 0.12, 1]
        self.render_results()

    def render_results(self):
        container = self.root.ids.results_container
        container.clear_widgets()

        data = self._filter(self.all_results)

        if not data:
            lbl = MDLabel(
                text="No results match filter" if self.all_results else "Add symbols and tap SCAN NOW",
                halign="center",
                theme_text_color="Custom",
                text_color=[0.43, 0.43, 0.51, 1],
                size_hint_y=None,
                height=dp(80),
            )
            container.add_widget(lbl)
            return

        for r in data:
            # Signal color
            if r["signal"] == "Bullish":
                sig_color = [0, 0.83, 0.67, 1]
            elif r["signal"] == "Bearish":
                sig_color = [1, 0.28, 0.34, 1]
            else:
                sig_color = [0.43, 0.43, 0.51, 1]

            # Divergence type
            dt = r.get("div_type", "")
            if dt == "Regular":
                div_type_text = "Regular"
                div_type_color = [0.29, 0.62, 1, 1]  # blue
            elif dt == "Hidden":
                div_type_text = "Hidden"
                div_type_color = [0.66, 0.33, 0.97, 1]  # purple
            else:
                div_type_text = "-"
                div_type_color = [0.43, 0.43, 0.51, 1]

            # RSI color
            if r["rsi"] < 35:
                rsi_color = [0, 0.83, 0.67, 1]
            elif r["rsi"] > 65:
                rsi_color = [1, 0.28, 0.34, 1]
            else:
                rsi_color = [0.8, 0.8, 0.85, 1]

            # Action
            if r["validated"] and r["signal"] == "Bullish":
                action_text = "LONG"
                action_color = [0, 0.83, 0.67, 1]
            elif r["validated"] and r["signal"] == "Bearish":
                action_text = "SHORT"
                action_color = [1, 0.28, 0.34, 1]
            else:
                action_text = "-"
                action_color = [0.43, 0.43, 0.51, 1]

            # Background for validated
            if r["validated"]:
                bg = [0.02, 0.12, 0.1, 1]
            else:
                bg = [0.1, 0.1, 0.18, 1]

            card = ResultCard(
                symbol_text=r["symbol"],
                tf_text=r["timeframe"],
                signal_text=r["signal"],
                signal_color=sig_color,
                div_type_text=div_type_text,
                div_type_color=div_type_color,
                price_text=f"Rs {r['price']:,.2f}",
                rsi_text=f"RSI {r['rsi']}",
                rsi_color=rsi_color,
                action_text=action_text,
                action_color=action_color,
                ob_text=f"OB Zone: {r['ob_zone']}" if r["ob_zone"] else "",
                bg_color=bg,
            )
            container.add_widget(card)

    def _filter(self, data):
        if self.current_filter == "signals":
            return [r for r in data if r["signal"] != "None"]
        elif self.current_filter == "validated":
            return [r for r in data if r["validated"]]
        elif self.current_filter == "bullish":
            return [r for r in data if r["signal"] == "Bullish"]
        elif self.current_filter == "bearish":
            return [r for r in data if r["signal"] == "Bearish"]
        elif self.current_filter == "hidden":
            return [r for r in data if r.get("div_type") == "Hidden"]
        return data


if __name__ == "__main__":
    RSIScreenerApp().run()
