#!/usr/bin/env python3
"""Scarica chiusure, medie e cambi per il Comitato di agenti. Solo libreria standard.
Scrive data/prezzi.json. Lo usa la riunione serale al posto di leggere le pagine una per una."""
import json, time, urllib.request, urllib.error, xml.etree.ElementTree as ET, datetime as dt, os, sys

UA = {"User-Agent": "Mozilla/5.0 (compatible; comitato-agenti/1.0)"}

def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(3 * (i + 1))
    raise last

def yahoo(symbol):
    for host in ("query1", "query2"):
        try:
            raw = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d")
            res = json.loads(raw)["chart"]["result"][0]
            break
        except Exception as e:
            err = e
    else:
        raise err
    meta = res["meta"]
    ts = res.get("timestamp") or []
    closes = (res["indicators"]["quote"][0].get("close") or [])
    tz = dt.timezone(dt.timedelta(seconds=meta.get("gmtoffset", 0)))
    rows = [(dt.datetime.fromtimestamp(t, tz).date().isoformat(), round(c, 4)) for t, c in zip(ts, closes) if c is not None]
    if not rows:
        raise ValueError("nessuna chiusura")
    vals = [c for _, c in rows]
    ma = lambda n: round(sum(vals[-n:]) / n, 4) if len(vals) >= n else None
    last_d, last_c = rows[-1]
    prev = rows[-2][1] if len(rows) > 1 else None
    hi, lo = max(vals), min(vals)
    return {
        "symbol": symbol, "currency": meta.get("currency"), "exchange": meta.get("exchangeName"),
        "date": last_d, "close": last_c, "prevClose": prev,
        "changePct": round((last_c / prev - 1) * 100, 3) if prev else None,
        "high52": hi, "low52": lo, "fromHighPct": round((last_c / hi - 1) * 100, 3),
        "ma50": ma(50), "ma200": ma(200), "days": len(vals),
        "last5": rows[-5:],
    }

def ecb():
    raw = get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
    root = ET.fromstring(raw); out = {}; day = None
    for el in root.iter():
        if el.get("time"): day = el.get("time")
        if el.get("currency"): out[el.get("currency")] = float(el.get("rate"))
    return {"date": day, "USD": out.get("USD"), "DKK": out.get("DKK"), "CHF": out.get("CHF"), "GBP": out.get("GBP"), "source": "BCE eurofxref-daily"}

def main():
    cfg = json.load(open("tickers.json"))
    out = {"updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": "Yahoo Finance (chart API), cambi BCE", "tickers": {}, "errors": []}
    try:
        out["fx"] = ecb()
    except Exception as e:
        out["fx"] = None; out["errors"].append(f"BCE: {e}")
    for name, sym in cfg["tickers"].items():
        try:
            out["tickers"][name] = yahoo(sym)
        except Exception as e:
            out["errors"].append(f"{name} ({sym}): {e}")
        time.sleep(1)
    b = out["tickers"].get("EUNL")
    if b:
        dd = b["fromHighPct"]; above = b["ma200"] is None or b["close"] >= b["ma200"]
        regime = "ribasso" if dd <= -20 else ("rialzo" if dd > -10 and above else "correzione")
        out["regime"] = {"regime": regime, "eunlClose": b["close"], "date": b["date"], "high52": b["high52"], "low52": b["low52"],
                         "drawdownPct": dd, "ma200": b["ma200"], "cashRange": {"rialzo": "2-8%", "correzione": "5-20%", "ribasso": "10-30%"}[regime]}
    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/prezzi.json", "w"), ensure_ascii=False, indent=1)
    fx = out.get("fx") or {}
    lines = [f"aggiornato,{out['updatedAt']}", f"cambi_bce,{fx.get('date')},USD={fx.get('USD')},DKK={fx.get('DKK')},CHF={fx.get('CHF')},GBP={fx.get('GBP')}"]
    r = out.get("regime")
    if r:
        lines.append(f"fase,{r['regime']},EUNL={r['eunlClose']},max52={r['high52']},min52={r['low52']},dal_massimo%={r['drawdownPct']},media200={r['ma200']},liquidita={r['cashRange']}")
    lines.append("titolo,data,chiusura,precedente,var%,max52,min52,media50,media200,valuta")
    for k, v in out["tickers"].items():
        lines.append(",".join(str(x) for x in [k, v["date"], v["close"], v["prevClose"], v["changePct"], v["high52"], v["low52"], v["ma50"], v["ma200"], v["currency"]]))
    for e in out["errors"]:
        lines.append("errore," + e.replace(",", ";"))
    open("data/prezzi.csv", "w").write("\n".join(lines) + "\n")
    # universo: titoli piu' comuni gia' pronti, cosi' un acquisto nuovo ha quasi sempre il prezzo senza aggiungerlo a mano
    uni = cfg.get("universo") or []
    if uni:
        ul = [f"aggiornato,{out['updatedAt']}", "simbolo,data,chiusura,precedente,var%,max52,min52,media200,valuta"]
        for sym in uni:
            try:
                v = yahoo(sym)
                ul.append(",".join(str(x) for x in [sym, v["date"], v["close"], v["prevClose"], v["changePct"], v["high52"], v["low52"], v["ma200"], v["currency"]]))
            except Exception as e:
                ul.append(f"{sym},errore")
            time.sleep(0.5)
        open("data/universo.csv", "w").write("\n".join(ul) + "\n")
    print(json.dumps({k: (v["close"], v["date"]) for k, v in out["tickers"].items()}), out.get("regime"), out["errors"])
    if not out["tickers"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
