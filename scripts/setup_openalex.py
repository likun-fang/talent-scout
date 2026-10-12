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
        raise RuntimeError(f'OpenAlex 返回 HTTP {exc.code}；请检查 Key 或稍后重试。') from None
    except Exception as exc:
        raise RuntimeError(f'无法验证 OpenAlex 连接（{type(exc).__name__}），未保存新 Key。') from None


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
                print('尚未配置 OpenAlex Key。')
                return 1
            verify(key)
            print('OpenAlex Key 连接验证通过（密钥未显示）。')
            return 0
        if not sys.stdin.isatty():
            raise RuntimeError('请在本机交互式终端运行，避免将 Key 写入命令行。')
        print('先打开 https://openalex.org/settings/api 登录并复制 API Key。')
        print('粘贴后按回车；输入不会显示。直接回车可取消。')
        key = getpass.getpass('OpenAlex API Key: ').strip()
        if not key:
            print('已取消，未修改配置。')
            return 1
        verify(key)
        save_key(key, DEFAULT_KEY_FILE)
        print('验证成功，Key 已保存至项目 .secrets/openalex.key（仅当前用户可读写，Git 已忽略）。')
        print('后续脚本会自动读取，无需重复输入。')
        if os.environ.get('OPENALEX_API_KEY') or os.environ.get('OPENALEX_API_KEY_FILE'):
            print('注意：已有 OPENALEX_API_KEY / OPENALEX_API_KEY_FILE 环境变量优先于此本地配置。')
        return 0
    except (RuntimeError, OSError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else '本地配置文件写入失败。', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\n已取消。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
