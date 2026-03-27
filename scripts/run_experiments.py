import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
EXPERIMENTS_DIR = ROOT / 'experiments'
EXPERIMENTS_DIR.mkdir(exist_ok=True)

BASE_ENV = {
    'PYTHONPATH': 'src',
}

EXPERIMENTS = [
    {
        'name': 'exp_A_open_flow',
        'env': {
            'ENTRY_THRESHOLD_PCT': '0.18',
            'EXIT_THRESHOLD_PCT': '0.07',
            'MIN_QUALITY_SCORE': '-0.02',
            'MIN_FILL_RATIO': '0.35',
            'TOP_PAIRS_LIMIT': '8',
            'RANKING_MIN_SIGNALS': '20',
            'EXPECTED_NET_EDGE_MARGIN_PCT': '0.02',
            'MIN_EXPECTED_NET_EDGE_PCT': '-0.04',
            'MIN_EXIT_CAPTURE_RATIO': '0.30',
            'MAX_CROSS_EXCHANGE_TICK_AGE_MS': '3000',
        },
    },
    {
        'name': 'exp_B_soft_edge',
        'env': {
            'ENTRY_THRESHOLD_PCT': '0.20',
            'EXIT_THRESHOLD_PCT': '0.08',
            'MIN_QUALITY_SCORE': '-0.01',
            'MIN_FILL_RATIO': '0.40',
            'TOP_PAIRS_LIMIT': '8',
            'RANKING_MIN_SIGNALS': '20',
            'EXPECTED_NET_EDGE_MARGIN_PCT': '0.02',
            'MIN_EXPECTED_NET_EDGE_PCT': '-0.03',
            'MIN_EXIT_CAPTURE_RATIO': '0.35',
            'MAX_CROSS_EXCHANGE_TICK_AGE_MS': '3000',
        },
    },
    {
        'name': 'exp_C_balanced_relaxed',
        'env': {
            'ENTRY_THRESHOLD_PCT': '0.22',
            'EXIT_THRESHOLD_PCT': '0.08',
            'MIN_QUALITY_SCORE': '0.00',
            'MIN_FILL_RATIO': '0.40',
            'TOP_PAIRS_LIMIT': '8',
            'RANKING_MIN_SIGNALS': '25',
            'EXPECTED_NET_EDGE_MARGIN_PCT': '0.03',
            'MIN_EXPECTED_NET_EDGE_PCT': '-0.02',
            'MIN_EXIT_CAPTURE_RATIO': '0.35',
            'MAX_CROSS_EXCHANGE_TICK_AGE_MS': '3000',
        },
    },
    {
        'name': 'exp_D_guarded',
        'env': {
            'ENTRY_THRESHOLD_PCT': '0.24',
            'EXIT_THRESHOLD_PCT': '0.09',
            'MIN_QUALITY_SCORE': '0.01',
            'MIN_FILL_RATIO': '0.45',
            'TOP_PAIRS_LIMIT': '6',
            'RANKING_MIN_SIGNALS': '25',
            'EXPECTED_NET_EDGE_MARGIN_PCT': '0.03',
            'MIN_EXPECTED_NET_EDGE_PCT': '-0.01',
            'MIN_EXIT_CAPTURE_RATIO': '0.40',
            'MAX_CROSS_EXCHANGE_TICK_AGE_MS': '3000',
        },
    },
]


def reset_data_dir():
    DATA_DIR.mkdir(exist_ok=True)
    for file_name in [
        'paper_trades.jsonl',
        'rejected_opportunities.jsonl',
        'cancelled_orders.jsonl',
        'status_history.jsonl',
    ]:
        (DATA_DIR / file_name).write_text('', encoding='utf8')
    for file_name in [
        'pair_metrics.json',
        'pair_ranking.json',
        'status.json',
        'reconciliation.json',
        'execution_dry_run.jsonl',
        'risk_state.json',
        'KILL_SWITCH',
    ]:
        path = DATA_DIR / file_name
        if path.exists():
            path.unlink()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def load_jsonl(path: Path):
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


def summarize_run(name: str, env_overrides: dict, duration_seconds: int):
    trades = load_jsonl(DATA_DIR / 'paper_trades.jsonl')
    ranking = load_json(DATA_DIR / 'pair_ranking.json', [])
    metrics = load_json(DATA_DIR / 'pair_metrics.json', {})
    status = load_json(DATA_DIR / 'status.json', {})
    rejected = load_jsonl(DATA_DIR / 'rejected_opportunities.jsonl')
    cancelled = load_jsonl(DATA_DIR / 'cancelled_orders.jsonl')

    wins = sum(1 for t in trades if (t.get('net_pnl', 0) or 0) >= 0)
    losses = sum(1 for t in trades if (t.get('net_pnl', 0) or 0) < 0)
    total_net = sum((t.get('net_pnl', 0) or 0) for t in trades)
    total_gross = sum((t.get('gross_pnl', 0) or 0) for t in trades)
    avg_fill = (sum((t.get('fill_ratio', 0) or 0) for t in trades) / len(trades)) if trades else 0.0
    avg_expected_edge = (sum((t.get('expected_net_edge_pct', 0) or 0) for t in trades) / len(trades)) if trades else 0.0
    avg_realized_edge = (sum((t.get('realized_net_edge_pct', 0) or 0) for t in trades) / len(trades)) if trades else 0.0

    summary = {
        'name': name,
        'duration_seconds': duration_seconds,
        'env': env_overrides,
        'status': status,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'win_rate_pct': (wins / len(trades) * 100) if trades else 0.0,
        'total_net_pnl': total_net,
        'total_gross_pnl': total_gross,
        'avg_fill_ratio': avg_fill,
        'avg_expected_net_edge_pct': avg_expected_edge,
        'avg_realized_net_edge_pct': avg_realized_edge,
        'rejections': len(rejected),
        'cancellations': len(cancelled),
        'top_ranking': ranking[:10],
        'metrics': metrics,
    }
    return summary


def main():
    duration_seconds = int(os.getenv('EXPERIMENT_DURATION_SECONDS', '1800'))
    summaries = []

    for experiment in EXPERIMENTS:
        print(f"\n=== Running {experiment['name']} for {duration_seconds}s ===")
        reset_data_dir()
        run_env = os.environ.copy()
        run_env.update(BASE_ENV)
        run_env.update(experiment['env'])

        process = subprocess.Popen(
            [sys.executable, '-m', 'leadlagobot.main'],
            cwd=ROOT,
            env=run_env,
        )
        try:
            time.sleep(duration_seconds)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()

        summary = summarize_run(experiment['name'], experiment['env'], duration_seconds)
        summaries.append(summary)
        exp_dir = EXPERIMENTS_DIR / experiment['name']
        exp_dir.mkdir(exist_ok=True)
        (exp_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')

        for file_name in [
            'paper_trades.jsonl',
            'pair_metrics.json',
            'pair_ranking.json',
            'rejected_opportunities.jsonl',
            'cancelled_orders.jsonl',
            'status.json',
            'status_history.jsonl',
            'reconciliation.json',
        ]:
            src = DATA_DIR / file_name
            if src.exists():
                shutil.copy2(src, exp_dir / file_name)

    (EXPERIMENTS_DIR / 'summary.json').write_text(json.dumps(summaries, indent=2), encoding='utf8')
    print(f"\nExperiment summary written to {EXPERIMENTS_DIR / 'summary.json'}")


if __name__ == '__main__':
    main()
