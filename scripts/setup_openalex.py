#!/usr/bin/env python3
"""Configure an OpenAlex key interactively, or check the existing key with --check."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
import urllib.request
from openalex_auth import DEFAULT_KEY_FILE, api_key


def verify(key):
    request = urllib.request.Request('https://api.openalex.org/rate-limit',
        headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get('error'):
            raise ValueError('Unexpected response')
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'OpenAlex returned HTTP {exc.code}; check your key or try again later.') from None
    except Exception as exc:
        raise RuntimeError(f'Could not verify the OpenAlex connection ({type(exc).__name__}); no new key was saved.') from None


def save_key(key, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False) as handle:
            temporary = handle.name
            handle.write(key + '\n')
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.check:
            key = api_key()
            if not key:
                print('No OpenAlex key is configured.')
                return 1
            verify(key)
            print('OpenAlex connection verified (key not displayed).')
            return 0
        if not sys.stdin.isatty():
            raise RuntimeError('Run this script in a local interactive terminal to keep your key out of command-line arguments.')
        print('Open https://openalex.org/settings/api, sign in, and copy your API key.')
        print('Paste your key and press Enter; input is hidden. Press Enter without a key to cancel.')
        key = getpass.getpass('OpenAlex API Key: ').strip()
        if not key:
            print('Cancelled; configuration unchanged.')
            return 1
        verify(key)
        save_key(key, DEFAULT_KEY_FILE)
        print('Verified. Key saved to .secrets/openalex.key (owner read/write only; ignored by Git).')
        print('Scripts will read this key automatically; you do not need to enter it again.')
        if os.environ.get('OPENALEX_API_KEY') or os.environ.get('OPENALEX_API_KEY_FILE'):
            print('Note: existing OPENALEX_API_KEY / OPENALEX_API_KEY_FILE environment variables take precedence over this local configuration.')
        return 0
    except (RuntimeError, OSError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else 'Could not write the local configuration file.', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
