import yfinance as yf
import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}&parse_mode=Markdown"
    requests.get(url)

# 1. FETCH DATA
nifty = yf.Ticker("^NSEI").history(period="2d")
pdh, pdl, prev_close = nifty['High'].iloc[-2], nifty['Low'].iloc[-2], nifty['Close'].iloc[-2]
spot_now = nifty['Close'].iloc[-1]

# 2. CALCULATE BENCHMARKS
pivot = (pdh + pdl + prev_close) / 3
r1, s1 = (2 * pivot) - pdl, (2 * pivot) - pdh

# 3. INDICATORS
vix = yf.Ticker("^INDIAVIX").history(period="1d")['Close'].iloc[-1]
gift_live = yf.Ticker("^NSEI").fast_info['last_price']
gap = gift_live - spot_now

# 4. MESSAGE
msg = f"""
📊 *TRADING BENCHMARKS*
---
💰 *GIFT Nifty Gap:* {gap:+.2f}
🧗 *PDH:* {pdh:.2f} | *PDL:* {pdl:.2f}
📐 *R1:* {r1:.2f} | *S1:* {s1:.2f}
📉 *India VIX:* {vix:.2f}
"""
send_msg(msg)
