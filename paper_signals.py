#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纸面 BTC/ETH 信号台 v0.1 —— 只记录不下单
数据源（本机实测可达，无需 key）：
  行情      data-api.binance.vision  (BTC/ETH 日线 klines)
  情绪      api.alternative.me/fng/  (恐惧贪婪指数)
  资金费率  币安 App 实盘（用户贴数；fapi/bybit 本机被墙）
输出：四角色信号 + 综合倾向；同时追加一行到 signals.jsonl
"""
import json, os, sys, urllib.request, datetime

VISION = "https://data-api.binance.vision"
FNG_URL = "https://api.alternative.me/fng/?limit=2"
UA = {"User-Agent": "paper-bot/0.1"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "signals.jsonl")

def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def klines(symbol, limit=70):
    return get(f"{VISION}/api/v3/klines?symbol={symbol}USDT&interval=1d&limit={limit}")

def closes(ks): return [float(k[4]) for k in ks]
def highs(ks):  return [float(k[2]) for k in ks]
def lows(ks):   return [float(k[3]) for k in ks]

def sma(xs, n): return sum(xs[-n:]) / n

def ema_series(xs, n):
    k = 2 / (n + 1); out = []; e = xs[0]
    for x in xs:
        e = x * k + e * (1 - k); out.append(e)
    return out

def macd_hist(xs):
    e12, e26 = ema_series(xs, 12), ema_series(xs, 26)
    line = [a - b for a, b in zip(e12, e26)]
    sig = ema_series(line, 9)
    return line[-1] - sig[-1]

def atr(ks, n=14):
    h, l, c = highs(ks), lows(ks), closes(ks)
    trs = []
    for i in range(1, len(ks)):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1])))
    return sum(trs[-n:]) / n

def trend_role(symbol, ks):
    c = closes(ks); last = c[-1]
    s20, s50 = sma(c, 20), sma(c, 50)
    hist = macd_hist(c)
    votes = []
    votes.append(("收盘>SMA20", last > s20))
    votes.append(("收盘>SMA50", last > s50))
    votes.append(("SMA20>SMA50", s20 > s50))
    votes.append(("MACD柱>0", hist > 0))
    bull = sum(1 for _, b in votes if b)
    sig = "看多" if bull >= 3 else ("看空" if bull <= 1 else "中性")
    detail = f"收${last:,.0f} SMA20 ${s20:,.0f} SMA50 ${s50:,.0f} MACD柱{hist:+.0f} ({bull}/4偏多)"
    return sig, detail, {"close": last, "sma20": s20, "sma50": s50, "macd_hist": hist}

def vol_role(symbol, ks):
    c = closes(ks); last = c[-1]
    a = atr(ks); pct = a / last * 100
    rng7 = sum((highs(ks)[i] - lows(ks)[i]) / c[i] for i in range(-7, 0)) / 7 * 100
    lvl = "高" if pct > 4 else ("低" if pct < 2 else "中")
    # 网格友好度：波动越高配对机会越多
    detail = f"ATR14 {pct:.2f}%（{lvl}波动）近7日均波幅{rng7:.2f}% 网格友好度:{'高' if pct>2.5 else '一般'}"
    return ("高波动" if lvl == "高" else ("低波动" if lvl == "低" else "中波动")), detail, {"atr_pct": round(pct,2), "range7_pct": round(rng7,2)}

def funding_role(funding_pct):
    # funding_pct: 用户从币安 App 贴的下次资金费率（%），None=缺数
    if funding_pct is None:
        return "待数据", "本机取不到资金费率（fapi/bybit被墙），等用户从币安App贴数", {}
    f = funding_pct
    if f >= 0.01:   sig, why = "偏空", "≥0.01% 做多拥挤"
    elif f <= -0.01: sig, why = "偏多", "≤-0.01% 做空拥挤"
    else:            sig, why = "中性", "费率温和"
    return sig, f"资金费率{f:+.4f}% {why}", {"funding_pct": f}

def sentiment_role():
    d = get(FNG_URL)["data"][0]
    v = int(d["value"]); cls = d["value_classification"]
    if v <= 24:   sig = "偏多(极恐)"
    elif v <= 44: sig = "偏多(恐惧)"
    elif v <= 55: sig = "中性"
    elif v <= 74: sig = "偏空(贪婪)"
    else:         sig = "偏空(极贪)"
    return sig, f"恐惧贪婪 {v}（{cls}）", {"fng": v}

def composite(signals):
    # 趋势2票，其余各1票；看多=+1，看空=-1，中性/待数据=0
    w = {"trend": 2, "vol": 0, "funding": 1, "sentiment": 1}  # 波动率不计方向票
    score = 0
    for role, (sig, _, _) in signals.items():
        if role == "vol": continue
        if "多" in sig: score += w[role]
        elif "空" in sig: score -= w[role]
    if score >= 2: return "看多"
    if score <= -2: return "看空"
    return "观望"

def review():
    """周复盘：对 ≥7 天前的方向性信号，对比 7 日后收盘涨跌，计胜率。
    口径：信号日(+08)对应上一根已收盘日线(UTC)，entry=该收盘，exit=7天后收盘。"""
    rows = [json.loads(l) for l in open(LOG_PATH) if l.strip()]
    tz8 = datetime.timezone(datetime.timedelta(hours=8))
    today8 = datetime.datetime.now(tz8).strftime("%Y-%m-%d")
    lines = ["纸面信号周复盘（信号成熟≥7天，方向 vs 7日后收盘涨跌）"]
    for sym in ("BTC", "ETH"):
        ks = klines(sym, limit=400)
        cmap = {}
        for k in ks:
            d = datetime.datetime.fromtimestamp(k[0] / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
            cmap[d] = float(k[4])
        for role, key in (("综合", "composite"), ("趋势哨兵", "trend")):
            total = wins = 0
            for r in rows:
                entry_d = (datetime.datetime.strptime(r["date"], "%Y-%m-%d") -
                           datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                exit_d = (datetime.datetime.strptime(entry_d, "%Y-%m-%d") +
                          datetime.timedelta(days=7)).strftime("%Y-%m-%d")
                if exit_d > today8 or entry_d not in cmap or exit_d not in cmap:
                    continue
                sig = r[sym][key]
                if "多" not in sig and "空" not in sig:
                    continue
                total += 1
                up = cmap[exit_d] > cmap[entry_d]
                if ("多" in sig and up) or ("空" in sig and not up):
                    wins += 1
            wr = f"{wins/total*100:.0f}%" if total else "—"
            lines.append(f"  [{sym}]{role}：{total} 个信号，胜率 {wr}")
    lines.append("仅个人记录，不构成投资建议。")
    print("\n".join(lines))


def main():
    import time
    if len(sys.argv) > 1 and sys.argv[1] == "--review":
        return review()
    funding = None
    for a in sys.argv[1:]:
        if a == "--review":
            continue
        try:
            funding = float(a)
        except ValueError:
            pass
    now_ms = int(time.time() * 1000)
    today = datetime.datetime.now(datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    out = {"date": today, "note": "仅个人记录，不构成投资建议"}
    lines = [f"纸面信号 {today}（日线收盘口径，截至昨日收盘）"]
    for sym in ("BTC", "ETH"):
        ks = klines(sym)
        live = None
        if ks[-1][6] > now_ms:  # 最后一根未收盘：只取现价，指标用已收盘K线
            live = float(ks[-1][4]); ks = ks[:-1]
        t = trend_role(sym, ks); v = vol_role(sym, ks)
        f = funding_role(funding); s = sentiment_role()
        comp = composite({"trend": t, "vol": v, "funding": f, "sentiment": s})
        out[sym] = {"trend": t[0], "vol": v[0], "funding": f[0], "sentiment": s[0],
                    "composite": comp,
                    "detail": {"trend": t[1], "vol": v[1], "funding": f[1], "sentiment": s[1]}}
        lines.append(f"\n[{sym}] 综合：{comp}" + (f"（现价${live:,.0f}盘中）" if live else ""))
        lines.append(f"  趋势哨兵 {t[0]}：{t[1]}")
        lines.append(f"  波动率官 {v[0]}：{v[1]}")
        lines.append(f"  资金费瞭望 {f[0]}：{f[1]}")
        lines.append(f"  情绪扫描 {s[0]}：{s[1]}")
    with open(LOG_PATH, "a") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    print("\n".join(lines))
    print("\n仅个人记录，不构成投资建议。已追加 signals.jsonl")

if __name__ == "__main__":
    main()
