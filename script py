import yfinance as yf
import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}&parse_mode=Markdown"
    requests.get(url)

# Fetch Data
nifty = yf.Ticker("^NSEI").history(period="2d")
spot_close = nifty['Close'].iloc[-1]
gift_live = yf.Ticker("^NSEI").fast_info['last_price'] 
usd_inr = yf.Ticker("INR=X").fast_info['last_price']

expected_gap = gift_live - spot_close
gap_type = "🟩 GAP UP" if expected_gap > 0 else "🟥 GAP DOWN"

msg = f"📈 *TETE 05:45 AM PRE-MARKET*\n---\n*Expected:* {gap_type}\n📍 *Nifty Spot:* {spot_close:.2f}\n📍 *GIFT Nifty:* {gift_live:.2f}\n📊 *Gap:* {expected_gap:+.2f} pts\n💵 *USD/INR:* {usd_inr:.2f}"
send_msg(msg)

