"""Load OpenAlex credentials without placing them in URLs or run artifacts."""
import os
from pathlib import Path

DEFAULT_KEY_FILE = Path(__file__).resolve().parents[1] / '.secrets' / 'openalex.key'


def api_key():
    key = os.environ.get('OPENALEX_API_KEY', '').strip()
    if key:
        return key
    supplied = os.environ.get('OPENALEX_API_KEY_FILE')
    path = Path(supplied).expanduser() if supplied else DEFAULT_KEY_FILE
    try:
        return path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        if supplied:
            raise RuntimeError('OPENALEX_API_KEY_FILE does not exist') from None
        return ''
    except OSError:
        raise RuntimeError('Cannot read OpenAlex key file') from None


def auth_headers():
    key = api_key()
    return {'Authorization': 'Bearer ' + key} if key else {}
