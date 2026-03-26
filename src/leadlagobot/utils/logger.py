from pathlib import Path
from rich.console import Console
import json

console = Console()
LOG_PATH = Path('data/paper_trades.jsonl')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_trade(trade):
    with LOG_PATH.open('a', encoding='utf8') as file:
        file.write(json.dumps(trade.__dict__) + '\n')


def print_event(message: str):
    console.print(message)
