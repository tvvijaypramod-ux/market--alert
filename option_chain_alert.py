"""
NIFTY OPTION CHAIN ALERT — 9:30 AM IST / 6:00 AM Tete
-------------------------------------------------------
Uses nselib library to bypass NSE IP blocking.
Runs 7 times daily during market hours.
"""

import yfinance as yf
import requests
import os
import time
import pandas as pd
from datetime import datetime

try:
    from nselib import derivatives
    NSELIB_AVAILABLE = True
except ImportError:
    NSELIB_AVAILABLE = False

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

try:
    nifty_hist  = yf.Ticker("^NSEI").history(period="2d")
    spot        = nifty_hist['Close'].iloc[-1]
    prev_close  = nifty_hist['Close'].iloc[-2]
    spot_change = spot - prev_close
    spot_pct    = (spot_change / prev_close) * 100
    spot_emoji  = "🟢" if spot_change >= 0 else "🔴"
except Exception as e:
    send_msg(f"❌ ERROR fetching Nifty spot: {e}")
    exit()

oc_data   = None
oc_status = "❌ Unavailable"
oc_format = None

if NSELIB_AVAILABLE:
    for attempt in range(3):
        try:
            time.sleep(2)
            raw = derivatives.nse_live_option_chain(symbol="NIFTY", expiry_date=None)
            if raw is not None and not raw.empty:
                oc_data   = raw
                oc_status = "✅ NSE Live"
                oc_format = "dataframe"
                print(f"nselib success on attempt {attempt+1}")
                break
        except Exception as ex:
            print(f"nselib attempt {attempt+1} failed: {ex}")
            time.sleep(3)

if oc_data is None:
    NSE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
        "Connection": "keep-alive",
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        time.sleep(2)
        session.get("https://www.nseindia.com/option-chain", headers=NSE_HEADERS, timeout=8)
        time.sleep(2)
        resp      = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            headers=NSE_HEADERS, timeout=10
        )
        oc_data   = resp.json()
        oc_status = "✅ NSE Live"
        oc_format = "dict"
        print("Direct NSE fetch success")
    except Exception as ex:
        print(f"Direct NSE failed: {ex}")

oc_parsed  = False
ce_oi_map  = {}
pe_oi_map  = {}
ce_chg_map = {}
pe_chg_map = {}

if oc_data is not None:
    try:
        if oc_format == "dataframe":
            df = oc_data
            for _, row in df.iterrows():
                strike = float(row.get('Strike Price', 0))
                ce_oi_map[strike]  = float(row.get('CALLS_OI', 0) or 0)
                pe_oi_map[strike]  = float(row.get('PUTS_OI', 0) or 0)
                ce_chg_map[strike] = float(row.get('CALLS_Chng_in_OI', 0) or 0)
                pe_chg_map[strike] = float(row.get('PUTS_Chng_in_OI', 0) or 0)
            total_ce_oi = sum(ce_oi_map.values())
            total_pe_oi = sum(pe_oi_map.values())
        elif oc_format == "dict":
            total_ce_oi = oc_data['filtered']['CE']['totOI']
            total_pe_oi = oc_data['filtered']['PE']['totOI']
            for item in oc_data['filtered']['data']:
                strike = item.get('strikePrice', 0)
                ce     = item.get('CE', {})
                pe     = item.get('PE', {})
                ce_oi_map[strike]  = ce.get('openInterest', 0)
                pe_oi_map[strike]  = pe.get('openInterest', 0)
                ce_chg_map[strike] = ce.get('changeinOpenInterest', 0)
                pe_chg_map[strike] = pe.get('changeinOpenInterest', 0)

        pcr               = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0
        max_ce_strike     = max(ce_oi_map, key=ce_oi_map.get)
        max_pe_strike     = max(pe_oi_map, key=pe_oi_map.get)
        max_ce_chg_strike = max(ce_chg_map, key=ce_chg_map.get)
        max_pe_chg_strike = max(pe_chg_map, key=pe_chg_map.get)
        max_ce_oi         = ce_oi_map[max_ce_strike]
        max_pe_oi         = pe_oi_map[max_pe_strike]
        max_ce_chg        = ce_chg_map[max_ce_chg_strike]
        max_pe_chg        = pe_chg_map[max_pe_chg_strike]
        all_strikes       = {s: ce_oi_map.get(s,0) + pe_oi_map.get(s,0)
                             for s in set(ce_oi_map)|set(pe_oi_map)}
        max_pain          = max(all_strikes, key=all_strikes.get) if all_strikes else None
        straddle_center   = round((max_ce_strike + max_pe_strike) / 2)
        top3_ce           = sorted(ce_oi_map, key=ce_oi_map.get, reverse=True)[:3]
        top3_pe           = sorted(pe_oi_map, key=pe_oi_map.get, reverse=True)[:3]
        oc_parsed         = True
    except Exception as ex:
        print(f"Parse error: {ex}")

if oc_parsed:
    dist_from_ce = max_ce_strike - spot
    dist_from_pe = spot - max_pe_strike

    if pcr >= 1.5:   pcr_note = "🟢 Very Bullish"
    elif pcr >= 1.2: pcr_note = "🟢 Bullish"
    elif pcr >= 0.8: pcr_note = "⚖️ Neutral"
    elif pcr >= 0.5: pcr_note = "🔴 Bearish"
    else:            pcr_note = "🔴 Very Bearish"

    if max_pain:
        pain_diff = spot - max_pain
        if pain_diff > 100:
            pain_note = f"⬇️ {pain_diff:.0f} pts ABOVE Max Pain — pull down likely"
        elif pain_diff < -100:
            pain_note = f"⬆️ {abs(pain_diff):.0f} pts BELOW Max Pain — pull up likely"
        else:
            pain_note = "↔️ Near Max Pain — sideways expiry likely"
    else:
        pain_note = "N/A"

    if spot > max_ce_strike:
        zone = "🚀 BREAKOUT ZONE"
        zone_note  = f"Spot broke above CE wall {int(max_ce_strike)}"
        trade_bias = "BUY CE — ride the momentum"
    elif spot < max_pe_strike:
        zone = "💥 BREAKDOWN ZONE"
        zone_note  = f"Spot broke below PE wall {int(max_pe_strike)}"
        trade_bias = "BUY PE — ride the momentum down"
    elif dist_from_ce < 50:
        zone = "⚠️ NEAR RESISTANCE"
        zone_note  = f"Only {dist_from_ce:.0f} pts from CE wall {int(max_ce_strike)}"
        trade_bias = "WAIT — buy CE only on clean breakout"
    elif dist_from_pe < 50:
        zone = "⚠️ NEAR SUPPORT"
        zone_note  = f"Only {dist_from_pe:.0f} pts from PE wall {int(max_pe_strike)}"
        trade_bias = "WAIT — buy PE only on clean breakdown"
    else:
        zone = "↔️ RANGE ZONE"
        zone_note  = f"Between PE wall ({int(max_pe_strike)}) and CE wall ({int(max_ce_strike)})"
        trade_bias = f"SELL straddle at {straddle_center} — range trade"

    danger_ce  = "🔴 BREAKOUT ALERT" if dist_from_ce < 50 else f"{dist_from_ce:.0f} pts away"
    danger_pe  = "🔴 BREAKDOWN ALERT" if dist_from_pe < 50 else f"{dist_from_pe:.0f} pts away"
    fresh_note = (f"🐻 Bears adding at {int(max_ce_chg_strike)} CE ({max_ce_chg:,.0f} fresh OI)"
                  if max_ce_chg > max_pe_chg else
                  f"🐂 Bulls adding at {int(max_pe_chg_strike)} PE ({max_pe_chg:,.0f} fresh OI)")

now = datetime.utcnow().strftime("%d %b %Y %I:%M %p UTC")

if oc_parsed:
    top_ce_lines = "\n".join([f"  • {int(s)}: <code>{ce_oi_map[s]:,.0f}</code>" for s in top3_ce])
    top_pe_lines = "\n".join([f"  • {int(s)}: <code>{pe_oi_map[s]:,.0f}</code>" for s in top3_pe])
    msg = f"""📊 <b>NIFTY OPTION CHAIN REPORT</b>
🕐 {now}
{oc_status}
━━━━━━━━━━━━━━━━━━━━
{spot_emoji} <b>Nifty Spot:</b> <code>{spot:.2f}</code>
   Change: <code>{spot_change:+.2f} ({spot_pct:+.2f}%)</code>
━━━━━━━━━━━━━━━━━━━━
🧱 <b>OI WALLS (Smart Money):</b>
🔴 <b>CE Wall (Resistance):</b> <code>{int(max_ce_strike)}</code>
   OI: <code>{max_ce_oi:,.0f}</code> | {danger_ce}
🟢 <b>PE Wall (Support):</b> <code>{int(max_pe_strike)}</code>
   OI: <code>{max_pe_oi:,.0f}</code> | {danger_pe}

🎯 <b>Max Pain:</b> <code>{int(max_pain) if max_pain else 'N/A'}</code>
   {pain_note}
↔️ <b>Straddle Center:</b> <code>{straddle_center}</code>
━━━━━━━━━━━━━━━━━━━━
📈 <b>TOP 3 RESISTANCE (CE OI):</b>
{top_ce_lines}

📉 <b>TOP 3 SUPPORT (PE OI):</b>
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
• CE wall breaks → buy CE aggressively
• PE wall breaks → buy PE aggressively
• In range → sell options, don't buy
• Stop loss = 20% of premium always"""
else:
    msg = f"""📊 <b>NIFTY OPTION CHAIN REPORT</b>
🕐 {now} | {oc_status}
━━━━━━━━━━━━━━━━━━━━
{spot_emoji} <b>Nifty Spot:</b> <code>{spot:.2f}</code>
   Change: <code>{spot_change:+.2f} ({spot_pct:+.2f}%)</code>

⚠️ Option chain unavailable right now.
Check manually: nseindia.com/option-chain"""

send_msg(msg)
print("✅ Option chain alert sent!")
