"""
NIFTY MORNING ALERT — 7:00 AM IST / 5:00 AM Tete
--------------------------------------------------
Fixed version:
- HTML parse mode (no more escape issues)
- Proper fallback for US futures when markets are closed
- Better NSE session handling for PCR/Gift Nifty
- Clean message formatting
"""

import yfinance as yf
import requests
import os
from datetime import datetime

# ── TELEGRAM CREDENTIALS ──────────────────────────────────────────
TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_msg(text):
    """Send message to Telegram with HTML formatting."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        print(f"Telegram response: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"Telegram error: {e}")


def safe_ticker_price(symbol):
    """Safely get last price using history — works even when market closed."""
    try:
        hist = yf.Ticker(symbol).history(period="2d")
        if len(hist) >= 2:
            return hist['Close'].iloc[-1], hist['Close'].iloc[-2]
        elif len(hist) == 1:
            return hist['Close'].iloc[-1], hist['Close'].iloc[-1]
    except Exception:
        pass
    return None, None


def get_nse_session():
    """Create NSE session with proper headers."""
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com",
        "Connection": "keep-alive",
    }
    session.headers.update(headers)
    try:
        session.get("https://www.nseindia.com", timeout=8)
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=8)
    except Exception:
        pass
    return session


# ══════════════════════════════════════════════════════════════════
# 1. NIFTY SPOT — PDH / PDL / Close
# ══════════════════════════════════════════════════════════════════
try:
    nifty      = yf.Ticker("^NSEI").history(period="5d")
    pdh        = nifty['High'].iloc[-2]
    pdl        = nifty['Low'].iloc[-2]
    prev_close = nifty['Close'].iloc[-2]
    spot_now   = nifty['Close'].iloc[-1]
except Exception as e:
    send_msg(f"ERROR fetching Nifty data: {e}")
    exit()

# ══════════════════════════════════════════════════════════════════
# 2. PIVOT POINTS
# ══════════════════════════════════════════════════════════════════
pivot = (pdh + pdl + prev_close) / 3
r1    = (2 * pivot) - pdl
r2    = pivot + (pdh - pdl)
s1    = (2 * pivot) - pdh
s2    = pivot - (pdh - pdl)

# ══════════════════════════════════════════════════════════════════
# 3. INDIA VIX
# ══════════════════════════════════════════════════════════════════
try:
    vix_data = yf.Ticker("^INDIAVIX").history(period="2d")
    vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 0
except Exception:
    vix = 0

if vix > 25:
    vix_warn = "🔴 EXTREME VOLATILITY"
elif vix > 20:
    vix_warn = "⚠️ HIGH VOLATILITY"
elif vix > 15:
    vix_warn = "🟡 MODERATE"
else:
    vix_warn = "✅ STABLE"

# ══════════════════════════════════════════════════════════════════
# 4. GIFT NIFTY
# ══════════════════════════════════════════════════════════════════
gift_live   = None
gift_source = None

# Attempt 1: NSE India API
try:
    session = get_nse_session()
    resp = session.get(
        "https://www.nseindia.com/api/equity-stockIndices?index=GIFT%20NIFTY",
        timeout=8
    )
    data = resp.json()
    gift_live   = float(str(data['data'][0]['lastPrice']).replace(',', ''))
    gift_source = "NSE Live"
except Exception:
    pass

# Attempt 2: Yahoo Finance SGX Nifty
if gift_live is None:
    try:
        val, _ = safe_ticker_price("NIFTY50=F")
        if val:
            gift_live   = val
            gift_source = "Yahoo Futures"
    except Exception:
        pass

# Attempt 3: Nasdaq proxy estimate
if gift_live is None:
    try:
        nq_now, nq_prev = safe_ticker_price("NQ=F")
        if nq_now and nq_prev and nq_prev != 0:
            nq_pct      = (nq_now - nq_prev) / nq_prev * 100
            gift_live   = round(prev_close * (1 + (nq_pct * 0.4) / 100), 2)
            gift_source = "Estimated (Nasdaq proxy)"
    except Exception:
        pass

# Fallback
if gift_live is None:
    gift_live   = prev_close
    gift_source = "Unavailable — using prev close"

# ══════════════════════════════════════════════════════════════════
# 5. GAP & ESTIMATED OPEN
# ══════════════════════════════════════════════════════════════════
gap      = gift_live - prev_close
gap_pct  = (gap / prev_close) * 100
est_open = round(prev_close + gap, 2)

if gap > 50:
    gap_label = "🟢 BIG GAP UP"
elif gap > 15:
    gap_label = "🟢 GAP UP"
elif gap < -50:
    gap_label = "🔴 BIG GAP DOWN"
elif gap < -15:
    gap_label = "🔴 GAP DOWN"
else:
    gap_label = "⚪ FLAT OPEN"

# ══════════════════════════════════════════════════════════════════
# 6. GLOBAL CUES — uses history() not fast_info (works when closed)
# ══════════════════════════════════════════════════════════════════
def get_futures_change(symbol):
    """Get price change using history — reliable even when market closed."""
    try:
        now, prev = safe_ticker_price(symbol)
        if now is not None and prev is not None and prev != 0:
            chg = now - prev
            pct = (chg / prev) * 100
            emoji = "🟢" if chg >= 0 else "🔴"
            return chg, pct, emoji
    except Exception:
        pass
    return None, None, "⚪"

dow_chg, dow_pct, dow_emoji = get_futures_change("YM=F")
nas_chg, nas_pct, nas_emoji = get_futures_change("NQ=F")
sgx_chg, sgx_pct, sgx_emoji = get_futures_change("ES=F")

def fmt_futures(chg, pct, emoji, label):
    if chg is not None:
        return f"{emoji} {label}: {chg:+.0f} pts ({pct:+.2f}%)"
    return f"⚪ {label}: Unavailable"

dow_line = fmt_futures(dow_chg, dow_pct, dow_emoji, "Dow Futures")
nas_line = fmt_futures(nas_chg, nas_pct, nas_emoji, "Nasdaq Futures")
sgx_line = fmt_futures(sgx_chg, sgx_pct, sgx_emoji, "S&P 500 Futures")

# ══════════════════════════════════════════════════════════════════
# 7. USD/INR
# ══════════════════════════════════════════════════════════════════
try:
    usd_inr, usd_inr_prev = safe_ticker_price("INR=X")
    if usd_inr is None:
        usd_inr = 0
    inr_chg = (usd_inr - usd_inr_prev) if usd_inr_prev else 0
    if usd_inr > 85.0:
        inr_note = "🔴 Very Weak Rupee — FII selling likely"
    elif usd_inr > 84.5:
        inr_note = "⚠️ Weak Rupee — watch FII flows"
    elif inr_chg < -0.2:
        inr_note = "🟢 Rupee strengthening — FII buying signal"
    else:
        inr_note = "✅ Stable"
except Exception:
    usd_inr  = 0
    inr_note = "⚪ Unavailable"

# ══════════════════════════════════════════════════════════════════
# 8. OPTION CHAIN — PCR + Max Pain
# ══════════════════════════════════════════════════════════════════
pcr       = None
oc_source = "Unavailable"
max_pain  = None

try:
    session2 = get_nse_session()
    oc_resp = session2.get(
        "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
        timeout=10
    )
    oc_data  = oc_resp.json()
    total_ce = oc_data['filtered']['CE']['totOI']
    total_pe = oc_data['filtered']['PE']['totOI']
    pcr      = round(total_pe / total_ce, 2) if total_ce > 0 else None
    oc_source = "NSE Live"

    # Max Pain calculation
    strikes = {}
    for item in oc_data['filtered']['data']:
        strike = item.get('strikePrice', 0)
        ce_oi  = item.get('CE', {}).get('openInterest', 0)
        pe_oi  = item.get('PE', {}).get('openInterest', 0)
        strikes[strike] = ce_oi + pe_oi
    if strikes:
        max_pain = max(strikes, key=strikes.get)

except Exception as e:
    print(f"NSE OC error: {e}")

# PCR interpretation
if pcr is not None:
    if pcr >= 1.5:
        pcr_note = "🟢 Very Bullish (heavy PUT writing)"
    elif pcr >= 1.2:
        pcr_note = "🟢 Bullish"
    elif pcr >= 0.8:
        pcr_note = "⚖️ Neutral"
    elif pcr >= 0.5:
        pcr_note = "🔴 Bearish"
    else:
        pcr_note = "🔴 Very Bearish"
    pcr_display = f"{pcr} — {pcr_note}"
else:
    pcr_display = "⚪ Unavailable"

# ══════════════════════════════════════════════════════════════════
# 9. OVERALL BIAS
# ══════════════════════════════════════════════════════════════════
bull_signals = 0
bear_signals = 0

if gap > 30:                    bull_signals += 1
if gap < -30:                   bear_signals += 1
if dow_chg and dow_chg > 0:    bull_signals += 1
if dow_chg and dow_chg < 0:    bear_signals += 1
if nas_chg and nas_chg > 0:    bull_signals += 1
if nas_chg and nas_chg < 0:    bear_signals += 1
if pcr and pcr >= 1.2:         bull_signals += 1
if pcr and pcr <= 0.8:         bear_signals += 1
if gift_live > pivot:           bull_signals += 1
if gift_live < pivot:           bear_signals += 1

if bull_signals >= 4:
    bias      = "🚀 BULLISH"
    bias_note = f"{bull_signals}/5 signals bullish — look for long setups above pivot"
elif bear_signals >= 4:
    bias      = "📉 BEARISH"
    bias_note = f"{bear_signals}/5 signals bearish — look for short setups below pivot"
elif bull_signals > bear_signals:
    bias      = "🟡 CAUTIOUSLY BULLISH"
    bias_note = "Mixed signals — wait for 9:20 AM candle confirmation"
elif bear_signals > bull_signals:
    bias      = "🟡 CAUTIOUSLY BEARISH"
    bias_note = "Mixed signals — wait for 9:20 AM candle confirmation"
else:
    bias      = "⚖️ NEUTRAL/SIDEWAYS"
    bias_note = "No clear edge — avoid aggressive positions at open"

# ══════════════════════════════════════════════════════════════════
# 10. BUILD & SEND MESSAGE (HTML parse mode — no escaping needed)
# ══════════════════════════════════════════════════════════════════
max_pain_line = f"🎯 Max Pain: <code>{max_pain}</code>" if max_pain else ""

msg = f"""🌅 <b>NIFTY FINAL PRE-MARKET REPORT</b>
📍 7:00 AM IST | 5:00 AM Tete
━━━━━━━━━━━━━━━━━━━━
<b>Overall Bias:</b> {bias}
<i>{bias_note}</i>

<b>Expected Open:</b> {gap_label}
🎯 <b>Est. Nifty Open:</b> <code>{est_open:.2f}</code>
📍 <b>Prev Close:</b> <code>{prev_close:.2f}</code>
🎁 <b>Gift Nifty:</b> <code>{gift_live:.2f}</code> <i>({gift_source})</i>
📐 <b>Gap:</b> <code>{gap:+.2f} pts ({gap_pct:+.2f}%)</code>
━━━━━━━━━━━━━━━━━━━━
🌍 <b>GLOBAL CUES (Overnight):</b>
{dow_line}
{nas_line}
{sgx_line}
💵 USD/INR: <code>{usd_inr:.2f}</code> — {inr_note}
━━━━━━━━━━━━━━━━━━━━
📊 <b>OPTION CHAIN ({oc_source}):</b>
📈 PCR: {pcr_display}
{max_pain_line}
━━━━━━━━━━━━━━━━━━━━
📐 <b>KEY LEVELS:</b>
• R2: <code>{r2:.2f}</code>
• R1: <code>{r1:.2f}</code>
• Pivot: <code>{pivot:.2f}</code>
• S1: <code>{s1:.2f}</code>
• S2: <code>{s2:.2f}</code>
• PDH: <code>{pdh:.2f}</code>
• PDL: <code>{pdl:.2f}</code>

📉 India VIX: <code>{vix:.2f}</code> {vix_warn}
━━━━━━━━━━━━━━━━━━━━
⚡ <b>TRADE RULES:</b>
• Gap &gt;50pts → wait for gap fill before entry
• Below PDL → no longs
• Above PDH → momentum trade only
• VIX &gt;20 → reduce position size
• Confirm with 9:20 AM candle always"""

send_msg(msg)
print("Morning alert sent successfully!")
