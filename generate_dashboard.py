import yfinance as yf
import requests
import os
import time
import json
from datetime import datetime, timezone

# ── 1. NIFTY SPOT ─────────────────────────────────────────────
nifty      = yf.Ticker("^NSEI").history(period="2d")
spot       = float(nifty['Close'].iloc[-1])
prev_close = float(nifty['Close'].iloc[-2])
pdh        = float(nifty['High'].iloc[-2])
pdl        = float(nifty['Low'].iloc[-2])
day_high   = float(nifty['High'].iloc[-1])
day_low    = float(nifty['Low'].iloc[-1])
spot_change= spot - prev_close
spot_pct   = (spot_change / prev_close) * 100

# ── 2. PIVOT POINTS ───────────────────────────────────────────
pivot = (pdh + pdl + prev_close) / 3
r1    = (2 * pivot) - pdl
r2    = pivot + (pdh - pdl)
s1    = (2 * pivot) - pdh
s2    = pivot - (pdh - pdl)

# ── 3. VIX ────────────────────────────────────────────────────
try:
    vix_data = yf.Ticker("^INDIAVIX").history(period="1d")
    vix = float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 20
except:
    vix = 20

# ── 4. OPTION CHAIN via NSE direct API ────────────────────────
oi_data  = []
ce_wall  = round(r1 / 50) * 50
pe_wall  = round(s1 / 50) * 50
max_pain = round(pivot / 50) * 50
pcr      = 1.0
total_ce = 0
total_pe = 0
straddle = round((ce_wall + pe_wall) / 2 / 50) * 50

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
}

# Try NSE direct API
nse_success = False
for attempt in range(3):
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com",
                   headers=NSE_HEADERS, timeout=10)
        time.sleep(2)
        session.get("https://www.nseindia.com/option-chain",
                   headers=NSE_HEADERS, timeout=10)
        time.sleep(2)
        resp = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            headers=NSE_HEADERS, timeout=15
        )
        raw = resp.json()
        if 'filtered' in raw:
            total_ce  = raw['filtered']['CE']['totOI']
            total_pe  = raw['filtered']['PE']['totOI']
            pcr       = round(total_pe/total_ce, 2) if total_ce > 0 else 1.0
            ce_oi_map = {}
            pe_oi_map = {}

            for item in raw['filtered']['data']:
                sk     = item.get('strikePrice', 0)
                ce     = item.get('CE', {})
                pe     = item.get('PE', {})
                ce_oi  = ce.get('openInterest', 0)
                pe_oi  = pe.get('openInterest', 0)
                ce_chg = ce.get('changeinOpenInterest', 0)
                pe_chg = pe.get('changeinOpenInterest', 0)
                ce_ltp = ce.get('lastPrice', 0)
                pe_ltp = pe.get('lastPrice', 0)
                ce_iv  = ce.get('impliedVolatility', 0)
                pe_iv  = pe.get('impliedVolatility', 0)

                ce_oi_map[sk] = ce_oi
                pe_oi_map[sk] = pe_oi

                ce_chg_pct = round((ce_chg/ce_oi*100),1) if ce_oi>0 else 0
                pe_chg_pct = round((pe_chg/pe_oi*100),1) if pe_oi>0 else 0

                if abs(sk - spot) <= 1500:
                    oi_data.append({
                        "strike": float(sk),
                        "ce_oi":  float(ce_oi),
                        "pe_oi":  float(pe_oi),
                        "ce_chg": ce_chg_pct,
                        "pe_chg": pe_chg_pct,
                        "ltp_ce": float(ce_ltp),
                        "ltp_pe": float(pe_ltp),
                        "iv_ce":  float(ce_iv),
                        "iv_pe":  float(pe_iv),
                    })

            if ce_oi_map:
                ce_wall  = float(max(ce_oi_map, key=ce_oi_map.get))
                pe_wall  = float(max(pe_oi_map, key=pe_oi_map.get))
                all_s    = {s: ce_oi_map.get(s,0)+pe_oi_map.get(s,0)
                            for s in set(ce_oi_map)|set(pe_oi_map)}
                max_pain = float(max(all_s, key=all_s.get))
                straddle = round((ce_wall+pe_wall)/2/50)*50
                oi_data.sort(key=lambda x: x['strike'], reverse=True)
                nse_success = True
                print(f"✅ NSE API success attempt {attempt+1} — {len(oi_data)} strikes")
                break
    except Exception as ex:
        print(f"NSE attempt {attempt+1} failed: {ex}")
        time.sleep(5)

# ── 5. SYNTHETIC FALLBACK if NSE failed ───────────────────────
if not nse_success or not oi_data:
    print("Using synthetic OI data")
    strikes = sorted([
        round((spot + i*50)/50)*50
        for i in range(-12, 13)
    ], reverse=True)

    ce_wall  = round((spot + 300)/50)*50
    pe_wall  = round((spot - 300)/50)*50
    max_pain = round(spot/50)*50
    straddle = round(spot/50)*50
    pcr      = 1.0
    total_ce = 5000000
    total_pe = 5000000

    for sk in strikes:
        dist = sk - spot
        if dist > 0:
            ce_oi = int(max(50000, 1000000 * (1 - dist/800)))
            pe_oi = int(max(50000, 300000 * (1 - dist/800)))
        else:
            ce_oi = int(max(50000, 300000 * (1 + dist/800)))
            pe_oi = int(max(50000, 1000000 * (1 + dist/800)))

        oi_data.append({
            "strike": float(sk),
            "ce_oi":  float(ce_oi),
            "pe_oi":  float(pe_oi),
            "ce_chg": round(abs(dist)/100, 1),
            "pe_chg": round(abs(dist)/100, 1),
            "ltp_ce": float(max(5, round((300-dist)/3))),
            "ltp_pe": float(max(5, round((300+dist)/3))),
            "iv_ce":  round(vix*1.1, 1),
            "iv_pe":  round(vix*1.0, 1),
        })

# ── 6. SAVE JSON ──────────────────────────────────────────────
data = {
    "spot":        round(spot, 2),
    "prev_close":  round(prev_close, 2),
    "spot_change": round(spot_change, 2),
    "spot_pct":    round(spot_pct, 2),
    "day_high":    round(day_high, 2),
    "day_low":     round(day_low, 2),
    "vix":         round(vix, 2),
    "pdh":         round(pdh, 2),
    "pdl":         round(pdl, 2),
    "pivot":       round(pivot, 2),
    "r1":          round(r1, 2),
    "r2":          round(r2, 2),
    "s1":          round(s1, 2),
    "s2":          round(s2, 2),
    "max_pain":    float(max_pain),
    "pcr":         float(pcr),
    "ce_wall":     float(ce_wall),
    "pe_wall":     float(pe_wall),
    "total_ce_oi": float(total_ce),
    "total_pe_oi": float(total_pe),
    "straddle":    float(straddle),
    "updated":     datetime.now(timezone.utc).isoformat(),
    "oi_data":     oi_data
}

with open("data.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"✅ data.json saved!")
print(f"   Spot:{spot} PCR:{pcr} CE:{ce_wall} PE:{pe_wall} Strikes:{len(oi_data)}")
