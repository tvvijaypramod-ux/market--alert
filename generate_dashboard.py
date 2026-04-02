import yfinance as yf
import requests
import os
import time
import json
from datetime import datetime, timezone

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

# ── 4. OPTION CHAIN ───────────────────────────────────────────
oi_data  = []
ce_wall  = round(r1 / 50) * 50
pe_wall  = round(s1 / 50) * 50
max_pain = round(pivot / 50) * 50
pcr      = 1.0
total_ce = 0
total_pe = 0
straddle = round((ce_wall + pe_wall) / 2 / 50) * 50

try:
    from nselib import derivatives
    time.sleep(3)
    raw = derivatives.nse_live_option_chain(
        symbol="NIFTY", expiry_date=None
    )
    if raw is not None and not raw.empty:
        ce_oi_map  = {}
        pe_oi_map  = {}
        ce_chg_map = {}
        pe_chg_map = {}

        for _, row in raw.iterrows():
            s      = float(row.get('Strike Price', 0))
            ce_oi  = float(row.get('CALLS_OI', 0) or 0)
            pe_oi  = float(row.get('PUTS_OI', 0) or 0)
            ce_chg = float(row.get('CALLS_Chng_in_OI', 0) or 0)
            pe_chg = float(row.get('PUTS_Chng_in_OI', 0) or 0)
            ce_ltp = float(row.get('CALLS_LTP', 0) or 0)
            pe_ltp = float(row.get('PUTS_LTP', 0) or 0)
            ce_iv  = float(row.get('CALLS_IV', 0) or 0)
            pe_iv  = float(row.get('PUTS_IV', 0) or 0)

            ce_chg_pct = round((ce_chg/ce_oi*100),1) if ce_oi>0 else 0
            pe_chg_pct = round((pe_chg/pe_oi*100),1) if pe_oi>0 else 0

            ce_oi_map[s]  = ce_oi
            pe_oi_map[s]  = pe_oi
            ce_chg_map[s] = ce_chg_pct
            pe_chg_map[s] = pe_chg_pct

            if abs(s - spot) <= 1500:
                oi_data.append({
                    "strike": s,
                    "ce_oi":  ce_oi,
                    "pe_oi":  pe_oi,
                    "ce_chg": ce_chg_pct,
                    "pe_chg": pe_chg_pct,
                    "ltp_ce": ce_ltp,
                    "ltp_pe": pe_ltp,
                    "iv_ce":  ce_iv,
                    "iv_pe":  pe_iv,
                })

        if ce_oi_map:
            total_ce = sum(ce_oi_map.values())
            total_pe = sum(pe_oi_map.values())
            pcr      = round(total_pe/total_ce, 2) if total_ce > 0 else 1.0
            ce_wall  = float(max(ce_oi_map, key=ce_oi_map.get))
            pe_wall  = float(max(pe_oi_map, key=pe_oi_map.get))
            all_s    = {s: ce_oi_map.get(s,0)+pe_oi_map.get(s,0)
                        for s in set(ce_oi_map)|set(pe_oi_map)}
            max_pain = float(max(all_s, key=all_s.get))
            straddle = round((ce_wall+pe_wall)/2/50)*50
            oi_data.sort(key=lambda x: x['strike'], reverse=True)
            print(f"✅ nselib success — {len(oi_data)} strikes loaded")

except Exception as ex:
    print(f"⚠️ nselib failed: {ex} — using pivot-based fallback")

# ── 5. FALLBACK OI DATA if nselib failed ──────────────────────
if not oi_data:
    print("Using synthetic OI data from pivot levels")
    base_strikes = [
        round((spot + i*100)/50)*50 for i in range(-8, 9)
    ]
    for sk in sorted(base_strikes, reverse=True):
        dist = abs(sk - spot)
        ce_oi = max(100000, int(800000 * (1 - dist/1500)))
        pe_oi = max(100000, int(800000 * (1 - dist/1500)))
        if sk > spot + 200: ce_oi = int(ce_oi * 1.5)
        if sk < spot - 200: pe_oi = int(pe_oi * 1.5)
        oi_data.append({
            "strike": float(sk),
            "ce_oi":  ce_oi,
            "pe_oi":  pe_oi,
            "ce_chg": round(5 + (sk-spot)/100, 1),
            "pe_chg": round(5 - (sk-spot)/100, 1),
            "ltp_ce": max(10, round((spot-sk+300)/3)),
            "ltp_pe": max(10, round((sk-spot+300)/3)),
            "iv_ce":  round(vix * 1.1, 1),
            "iv_pe":  round(vix * 1.0, 1),
        })

# ── 6. BUILD JSON ─────────────────────────────────────────────
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
