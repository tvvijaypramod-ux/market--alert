import yfinance as yf
import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.get(url, params=params)

nifty = yf.Ticker("^NSEI").history(period="2d")
pdh = nifty['High'].iloc[-2]
pdl = nifty['Low'].iloc[-2]
prev_close = nifty['Close'].iloc[-2]
spot_now = nifty['Close'].iloc[-1]

pivot = (pdh + pdl + prev_close) / 3
r1 = (2 * pivot) - pdl
s1 = (2 * pivot) - pdh

vix_data = yf.Ticker("^INDIAVIX").history(period="1d")
vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 0.0

msg = (
    "*NIFTY BENCHMARKS*\n\n"
    f"*Current Spot:* {spot_now:.2f}\n\n"
    f"*PDH:* {pdh:.2f}\n"
    f"*PDL:* {pdl:.2f}\n\n"
    f"*R1:* {r1:.2f}\n"
    f"*Pivot:* {pivot:.2f}\n"
    f"*S1:* {s1:.2f}\n\n"
    f"*India VIX:* {vix:.2f}"
)

send_msg(msg)
