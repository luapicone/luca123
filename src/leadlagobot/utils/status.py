from pathlib import Path
import json


class StatusBoard:
    def __init__(self, path: str = 'data/status.json'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2), encoding='utf8')
