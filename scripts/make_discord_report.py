import json
from pathlib import Path
from collections import Counter, defaultdict


data_dir = Path("data")
out = Path("discord_report.txt")


def load_json(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}



def load_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


status = load_json(data_dir / "status.json", {})
ranking = load_json(data_dir / "pair_ranking.json", [])
metrics = load_json(data_dir / "pair_metrics.json", {})
reconciliation = load_json(data_dir / "reconciliation.json", {})
trades = load_jsonl(data_dir / "paper_trades.jsonl")
rejected = load_jsonl(data_dir / "rejected_opportunities.jsonl")
cancelled = load_jsonl(data_dir / "cancelled_orders.jsonl")

lines = []

lines.append("===== STATUS =====")
if isinstance(status, dict) and status:
    keys = [
        "tracked_symbol",
        "balance",
        "latest_gap_pct",
        "latest_quality_score",
        "latest_signal_age_ms",
        "risk_ok",
        "margin_ok",
        "rules_ok",
        "daily_realized_pnl",
        "cancel_rate",
        "top_symbols",
    ]
    for k in keys:
        if k in status:
            lines.append(f"{k}: {status.get(k)}")
else:
    lines.append(str(status))

lines.append("")
lines.append("===== TRADES SUMMARY =====")
lines.append(f"total_trades: {len(trades)}")
if trades:
    wins = sum(1 for t in trades if (t.get("net_pnl", 0) or 0) >= 0)
    losses = sum(1 for t in trades if (t.get("net_pnl", 0) or 0) < 0)
    total_pnl = sum((t.get("net_pnl", 0) or 0) for t in trades)
    gross_pnl = sum((t.get("gross_pnl", 0) or 0) for t in trades)
    avg_pnl = total_pnl / len(trades)
    avg_fill = sum((t.get("fill_ratio", 0) or 0) for t in trades) / len(trades)
    avg_dur = sum((t.get("duration_ms", 0) or 0) for t in trades) / len(trades)

    lines.append(f"wins: {wins}")
    lines.append(f"losses: {losses}")
    lines.append(f"win_rate_pct: {round((wins / len(trades)) * 100, 2)}")
    lines.append(f"total_net_pnl: {round(total_pnl, 6)}")
    lines.append(f"total_gross_pnl: {round(gross_pnl, 6)}")
    lines.append(f"avg_net_pnl: {round(avg_pnl, 6)}")
    lines.append(f"avg_fill_ratio: {round(avg_fill, 6)}")
    lines.append(f"avg_duration_ms: {round(avg_dur, 2)}")

    per_symbol = defaultdict(lambda: {"count": 0, "net": 0.0, "wins": 0, "losses": 0})
    for t in trades:
        s = t.get("symbol", "UNKNOWN")
        net = t.get("net_pnl", 0) or 0
        per_symbol[s]["count"] += 1
        per_symbol[s]["net"] += net
        if net >= 0:
            per_symbol[s]["wins"] += 1
        else:
            per_symbol[s]["losses"] += 1

    lines.append("")
    lines.append("top_symbols_by_trades:")
    for symbol, row in sorted(per_symbol.items(), key=lambda kv: kv[1]["count"], reverse=True)[:15]:
        lines.append(
            f"{symbol}: trades={row['count']} net={round(row['net'], 6)} wins={row['wins']} losses={row['losses']}"
        )

lines.append("")
lines.append("===== LAST 20 TRADES =====")
if trades:
    for t in trades[-20:]:
        lines.append(str({
            "symbol": t.get("symbol"),
            "net_pnl": t.get("net_pnl"),
            "gross_pnl": t.get("gross_pnl"),
            "duration_ms": t.get("duration_ms"),
            "fill_ratio": t.get("fill_ratio"),
            "entry_gap_pct": t.get("entry_gap_pct"),
            "exit_gap_pct": t.get("exit_gap_pct"),
        }))
else:
    lines.append("no trades")

lines.append("")
lines.append("===== TOP RANKING =====")
if isinstance(ranking, list):
    for r in ranking[:20]:
        lines.append(str({
            "symbol": r.get("symbol"),
            "ranking_score": r.get("ranking_score"),
            "signals": r.get("signals"),
            "opens": r.get("opens"),
            "closes": r.get("closes"),
            "wins": r.get("wins"),
            "losses": r.get("losses"),
            "rejected": r.get("rejected"),
            "cancelled": r.get("cancelled"),
            "net_pnl": r.get("net_pnl"),
            "avg_quality_score": r.get("avg_quality_score"),
            "avg_fill_ratio": r.get("avg_fill_ratio"),
        }))
else:
    lines.append(str(ranking))

lines.append("")
lines.append("===== PAIR METRICS =====")
if isinstance(metrics, dict):
    for symbol, r in sorted(metrics.items())[:50]:
        lines.append(f"{symbol}: {r}")
else:
    lines.append(str(metrics))

lines.append("")
lines.append("===== REJECTION REASONS =====")
reason_counter = Counter()
for r in rejected:
    reason_counter[r.get("reason", "unknown")] += 1

if reason_counter:
    for reason, count in reason_counter.most_common(20):
        lines.append(f"{reason}: {count}")
else:
    lines.append("no rejections")

lines.append("")
lines.append("===== LAST 40 REJECTIONS =====")
if rejected:
    for r in rejected[-40:]:
        lines.append(str({
            "symbol": r.get("symbol"),
            "reason": r.get("reason"),
            "gap_pct": r.get("gap_pct"),
            "quality_score": r.get("quality_score"),
            "signal_age_ms": r.get("signal_age_ms"),
            "fill_ratio": r.get("fill_ratio"),
        }))
else:
    lines.append("no rejections")

lines.append("")
lines.append("===== LAST 20 CANCELLATIONS =====")
if cancelled:
    for r in cancelled[-20:]:
        lines.append(str(r))
else:
    lines.append("no cancellations")

lines.append("")
lines.append("===== RECONCILIATION =====")
lines.append(str(reconciliation)[:12000])

out.write_text("\n".join(lines))
print(f"Reporte generado: {out}")
