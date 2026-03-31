"""
NIFTY OPTION CHAIN ALERT — 9:30 AM IST / 6:00 AM Tete
-------------------------------------------------------
Sends option chain analysis AFTER opening volatility settles.
Completely separate from existing bots — safe to run independently.

Schedule: 9:30 AM IST (6:00 AM Tete / CAT = UTC 04:00)
Uses same TELEGRAM_TOKEN and TELEGRAM_CHAT_ID env variables.
"""

import yfinance as yf
import requests
import os
from datetime import datetime

# ── TELEGRAM CREDENTIALS ───────────────────────────────────────────
TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_msg(text):
    """Send HTML formatted message to Telegram."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        return resp
    except Exception as e:
        print(f"Telegram error: {e}")


# ══════════════════════════════════════════════════════════════════
# 1. NIFTY SPOT — current live price
# ══════════════════════════════════════════════════════════════════
try:
    nifty_ticker = yf.Ticker("^NSEI")
    nifty_hist   = nifty_ticker.history(period="2d")
    spot         = nifty_hist['Close'].iloc[-1]
    prev_close   = nifty_hist['Close'].iloc[-2]
    spot_change  = spot - prev_close
    spot_pct     = (spot_change / prev_close) * 100
    spot_emoji   = "🟢" if spot_change >= 0 else "🔴"
except Exception as e:
    send_msg(f"❌ ERROR fetching Nifty spot: {e}")
    exit()

# ══════════════════════════════════════════════════════════════════
# 2. OPTION CHAIN — NSE API with full browser headers
# ══════════════════════════════════════════════════════════════════
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

oc_data   = None
oc_status = "❌ NSE Unavailable"

try:
    session = requests.Session()
    # Step 1: homepage cookies
    session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
    # Step 2: option chain page cookies
    session.get("https://www.nseindia.com/option-chain", headers=NSE_HEADERS, timeout=8)
    # Step 3: actual API call
    resp = session.get(
        "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
        headers=NSE_HEADERS,
        timeout=10
    )
    oc_data   = resp.json()
    oc_status = "✅ NSE Live"
    print("Option chain fetched successfully")
except Exception as ex:
    print(f"NSE fetch error: {ex}")

# ══════════════════════════════════════════════════════════════════
# 3. PARSE OPTION CHAIN DATA
# ══════════════════════════════════════════════════════════════════
if oc_data:
    try:
        # ── Total OI ──────────────────────────────────────────────
        total_ce_oi = oc_data['filtered']['CE']['totOI']
        total_pe_oi = oc_data['filtered']['PE']['totOI']
        total_ce_chg = oc_data['filtered']['CE'].get('totChgOI', 0)
        total_pe_chg = oc_data['filtered']['PE'].get('totChgOI', 0)
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0

        # ── Per Strike Analysis ───────────────────────────────────
        ce_oi_map     = {}   # strike → CE OI
        pe_oi_map     = {}   # strike → PE OI
        ce_chg_map    = {}   # strike → CE OI change
        pe_chg_map    = {}   # strike → PE OI change

        for item in oc_data['filtered']['data']:
            strike = item.get('strikePrice', 0)
            ce     = item.get('CE', {})
            pe     = item.get('PE', {})

            ce_oi_map[strike]  = ce.get('openInterest', 0)
            pe_oi_map[strike]  = pe.get('openInterest', 0)
            ce_chg_map[strike] = ce.get('changeinOpenInterest', 0)
            pe_chg_map[strike] = pe.get('changeinOpenInterest', 0)

        # ── Key Strikes ───────────────────────────────────────────
        # Highest OI = strongest wall
        max_ce_strike = max(ce_oi_map, key=ce_oi_map.get)   # resistance wall
        max_pe_strike = max(pe_oi_map, key=pe_oi_map.get)   # support wall

        # Highest OI Change = fresh smart money
        max_ce_chg_strike = max(ce_chg_map, key=ce_chg_map.get)
        max_pe_chg_strike = max(pe_chg_map, key=pe_chg_map.get)

        max_ce_oi     = ce_oi_map[max_ce_strike]
        max_pe_oi     = pe_oi_map[max_pe_strike]
        max_ce_chg    = ce_chg_map[max_ce_chg_strike]
        max_pe_chg    = pe_chg_map[max_pe_chg_strike]

        # ── Max Pain ──────────────────────────────────────────────
        all_strikes = {}
        for item in oc_data['filtered']['data']:
            strike = item.get('strikePrice', 0)
            ce_oi  = item.get('CE', {}).get('openInterest', 0)
            pe_oi  = item.get('PE', {}).get('openInterest', 0)
            all_strikes[strike] = ce_oi + pe_oi
        max_pain = max(all_strikes, key=all_strikes.get) if all_strikes else None

        # ── Straddle Center ───────────────────────────────────────
        straddle_center = round((max_ce_strike + max_pe_strike) / 2)

        # ── Top 3 CE & PE OI strikes ─────────────────────────────
        top3_ce = sorted(ce_oi_map, key=ce_oi_map.get, reverse=True)[:3]
        top3_pe = sorted(pe_oi_map, key=pe_oi_map.get, reverse=True)[:3]

        oc_parsed = True

    except Exception as ex:
        print(f"Parse error: {ex}")
        oc_parsed = False
else:
    oc_parsed = False

# ══════════════════════════════════════════════════════════════════
# 4. TRADE SUGGESTION LOGIC
# ══════════════════════════════════════════════════════════════════
if oc_parsed:
    # Distance from key walls
    dist_from_ce = max_ce_strike - spot   # positive = resistance above
    dist_from_pe = spot - max_pe_strike   # positive = support below

    # ── PCR Sentiment ─────────────────────────────────────────────
    if pcr >= 1.5:
        pcr_note  = "🟢 Very Bullish"
        pcr_color = "🟢"
    elif pcr >= 1.2:
        pcr_note  = "🟢 Bullish"
        pcr_color = "🟢"
    elif pcr >= 0.8:
        pcr_note  = "⚖️ Neutral"
        pcr_color = "🟡"
    elif pcr >= 0.5:
        pcr_note  = "🔴 Bearish"
        pcr_color = "🔴"
    else:
        pcr_note  = "🔴 Very Bearish"
        pcr_color = "🔴"

    # ── Spot vs Max Pain ──────────────────────────────────────────
    if max_pain:
        pain_diff = spot - max_pain
        if pain_diff > 100:
            pain_note = f"⬇️ Spot {pain_diff:.0f} pts ABOVE Max Pain — gravity pull down"
        elif pain_diff < -100:
            pain_note = f"⬆️ Spot {abs(pain_diff):.0f} pts BELOW Max Pain — gravity pull up"
        else:
            pain_note = f"↔️ Spot near Max Pain — sideways expiry likely"
    else:
        pain_note = "N/A"

    # ── Trade Zone ────────────────────────────────────────────────
    if spot > max_ce_strike:
        zone       = "🚀 BREAKOUT ZONE"
        zone_note  = f"Spot broke above resistance {max_ce_strike} — strong bullish momentum"
        trade_bias = "BUY CE or ride momentum"
    elif spot < max_pe_strike:
        zone       = "💥 BREAKDOWN ZONE"
        zone_note  = f"Spot broke below support {max_pe_strike} — strong bearish momentum"
        trade_bias = "BUY PE or ride momentum down"
    elif dist_from_ce < 50:
        zone       = "⚠️ NEAR RESISTANCE"
        zone_note  = f"Only {dist_from_ce:.0f} pts from CE wall at {max_ce_strike} — breakout watch"
        trade_bias = "Wait — buy CE only on breakout above"
    elif dist_from_pe < 50:
        zone       = "⚠️ NEAR SUPPORT"
        zone_note  = f"Only {dist_from_pe:.0f} pts from PE wall at {max_pe_strike} — breakdown watch"
        trade_bias = "Wait — buy PE only on breakdown below"
    else:
        zone       = "↔️ RANGE ZONE"
        zone_note  = f"Spot between PE wall ({max_pe_strike}) and CE wall ({max_ce_strike})"
        trade_bias = f"Sell straddle at {straddle_center} or trade the range"

    # ── Danger Zones ──────────────────────────────────────────────
    danger_ce = "🔴 BREAKOUT ALERT" if dist_from_ce < 50 else f"{dist_from_ce:.0f} pts away"
    danger_pe = "🔴 BREAKDOWN ALERT" if dist_from_pe < 50 else f"{dist_from_pe:.0f} pts away"

    # ── Fresh Money Signal ────────────────────────────────────────
    if max_ce_chg > max_pe_chg:
        fresh_note = f"🐻 Bears adding at {max_ce_chg_strike} CE ({max_ce_chg:,.0f} OI added)"
    else:
        fresh_note = f"🐂 Bulls adding at {max_pe_chg_strike} PE ({max_pe_chg:,.0f} OI added)"

# ══════════════════════════════════════════════════════════════════
# 5. BUILD MESSAGE
# ══════════════════════════════════════════════════════════════════
now = datetime.utcnow().strftime("%d %b %Y")

if oc_parsed:
    top_ce_lines = "\n".join(
        [f"  • {s}: <code>{ce_oi_map[s]:,.0f}</code>" for s in top3_ce]
    )
    top_pe_lines = "\n".join(
        [f"  • {s}: <code>{pe_oi_map[s]:,.0f}</code>" for s in top3_pe]
    )

    msg = f"""📊 <b>NIFTY OPTION CHAIN REPORT</b>
📅 {now} | 9:30 AM IST | 6:00 AM Tete
{oc_status}
━━━━━━━━━━━━━━━━━━━━
{spot_emoji} <b>Nifty Spot:</b> <code>{spot:.2f}</code>
   Change: <code>{spot_change:+.2f} ({spot_pct:+.2f}%)</code> vs prev close

━━━━━━━━━━━━━━━━━━━━
🧱 <b>OI WALLS (Smart Money):</b>
🔴 <b>Resistance (CE wall):</b> <code>{max_ce_strike}</code>
   OI: <code>{max_ce_oi:,.0f}</code> | {danger_ce}
🟢 <b>Support (PE wall):</b> <code>{max_pe_strike}</code>
   OI: <code>{max_pe_oi:,.0f}</code> | {danger_pe}

🎯 <b>Max Pain:</b> <code>{max_pain}</code>
   {pain_note}
↔️ <b>Straddle Center:</b> <code>{straddle_center}</code>

━━━━━━━━━━━━━━━━━━━━
📈 <b>TOP 3 RESISTANCE STRIKES (CE OI):</b>
{top_ce_lines}

📉 <b>TOP 3 SUPPORT STRIKES (PE OI):</b>
{top_pe_lines}

━━━━━━━━━━━━━━━━━━━━
💰 <b>FRESH MONEY (OI Change):</b>
{fresh_note}
📊 Total CE OI: <code>{total_ce_oi:,.0f}</code>
📊 Total PE OI: <code>{total_pe_oi:,.0f}</code>
📊 PCR: <code>{pcr}</code> — {pcr_note}

━━━━━━━━━━━━━━━━━━━━
🎯 <b>TRADE ZONE:</b> {zone}
<i>{zone_note}</i>

⚡ <b>BEST TRADE NOW:</b>
{trade_bias}

━━━━━━━━━━━━━━━━━━━━
⚠️ <b>RULES:</b>
• Never trade against the OI wall
• If spot breaks CE wall → buy CE aggressively
• If spot breaks PE wall → buy PE aggressively
• In range → sell options, don't buy
• Always use stop loss = 20% of premium
"""

else:
    # NSE unavailable — still send spot price at least
    msg = f"""📊 <b>NIFTY OPTION CHAIN REPORT</b>
📅 {now} | 9:30 AM IST | 6:00 AM Tete
❌ NSE Option Chain Unavailable

━━━━━━━━━━━━━━━━━━━━
{spot_emoji} <b>Nifty Spot:</b> <code>{spot:.2f}</code>
   Change: <code>{spot_change:+.2f} ({spot_pct:+.2f}%)</code>

⚠️ NSE API blocked from server.
Check option chain manually at:
nseindia.com/option-chain
"""

send_msg(msg)
print("✅ Option chain alert sent!")
