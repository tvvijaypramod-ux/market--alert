"""
NIFTY MORNING ALERT — 7:00 AM IST / 3:30 AM Tete
--------------------------------------------------
Sends a final pre-market prediction message to Telegram
before Indian market opens at 9:15 AM IST.

Run this as a SEPARATE script from your existing bot.
Uses same TELEGRAM_TOKEN and TELEGRAM_CHAT_ID env variables.

Schedule: 7:00 AM IST (3:30 AM Tete / CAT)
"""

import yfinance as yf
import requests
import os
from datetime import datetime

# ── TELEGRAM CREDENTIALS (same as your existing bot) ──────────────
TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_msg(text):
    """Send message to Telegram with Markdown formatting."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


# ══════════════════════════════════════════════════════════════════
# 1. NIFTY SPOT — Previous day data for PDH/PDL/Close
# ══════════════════════════════════════════════════════════════════
try:
    nifty      = yf.Ticker("^NSEI").history(period="2d")
    pdh        = nifty['High'].iloc[-2]
    pdl        = nifty['Low'].iloc[-2]
    prev_close = nifty['Close'].iloc[-2]
    spot_now   = nifty['Close'].iloc[-1]
except Exception as e:
    send_msg(f"❌ ERROR fetching Nifty data: {e}")
    exit()

# ══════════════════════════════════════════════════════════════════
# 2. PIVOT POINTS (Standard)
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
    vix_data = yf.Ticker("^INDIAVIX").history(period="1d")
    vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 0
except Exception:
    vix = 0

if vix > 25:
    vix_warn  = "🔴 EXTREME VOLATILITY"
elif vix > 20:
    vix_warn  = "⚠️ HIGH VOLATILITY"
elif vix > 15:
    vix_warn  = "🟡 MODERATE"
else:
    vix_warn  = "✅ STABLE"

# ══════════════════════════════════════════════════════════════════
# 4. GIFT NIFTY — NSE India API with fallback
# ══════════════════════════════════════════════════════════════════
gift_live   = None
gift_source = None

# Attempt 1: NSE India official API
try:
    session = requests.Session()
    # First hit NSE homepage to get cookies
    session.get(
        "https://www.nseindia.com",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=5
    )
    resp = session.get(
        "https://www.nseindia.com/api/equity-stockIndices?index=GIFT%20NIFTY",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com"
        },
        timeout=5
    )
    data = resp.json()
    gift_live   = float(str(data['data'][0]['lastPrice']).replace(',', ''))
    gift_source = "NSE Live"
except Exception:
    pass

# Attempt 2: Yahoo Finance NIFTY Futures (NF=F not always available)
if gift_live is None:
    try:
        nf = yf.Ticker("NIFTY50=F").fast_info
        gift_live   = nf['last_price']
        gift_source = "Yahoo Futures"
    except Exception:
        pass

# Attempt 3: Estimate from Nasdaq/Dow futures movement
if gift_live is None:
    try:
        nq_now  = yf.Ticker("NQ=F").fast_info['last_price']
        nq_hist = yf.Ticker("NQ=F").history(period="2d")
        nq_prev = nq_hist['Close'].iloc[-2]
        nq_pct  = (nq_now - nq_prev) / nq_prev * 100
        # Nifty typically moves ~0.4x Nasdaq on average
        gift_live   = round(prev_close * (1 + (nq_pct * 0.4) / 100), 2)
        gift_source = "⚠️ Estimated (Nasdaq proxy)"
    except Exception:
        gift_live   = prev_close   # Last resort: flat
        gift_source = "⚠️ Unavailable — using prev close"

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
# 6. GLOBAL CUES — Dow & Nasdaq Futures
# ══════════════════════════════════════════════════════════════════
try:
    dow_now  = yf.Ticker("YM=F").fast_info['last_price']
    dow_prev = yf.Ticker("YM=F").history(period="2d")['Close'].iloc[-2]
    dow_chg  = dow_now - dow_prev
    dow_pct  = (dow_chg / dow_prev) * 100
    dow_emoji = "🟢" if dow_chg >= 0 else "🔴"
except Exception:
    dow_chg = dow_pct = 0
    dow_emoji = "⚪"

try:
    nas_now  = yf.Ticker("NQ=F").fast_info['last_price']
    nas_prev = yf.Ticker("NQ=F").history(period="2d")['Close'].iloc[-2]
    nas_chg  = nas_now - nas_prev
    nas_pct  = (nas_chg / nas_prev) * 100
    nas_emoji = "🟢" if nas_chg >= 0 else "🔴"
except Exception:
    nas_chg = nas_pct = 0
    nas_emoji = "⚪"

try:
    sgx_now  = yf.Ticker("ES=F").fast_info['last_price']   # S&P futures
    sgx_prev = yf.Ticker("ES=F").history(period="2d")['Close'].iloc[-2]
    sgx_chg  = sgx_now - sgx_prev
    sgx_emoji = "🟢" if sgx_chg >= 0 else "🔴"
except Exception:
    sgx_chg  = 0
    sgx_emoji = "⚪"

# ══════════════════════════════════════════════════════════════════
# 7. USD/INR
# ══════════════════════════════════════════════════════════════════
try:
    usd_inr     = yf.Ticker("INR=X").fast_info['last_price']
    usd_inr_prev = yf.Ticker("INR=X").history(period="2d")['Close'].iloc[-2]
    inr_chg     = usd_inr - usd_inr_prev
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
    inr_chg  = 0
    inr_note = "⚪ Unavailable"

# ══════════════════════════════════════════════════════════════════
# 8. OPTION CHAIN — PCR (Put-Call Ratio)
# ══════════════════════════════════════════════════════════════════
pcr       = None
oc_source = None
max_pain  = None

try:
    session2 = requests.Session()
    session2.get(
        "https://www.nseindia.com",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=5
    )
    oc_resp = session2.get(
        "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com"
        },
        timeout=8
    )
    oc_data    = oc_resp.json()
    total_ce   = oc_data['filtered']['CE']['totOI']
    total_pe   = oc_data['filtered']['PE']['totOI']
    pcr        = round(total_pe / total_ce, 2) if total_ce > 0 else None
    oc_source  = "NSE Live"

    # Max Pain — strike with highest combined OI (rough calc)
    strikes    = {}
    for item in oc_data['filtered']['data']:
        strike = item.get('strikePrice', 0)
        ce_oi  = item.get('CE', {}).get('openInterest', 0)
        pe_oi  = item.get('PE', {}).get('openInterest', 0)
        strikes[strike] = ce_oi + pe_oi
    if strikes:
        max_pain = max(strikes, key=strikes.get)

except Exception:
    pcr       = None
    oc_source = "Unavailable"

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
        pcr_note = "🔴 Very Bearish (heavy CALL writing)"
    pcr_display = f"{pcr} — {pcr_note}"
else:
    pcr_display = "⚪ Unavailable"

# ══════════════════════════════════════════════════════════════════
# 9. OVERALL DIRECTION BIAS
# ══════════════════════════════════════════════════════════════════
bull_signals = 0
bear_signals = 0

if gap > 30:       bull_signals += 1
if gap < -30:      bear_signals += 1
if dow_chg > 0:    bull_signals += 1
if dow_chg < 0:    bear_signals += 1
if nas_chg > 0:    bull_signals += 1
if nas_chg < 0:    bear_signals += 1
if pcr and pcr >= 1.2:  bull_signals += 1
if pcr and pcr <= 0.8:  bear_signals += 1
if gift_live > pivot:   bull_signals += 1
if gift_live < pivot:   bear_signals += 1

if bull_signals >= 4:
    bias       = "🚀 BULLISH"
    bias_note  = f"{bull_signals}/5 signals bullish — look for long setups above pivot"
elif bear_signals >= 4:
    bias       = "📉 BEARISH"
    bias_note  = f"{bear_signals}/5 signals bearish — look for short setups below pivot"
elif bull_signals > bear_signals:
    bias       = "🟡 CAUTIOUSLY BULLISH"
    bias_note  = "Mixed signals — wait for 9:20 AM candle confirmation"
elif bear_signals > bull_signals:
    bias       = "🟡 CAUTIOUSLY BEARISH"
    bias_note  = "Mixed signals — wait for 9:20 AM candle confirmation"
else:
    bias       = "⚖️ NEUTRAL/SIDEWAYS"
    bias_note  = "No clear edge — avoid aggressive positions at open"

# ══════════════════════════════════════════════════════════════════
# 10. BUILD & SEND MESSAGE
# ══════════════════════════════════════════════════════════════════
now_ist  = datetime.utcnow()
now_tete = now_ist  # UTC+2 handled by scheduler

max_pain_line = f"🎯 *Max Pain:* {max_pain}" if max_pain else ""

msg = f"""
🌅 *NIFTY FINAL PRE\-MARKET REPORT*
📍 7:00 AM IST \| 3:30 AM Tete
━━━━━━━━━━━━━━━━━━━━
*Overall Bias:* {bias}
_{bias_note}_

*Expected Open:* {gap_label}
🎯 *Est\. Nifty Open:* `{est_open:.2f}`
📍 *Prev Close:* `{prev_close:.2f}`
🎁 *Gift Nifty:* `{gift_live:.2f}` _\({gift_source}\)_
📐 *Gap:* `{gap:+.2f} pts \({gap_pct:+.2f}%\)`
━━━━━━━━━━━━━━━━━━━━
🌍 *GLOBAL CUES \(Overnight\):*
{dow_emoji} Dow Futures: `{dow_chg:+.0f} pts \({dow_pct:+.2f}%\)`
{nas_emoji} Nasdaq Futures: `{nas_chg:+.0f} pts \({nas_pct:+.2f}%\)`
{sgx_emoji} S&P 500 Futures: `{sgx_chg:+.0f} pts`
💵 USD/INR: `{usd_inr:.2f}` — {inr_note}
━━━━━━━━━━━━━━━━━━━━
📊 *OPTION CHAIN \({oc_source}\):*
📈 PCR: {pcr_display}
{max_pain_line}
━━━━━━━━━━━━━━━━━━━━
📐 *KEY LEVELS:*
• R2: `{r2:.2f}`
• R1: `{r1:.2f}`
• Pivot: `{pivot:.2f}`
• S1: `{s1:.2f}`
• S2: `{s2:.2f}`
• PDH: `{pdh:.2f}`
• PDL: `{pdl:.2f}`

📉 India VIX: `{vix:.2f}` {vix_warn}
━━━━━━━━━━━━━━━━━━━━
⚡ *TRADE RULES:*
• Gap >50pts → wait for gap fill before entry
• Below PDL → no longs
• Above PDH → momentum trade only
• VIX >20 → reduce position size
• Confirm with 9:20 AM candle always
"""

send_msg(msg)
print("✅ Morning alert sent successfully!")
