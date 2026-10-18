#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金费率抓取 —— OKX 公开 API（免 key，本机直连可达）
供星槎 nightly-brief 调用。输出简报行 + 更新 funding_state.json。
注意：数据源为 OKX（币安 fapi 从本机/VPS 均被地理封锁），简报中须注明
"OKX 数据，决策以币安 App 实盘为准"。
"""
import datetime
import json
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "funding_state.json")

ENTER = 0.0001      # 0.01% 进场线（用户规则：连续多个 8h ≥0.01% 进场）
UA = {"User-Agent": "paper-bot/0.1"}
SYMBOLS = {"BTC": "BTC-USDT-SWAP", "ETH": "ETH-USDT-SWAP"}


def fetch(inst_id, limit=12):
    url = (f"https://www.okx.com/api/v5/public/funding-rate-history"
           f"?instId={inst_id}&limit={limit}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode())
    if d.get("code") != "0":
        raise RuntimeError(f"OKX 返回异常: {d.get('msg')}")
    return [{"t": int(x["fundingTime"]) // 1000, "rate": float(x["fundingRate"])}
            for x in d["data"]]


def analyze(rates):
    rs = sorted(rates, key=lambda x: x["t"])
    latest = rs[-1]
    consec = 0
    for x in reversed(rs):
        if x["rate"] >= ENTER:
            consec += 1
        else:
            break
    return {
        "latest_rate": latest["rate"],
        "latest_t": latest["t"],
        "consec_enter": consec,
        "periods": len(rs),
    }


def fmt_ts(t):
    return datetime.datetime.fromtimestamp(
        t, tz=datetime.timezone.utc).strftime("%m-%d %H:%M UTC")


def brief_line(sym, a):
    pct = a["latest_rate"] * 100
    base = f"{sym} 资金费率 {pct:+.4f}%（{fmt_ts(a['latest_t'])}已结算，OKX）"
    if a["consec_enter"] > 0:
        return f"{base}，已连续 {a['consec_enter']} 个 8h ≥0.01%"
    gap = (ENTER - a["latest_rate"]) * 100
    return f"{base}，距 0.01% 进场线还差 {gap:.4f}%"


def main():
    syms = sys.argv[1:] or ["BTC", "ETH"]
    state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            state = {}
    lines = []
    for sym in syms:
        inst = SYMBOLS.get(sym.upper(), sym)
        try:
            rates = fetch(inst)
        except Exception as e:
            lines.append(f"{sym} 资金费率获取失败: {e}")
            continue
        if not rates:
            lines.append(f"{sym} 资金费率无数据")
            continue
        a = analyze(rates)
        lines.append(brief_line(sym.upper(), a))
        state[sym.upper()] = {
            "source": "OKX",
            "updated_at": int(datetime.datetime.now(
                tz=datetime.timezone.utc).timestamp()),
            "latest_rate": a["latest_rate"],
            "latest_t": a["latest_t"],
            "consec_enter": a["consec_enter"],
            "history": rates[-12:],
        }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
