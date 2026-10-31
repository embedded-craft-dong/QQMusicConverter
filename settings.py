"""Persist only the output directory. Credentials and permission toggles are excluded."""
import json
import os
from pathlib import Path
import tempfile


def settings_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.config')) / 'QQMusicConverter' / 'settings.json'


def load_output(path=None):
    default = str(Path.home() / 'Music' / 'MP3Converted')
    try:
        value = json.loads((path or settings_path()).read_text(encoding='utf-8')).get('output_dir')
        return value if isinstance(value, str) and value.strip() else default
    except (OSError, ValueError, AttributeError):
        return default


def save_output(output, path=None):
    path = path or settings_path()
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.settings-', suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'output_dir': str(output)}, stream, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
    finally:
        if tmp and Path(tmp).exists():
            try:
                Path(tmp).unlink()
            except OSError:
                pass
