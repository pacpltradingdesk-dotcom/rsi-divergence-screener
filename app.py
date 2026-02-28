"""
RSI Divergence × Order Block — Web Screener
=============================================
Scans multiple symbols across 1H / Daily / Weekly / Monthly timeframes.
Detects pivot-confirmed RSI divergence, institutional Order Blocks,
and validates signals only when price is near an OB zone.
"""

from flask import Flask, render_template, jsonify, request as req
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import traceback

app = Flask(__name__)

# ─── Timeframe map ────────────────────────────────────────────────────────────
TF_CONFIG = {
    "1H":      {"interval": "1h",  "period": "60d"},
    "Daily":   {"interval": "1d",  "period": "1y"},
    "Weekly":  {"interval": "1wk", "period": "2y"},
    "Monthly": {"interval": "1mo", "period": "5y"},
}

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

NIFTY_MIDCAP_100 = [
    "360ONE", "ACC", "APLAPOLLO", "AUBANK", "ATGL", "ABCAPITAL", "ALKEM", "ASHOKLEY", "ASTRAL",
    "AUROPHARMA", "BSE", "BANKINDIA", "BDL", "BHARATFORG", "BHEL", "BHARTIHEXA", "BIOCON",
    "BLUESTARCO", "COCHINSHIP", "COFORGE", "COLPAL", "CONCOR", "COROMANDEL", "CUMMINSIND",
    "DABUR", "DIXON", "EXIDEIND", "NYKAA", "FEDERALBNK", "FORTIS", "GMRAIRPORT", "GLENMARK",
    "GODFRYPHLP", "GODREJPROP", "HDFCAMC", "HEROMOTOCO", "HINDPETRO", "POWERINDIA", "HUDCO",
    "IDFCFIRSTB", "IRB", "ITCHOTELS", "INDIANB", "IRCTC", "IREDA", "IGL", "INDUSTOWER",
    "INDUSINDBK", "JUBLFOOD", "KEI", "KPITTECH", "KALYANKJIL", "LTF", "LICHSGFIN", "LUPIN",
    "MRF", "M&MFIN", "MANKIND", "MARICO", "MFSL", "MOTILALOFS", "MPHASIS", "MUTHOOTFIN",
    "NHPC", "NMDC", "NTPCGREEN", "NATIONALUM", "OBEROIRLTY", "OIL", "PAYTM", "OFSS",
    "POLICYBZR", "PIIND", "PAGEIND", "PATANJALI", "PERSISTENT", "PHOENIXLTD", "POLYCAB",
    "PREMIERENE", "PRESTIGE", "RVNL", "SBICARD", "SRF", "SONACOMS", "SAIL", "SUPREMEIND",
    "SUZLON", "SWIGGY", "TATACOMM", "TATAELXSI", "TATATECH", "TORNTPOWER", "TIINDIA", "UPL",
    "UNIONBANK", "VMM", "IDEA", "VOLTAS", "WAAREEENER", "YESBANK",
]

NIFTY_500 = [
    "360ONE", "3MINDIA", "ABB", "ACC", "ACMESOLAR", "AIAENG", "APLAPOLLO", "AUBANK", "AWL",
    "AADHARHFC", "AARTIIND", "AAVAS", "ABBOTINDIA", "ACE", "ADANIENSOL", "ADANIENT",
    "ADANIGREEN", "ADANIPORTS", "ADANIPOWER", "ATGL", "ABCAPITAL", "ABFRL", "ABLBL", "ABREL",
    "ABSLAMC", "AEGISLOG", "AEGISVOPAK", "AFCONS", "AFFLE", "AJANTPHARM", "AKUMS", "AKZOINDIA",
    "APLLTD", "ALKEM", "ALKYLAMINE", "ALOKINDS", "ARE&M", "AMBER", "AMBUJACEM", "ANANDRATHI",
    "ANANTRAJ", "ANGELONE", "APARINDS", "APOLLOHOSP", "APOLLOTYRE", "APTUS", "ASAHIINDIA",
    "ASHOKLEY", "ASIANPAINT", "ASTERDM", "ASTRAZEN", "ASTRAL", "ATHERENERG", "ATUL",
    "AUROPHARMA", "AIIL", "DMART", "AXISBANK", "BASF", "BEML", "BLS", "BSE", "BAJAJ-AUTO",
    "BAJFINANCE", "BAJAJFINSV", "BAJAJHLDNG", "BAJAJHFL", "BALKRISIND", "BALRAMCHIN",
    "BANDHANBNK", "BANKBARODA", "BANKINDIA", "MAHABANK", "BATAINDIA", "BAYERCROP", "BERGEPAINT",
    "BDL", "BEL", "BHARATFORG", "BHEL", "BPCL", "BHARTIARTL", "BHARTIHEXA", "BIKAJI", "BIOCON",
    "BSOFT", "BLUEDART", "BLUEJET", "BLUESTARCO", "BBTC", "BOSCHLTD", "FIRSTCRY", "BRIGADE",
    "BRITANNIA", "MAPMYINDIA", "CCL", "CESC", "CGPOWER", "CRISIL", "CAMPUS", "CANFINHOME",
    "CANBK", "CAPLIPOINT", "CGCL", "CARBORUNIV", "CASTROLIND", "CEATLTD", "CENTRALBK", "CDSL",
    "CENTURYPLY", "CERA", "CHALET", "CHAMBLFERT", "CHENNPETRO", "CHOICEIN", "CHOLAHLDNG",
    "CHOLAFIN", "CIPLA", "CUB", "CLEAN", "COALINDIA", "COCHINSHIP", "COFORGE", "COHANCE",
    "COLPAL", "CAMS", "CONCORDBIO", "CONCOR", "COROMANDEL", "CRAFTSMAN", "CREDITACC", "CROMPTON",
    "CUMMINSIND", "CYIENT", "DCMSHRIRAM", "DLF", "DOMS", "DABUR", "DALBHARAT", "DATAPATTNS",
    "DEEPAKFERT", "DEEPAKNTR", "DELHIVERY", "DEVYANI", "DIVISLAB", "DIXON", "AGARWALEYE",
    "LALPATHLAB", "DRREDDY", "EIDPARRY", "EIHOTEL", "EICHERMOT", "ELECON", "ELGIEQUIP",
    "EMAMILTD", "EMCURE", "ENDURANCE", "ENGINERSIN", "ERIS", "ESCORTS", "ETERNAL", "EXIDEIND",
    "NYKAA", "FEDERALBNK", "FACT", "FINCABLES", "FINPIPE", "FSL", "FIVESTAR", "FORCEMOT",
    "FORTIS", "GAIL", "GVT&D", "GMRAIRPORT", "GRSE", "GICRE", "GILLETTE", "GLAND", "GLAXO",
    "GLENMARK", "MEDANTA", "GODIGIT", "GPIL", "GODFRYPHLP", "GODREJAGRO", "GODREJCP",
    "GODREJIND", "GODREJPROP", "GRANULES", "GRAPHITE", "GRASIM", "GRAVITA", "GESHIP",
    "FLUOROCHEM", "GUJGASLTD", "GMDCLTD", "GSPL", "HEG", "HBLENGINE", "HCLTECH", "HDFCAMC",
    "HDFCBANK", "HDFCLIFE", "HFCL", "HAPPSTMNDS", "HAVELLS", "HEROMOTOCO", "HEXT", "HSCL",
    "HINDALCO", "HAL", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HINDZINC", "POWERINDIA",
    "HOMEFIRST", "HONASA", "HONAUT", "HUDCO", "HYUNDAI", "ICICIBANK", "ICICIGI", "ICICIPRULI",
    "IDBI", "IDFCFIRSTB", "IFCI", "IIFL", "INOXINDIA", "IRB", "IRCON", "ITCHOTELS", "ITC",
    "ITI", "INDGN", "INDIACEM", "INDIAMART", "INDIANB", "IEX", "INDHOTEL", "IOC", "IOB",
    "IRCTC", "IRFC", "IREDA", "IGL", "INDUSTOWER", "INDUSINDBK", "NAUKRI", "INFY", "INOXWIND",
    "INTELLECT", "INDIGO", "IGIL", "IKS", "IPCALAB", "JBCHEPHARM", "JKCEMENT", "JBMA",
    "JKTYRE", "JMFINANCIL", "JSWCEMENT", "JSWENERGY", "JSWINFRA", "JSWSTEEL", "JPPOWER",
    "J&KBANK", "JINDALSAW", "JSL", "JINDALSTEL", "JIOFIN", "JUBLFOOD", "JUBLINGREA",
    "JUBLPHARMA", "JWL", "JYOTHYLAB", "JYOTICNC", "KPRMILL", "KEI", "KPITTECH", "KSB",
    "KAJARIACER", "KPIL", "KALYANKJIL", "KARURVYSYA", "KAYNES", "KEC", "KFINTECH",
    "KIRLOSBROS", "KIRLOSENG", "KOTAKBANK", "KIMS", "LTF", "LTTS", "LICHSGFIN", "LTFOODS",
    "LTIM", "LT", "LATENTVIEW", "LAURUSLABS", "THELEELA", "LEMONTREE", "LICI", "LINDEINDIA",
    "LLOYDSME", "LODHA", "LUPIN", "MMTC", "MRF", "MGL", "MAHSCOOTER", "MAHSEAMLES", "M&MFIN",
    "M&M", "MANAPPURAM", "MRPL", "MANKIND", "MARICO", "MARUTI", "MFSL", "MAXHEALTH", "MAZDOCK",
    "METROPOLIS", "MINDACORP", "MSUMI", "MOTILALOFS", "MPHASIS", "MCX", "MUTHOOTFIN",
    "NATCOPHARM", "NBCC", "NCC", "NHPC", "NLCINDIA", "NMDC", "NSLNISP", "NTPCGREEN", "NTPC",
    "NH", "NATIONALUM", "NAVA", "NAVINFLUOR", "NESTLEIND", "NETWEB", "NEULANDLAB", "NEWGEN",
    "NAM-INDIA", "NIVABUPA", "NUVAMA", "NUVOCO", "OBEROIRLTY", "ONGC", "OIL", "OLAELEC",
    "OLECTRA", "PAYTM", "ONESOURCE", "OFSS", "POLICYBZR", "PCBL", "PGEL", "PIIND",
    "PNBHOUSING", "PTCIL", "PVRINOX", "PAGEIND", "PATANJALI", "PERSISTENT", "PETRONET",
    "PFIZER", "PHOENIXLTD", "PIDILITIND", "PPLPHARMA", "POLYMED", "POLYCAB", "POONAWALLA",
    "PFC", "POWERGRID", "PRAJIND", "PREMIERENE", "PRESTIGE", "PGHH", "PNB", "RRKABEL",
    "RBLBANK", "RECLTD", "RHIM", "RITES", "RADICO", "RVNL", "RAILTEL", "RAINBOW", "RKFORGE",
    "RCF", "REDINGTON", "RELIANCE", "RELINFRA", "RPOWER", "SBFC", "SBICARD", "SBILIFE",
    "SJVN", "SRF", "SAGILITY", "SAILIFE", "SAMMAANCAP", "MOTHERSON", "SAPPHIRE", "SARDAEN",
    "SAREGAMA", "SCHAEFFLER", "SCHNEIDER", "SCI", "SHREECEM", "SHRIRAMFIN", "SHYAMMETL",
    "ENRIN", "SIEMENS", "SIGNATURE", "SOBHA", "SOLARINDS", "SONACOMS", "SONATSOFTW",
    "STARHEALTH", "SBIN", "SAIL", "SUMICHEM", "SUNPHARMA", "SUNTV", "SUNDARMFIN", "SUNDRMFAST",
    "SUPREMEIND", "SUZLON", "SWANCORP", "SWIGGY", "SYNGENE", "SYRMA", "TBOTEK", "TVSMOTOR",
    "TATACHEM", "TATACOMM", "TCS", "TATACONSUM", "TATAELXSI", "TATAINVEST", "TMPV",
    "TATAPOWER", "TATASTEEL", "TATATECH", "TTML", "TECHM", "TECHNOE", "TEJASNET", "NIACL",
    "RAMCOCEM", "THERMAX", "TIMKEN", "TITAGARH", "TITAN", "TORNTPHARM", "TORNTPOWER", "TARIL",
    "TRENT", "TRIDENT", "TRIVENI", "TRITURBINE", "TIINDIA", "UCOBANK", "UNOMINDA", "UPL",
    "UTIAMC", "ULTRACEMCO", "UNIONBANK", "UBL", "UNITDSPR", "USHAMART", "VGUARD", "DBREALTY",
    "VTL", "VBL", "MANYAVAR", "VEDL", "VENTIVE", "VIJAYA", "VMM", "IDEA", "VOLTAS",
    "WAAREEENER", "WELCORP", "WELSPUNLIV", "WHIRLPOOL", "WIPRO", "WOCKPHARMA", "YESBANK",
    "ZFCVINDIA", "ZEEL", "ZENTEC", "ZENSARTECH", "ZYDUSLIFE", "ECLERX",
]

PRESET_WATCHLISTS = {
    "Nifty 50":      [s + ".NS" for s in NIFTY_50],
    "Bank Nifty":    [s + ".NS" for s in BANK_NIFTY],
    "Nifty IT":      [s + ".NS" for s in NIFTY_IT],
    "Nifty Pharma":  [s + ".NS" for s in NIFTY_PHARMA],
    "Nifty Auto":    [s + ".NS" for s in NIFTY_AUTO],
    "Midcap 100":    [s + ".NS" for s in NIFTY_MIDCAP_100],
    "Nifty 500":     [s + ".NS" for s in NIFTY_500],
}

# ═══════════════════════════════════════════════════════════════════════════════
# CORE ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

def calc_rsi(close, length=14):
    """Wilder-smoothed RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=length - 1, min_periods=length).mean()
    avg_loss = loss.ewm(com=length - 1, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def find_pivots(highs, lows, left=5, right=5):
    """Return indices of confirmed pivot highs and pivot lows on PRICE.
    Used for Order Block detection."""
    n = len(highs)
    ph_idx, pl_idx = [], []
    h = highs.values
    l = lows.values

    for i in range(left, n - right):
        is_ph = True
        for j in range(i - left, i + right + 1):
            if j != i and h[j] >= h[i]:
                is_ph = False
                break
        if is_ph:
            ph_idx.append(i)

        is_pl = True
        for j in range(i - left, i + right + 1):
            if j != i and l[j] <= l[i]:
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
    r = rsi_values.values

    for i in range(left, n - right):
        # RSI Pivot High
        is_ph = True
        for j in range(i - left, i + right + 1):
            if j != i and r[j] >= r[i]:
                is_ph = False
                break
        if is_ph:
            ph_idx.append(i)

        # RSI Pivot Low
        is_pl = True
        for j in range(i - left, i + right + 1):
            if j != i and r[j] <= r[i]:
                is_pl = False
                break
        if is_pl:
            pl_idx.append(i)

    return ph_idx, pl_idx


def detect_divergences(df, rsi, rsi_ph_idx, rsi_pl_idx, range_lower=5, range_upper=60):
    """
    Matches TradingView RSI Divergence Indicator exactly.
    Pivots are on RSI — price is compared at those same bar indices.

    Regular Bullish:  Price Lower-Low  + RSI Higher-Low  (at RSI pivot lows)
    Hidden Bullish:   Price Higher-Low + RSI Lower-Low   (at RSI pivot lows)
    Regular Bearish:  Price Higher-High + RSI Lower-High  (at RSI pivot highs)
    Hidden Bearish:   Price Lower-High + RSI Higher-High  (at RSI pivot highs)
    """
    reg_bull, hid_bull = [], []
    reg_bear, hid_bear = [], []
    h = df["High"].values
    l = df["Low"].values
    r = rsi.values

    # ── Bullish divergences at RSI pivot lows ──
    for k in range(1, len(rsi_pl_idx)):
        ci, pi = rsi_pl_idx[k], rsi_pl_idx[k - 1]
        if not (range_lower <= (ci - pi) <= range_upper):
            continue

        # Regular Bullish: price LL + RSI HL
        if l[ci] < l[pi] and r[ci] > r[pi]:
            reg_bull.append(ci)

        # Hidden Bullish: price HL + RSI LL
        if l[ci] > l[pi] and r[ci] < r[pi]:
            hid_bull.append(ci)

    # ── Bearish divergences at RSI pivot highs ──
    for k in range(1, len(rsi_ph_idx)):
        ci, pi = rsi_ph_idx[k], rsi_ph_idx[k - 1]
        if not (range_lower <= (ci - pi) <= range_upper):
            continue

        # Regular Bearish: price HH + RSI LH
        if h[ci] > h[pi] and r[ci] < r[pi]:
            reg_bear.append(ci)

        # Hidden Bearish: price LH + RSI HH
        if h[ci] < h[pi] and r[ci] > r[pi]:
            hid_bear.append(ci)

    return reg_bull, reg_bear, hid_bull, hid_bear


def detect_order_blocks(df, ph_idx, pl_idx):
    """
    Bullish OB  → last bearish candle before price breaks above a pivot high.
    Bearish OB  → last bullish candle before price breaks below a pivot low.
    Returns two lists of dicts: [{high, low, bar, breakout_bar}, …]
    """
    c = df["Close"].values
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    n = len(df)

    ph_set = set(ph_idx)
    pl_set = set(pl_idx)

    last_ph_val = None
    last_pl_val = None
    bull_obs, bear_obs = [], []

    for i in range(n):
        if i in ph_set:
            last_ph_val = h[i]
        if i in pl_set:
            last_pl_val = l[i]

        if i == 0:
            continue

        # Break above pivot high → bullish OB
        if last_ph_val is not None and h[i] > last_ph_val and h[i - 1] <= last_ph_val:
            for j in range(i - 1, max(i - 30, -1), -1):
                if c[j] < o[j]:  # bearish candle
                    bull_obs.append({"high": float(h[j]), "low": float(l[j]),
                                     "bar": j, "breakout": i})
                    break

        # Break below pivot low → bearish OB
        if last_pl_val is not None and l[i] < last_pl_val and l[i - 1] >= last_pl_val:
            for j in range(i - 1, max(i - 30, -1), -1):
                if c[j] > o[j]:  # bullish candle
                    bear_obs.append({"high": float(h[j]), "low": float(l[j]),
                                     "bar": j, "breakout": i})
                    break

    return bull_obs, bear_obs


def check_proximity(price, ob_list, threshold):
    """True if price is within threshold% of any recent OB midpoint."""
    for ob in reversed(ob_list[-10:]):
        mid = (ob["high"] + ob["low"]) / 2.0
        if mid > 0 and abs(price - mid) / mid <= threshold:
            return True
    return False


def check_ob_breakout(price, ob_list, confirm_pct, ob_type):
    """
    OB breakout confirmation check.

    Bullish OB  = red candle (e.g. 100–105).
      Confirmed when price closes above OB high + confirm% → price > 105 * 1.01

    Bearish OB  = green candle (e.g. 100–105).
      Confirmed when price closes below OB low − confirm% → price < 100 * 0.99

    Returns (confirmed: bool, ob_dict or None)
    """
    for ob in reversed(ob_list[-10:]):
        if ob_type == "bullish":
            # Bullish OB (red candle) → price must close above OB high + X%
            target = ob["high"] * (1.0 + confirm_pct)
            if price >= target:
                return True, ob
        elif ob_type == "bearish":
            # Bearish OB (green candle) → price must close below OB low − X%
            target = ob["low"] * (1.0 - confirm_pct)
            if price <= target:
                return True, ob
    return False, None


# ═══════════════════════════════════════════════════════════════════════════════
# SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_data(symbol, interval, period):
    """Fetch OHLCV data via yf.Ticker (thread-safe, unlike yf.download)."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(interval=interval, period=period, auto_adjust=True)
    if df.empty:
        return None, None
    # Ensure standard column names
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    # Market cap
    try:
        mcap = ticker.info.get("marketCap")
    except Exception:
        mcap = None
    return df, mcap


def scan_one(symbol, tf_label, rsi_len, pivot_len, ob_prox_pct,
             rsi_div_on=True, ob_on=True, ob_confirm_pct=0.0):
    """Scan a single symbol × timeframe. Returns a result dict.
    rsi_div_on: enable RSI divergence detection
    ob_on: enable Order Block detection
    ob_confirm_pct: OB breakout confirmation % (0 = off)"""
    cfg = TF_CONFIG[tf_label]
    try:
        df, mcap = fetch_data(symbol, cfg["interval"], cfg["period"])
        if df is None or df.empty:
            return None

        needed = rsi_len + pivot_len * 2 + 10
        if len(df) < needed:
            return None

        # RSI (always calculated for display)
        rsi = calc_rsi(df["Close"], rsi_len)
        current_close = float(df["Close"].iloc[-1])
        current_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 0.0

        # ── RSI Divergence ──
        signal = "None"
        div_type = ""
        has_reg_bull = has_hid_bull = has_reg_bear = has_hid_bear = False

        if rsi_div_on:
            rsi_ph_idx, rsi_pl_idx = find_rsi_pivots(rsi, pivot_len, pivot_len)
            if len(rsi_ph_idx) >= 2 or len(rsi_pl_idx) >= 2:
                reg_bull, reg_bear, hid_bull, hid_bear = detect_divergences(
                    df, rsi, rsi_ph_idx, rsi_pl_idx, range_lower=5, range_upper=60
                )
                threshold = len(df) - pivot_len * 5
                has_reg_bull = len(reg_bull) > 0 and reg_bull[-1] >= threshold
                has_hid_bull = len(hid_bull) > 0 and hid_bull[-1] >= threshold
                has_reg_bear = len(reg_bear) > 0 and reg_bear[-1] >= threshold
                has_hid_bear = len(hid_bear) > 0 and hid_bear[-1] >= threshold

        candidates = []
        if has_reg_bull:
            candidates.append(("Bullish", "Regular", reg_bull[-1]))
        if has_hid_bull:
            candidates.append(("Bullish", "Hidden", hid_bull[-1]))
        if has_reg_bear:
            candidates.append(("Bearish", "Regular", reg_bear[-1]))
        if has_hid_bear:
            candidates.append(("Bearish", "Hidden", hid_bear[-1]))

        if candidates:
            candidates.sort(key=lambda x: -x[2])
            signal = candidates[0][0]
            div_type = candidates[0][1]

        # ── Order Blocks ──
        near_bull_ob = False
        near_bear_ob = False
        bull_obs, bear_obs = [], []
        ob_confirmed = False
        ob_confirm_dir = None
        ob_confirm_zone = None

        if ob_on:
            price_ph_idx, price_pl_idx = find_pivots(df["High"], df["Low"], pivot_len, pivot_len)
            bull_obs, bear_obs = detect_order_blocks(df, price_ph_idx, price_pl_idx)
            near_bull_ob = check_proximity(current_close, bull_obs, ob_prox_pct)
            near_bear_ob = check_proximity(current_close, bear_obs, ob_prox_pct)

            # OB Breakout Confirmation
            if ob_confirm_pct > 0:
                # Bullish OB (red candle) → price closed above high + X%
                bull_conf, bull_conf_ob = check_ob_breakout(
                    current_close, bull_obs, ob_confirm_pct, "bullish")
                # Bearish OB (green candle) → price closed below low − X%
                bear_conf, bear_conf_ob = check_ob_breakout(
                    current_close, bear_obs, ob_confirm_pct, "bearish")

                if bull_conf and bull_conf_ob:
                    ob_confirmed = True
                    ob_confirm_dir = "Bullish"
                    ob_confirm_zone = f"{bull_conf_ob['low']:.2f} – {bull_conf_ob['high']:.2f}"
                if bear_conf and bear_conf_ob:
                    ob_confirmed = True
                    ob_confirm_dir = "Bearish"
                    ob_confirm_zone = f"{bear_conf_ob['low']:.2f} – {bear_conf_ob['high']:.2f}"

        # ── Validation logic ──
        validated = False
        if rsi_div_on and ob_on:
            # Both ON → original logic: divergence + near OB
            if signal == "Bullish" and near_bull_ob:
                validated = True
            elif signal == "Bearish" and near_bear_ob:
                validated = True
        elif rsi_div_on and not ob_on:
            # Only RSI → any divergence = validated
            validated = signal != "None"
        elif not rsi_div_on and ob_on:
            # Only OB → near any OB = validated
            validated = near_bull_ob or near_bear_ob
            if near_bull_ob and not near_bear_ob:
                signal = "Bullish"
            elif near_bear_ob and not near_bull_ob:
                signal = "Bearish"
            elif near_bull_ob and near_bear_ob:
                signal = "Bullish"  # default to bullish if both

        # Skip if nothing found based on active features
        if not rsi_div_on and not ob_on:
            return None
        if rsi_div_on and not ob_on and signal == "None":
            return None
        if not rsi_div_on and ob_on and not (near_bull_ob or near_bear_ob):
            return None

        # OB zone details
        ob_zone = None
        if ob_on and (near_bull_ob or near_bear_ob):
            if (signal == "Bullish" or near_bull_ob) and bull_obs:
                ob = bull_obs[-1]
                ob_zone = f"{ob['low']:.2f} – {ob['high']:.2f}"
            elif (signal == "Bearish" or near_bear_ob) and bear_obs:
                ob = bear_obs[-1]
                ob_zone = f"{ob['low']:.2f} – {ob['high']:.2f}"

        return {
            "symbol":        symbol,
            "timeframe":     tf_label,
            "signal":        signal,
            "div_type":      div_type,
            "validated":     validated,
            "near_ob":       near_bull_ob or near_bear_ob,
            "rsi":           round(current_rsi, 1),
            "price":         round(current_close, 2),
            "ob_zone":       ob_zone,
            "mcap":          mcap,
            "ob_confirmed":  ob_confirmed,
            "ob_confirm_dir": ob_confirm_dir,
            "ob_confirm_zone": ob_confirm_zone,
        }

    except Exception:
        traceback.print_exc()
        return None


def run_scan(symbols, timeframes, rsi_len, pivot_len, ob_prox_pct,
             rsi_div_on=True, ob_on=True, ob_confirm_pct=0.0):
    """Scan all symbols × timeframes in parallel."""
    tasks = []
    for sym in symbols:
        for tf in timeframes:
            tasks.append((sym, tf))

    results = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(scan_one, sym, tf, rsi_len, pivot_len, ob_prox_pct,
                        rsi_div_on, ob_on, ob_confirm_pct): (sym, tf)
            for sym, tf in tasks
        }
        for future in as_completed(futures):
            r = future.result()
            if r is not None:
                results.append(r)

    # Sort: validated signals first, then by symbol
    results.sort(key=lambda x: (not x["validated"], x["signal"] == "None", x["symbol"], x["timeframe"]))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html", presets=PRESET_WATCHLISTS)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = req.get_json(force=True)
    symbols    = [s.strip().upper() for s in data.get("symbols", []) if s.strip()]
    timeframes = data.get("timeframes", ["Daily"])
    rsi_len    = int(data.get("rsi_len", 14))
    pivot_len  = int(data.get("pivot_len", 5))
    ob_prox    = float(data.get("ob_prox", 1.0)) / 100.0
    rsi_div_on = bool(data.get("rsi_div_on", True))
    ob_on      = bool(data.get("ob_on", True))
    ob_confirm = float(data.get("ob_confirm", 0.0)) / 100.0

    if not symbols:
        return jsonify({"error": "No symbols provided"}), 400
    if not rsi_div_on and not ob_on:
        return jsonify({"error": "Enable at least one: RSI Divergence or Order Block"}), 400

    results = run_scan(symbols, timeframes, rsi_len, pivot_len, ob_prox,
                       rsi_div_on, ob_on, ob_confirm)
    return jsonify({
        "results": results,
        "scanned": len(symbols) * len(timeframes),
        "signals": sum(1 for r in results if r["signal"] != "None"),
        "validated": sum(1 for r in results if r["validated"]),
        "ob_confirmed_count": sum(1 for r in results if r.get("ob_confirmed")),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/presets")
def api_presets():
    return jsonify(PRESET_WATCHLISTS)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("RENDER") is None  # debug only locally
    print("\n  RSI Divergence × Order Block Screener")
    print(f"  Open http://127.0.0.1:{port} in your browser\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
