from pathlib import Path
import os
import tempfile


def atomic_write_text(path: str | Path, content: str, encoding: str = 'utf8') -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=f'.{target.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding=encoding) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
