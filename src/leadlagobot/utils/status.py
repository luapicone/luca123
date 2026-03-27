from pathlib import Path
import json
import time


class StatusBoard:
    def __init__(self, path: str = 'data/status.json', history_path: str = 'data/status_history.jsonl'):
        self.path = Path(path)
        self.history_path = Path(history_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2), encoding='utf8')
        history_entry = {'ts': time.time(), **payload}
        with self.history_path.open('a', encoding='utf8') as file:
            file.write(json.dumps(history_entry) + '\n')
