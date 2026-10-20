"""Validate a domain pack: domain-cache/<slug>.yaml against assets/domain-pack.schema.json, plus its facets file and
its known-groups list.

  check_domain_pack.py <slug> [<slug> ...]       one or more packs under SKILL_ROOT
  check_domain_pack.py --template                the blank template, assets/domain-map.template.yaml

A pack's yaml may use the YAML subset the packs are written in: block mappings and sequences, "- key: value" items,
flow {…} and […], quoted and plain scalars, comments. The loader is part of this script so the check needs only the
standard library; a construct outside the subset (a block scalar, an anchor) is reported with its line number.
Exits 1 when any pack has an error; a missing known-groups list is a warning, because check_groups.py needs it only
before a map is published.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = SKILL_ROOT / 'assets/domain-pack.schema.json'
TEMPLATE = SKILL_ROOT / 'assets/domain-map.template.yaml'
# A pack maps institutions and sources; names of people, OpenAlex author ids and LinkedIn URLs belong to no pack.
PERSONAL = ((r'linkedin\.', 'a LinkedIn URL'), (r'\bA5\d{9}\b', 'an OpenAlex author id'))


# --- YAML subset -------------------------------------------------------------------------------------------------

def strip_comment(text: str) -> str:
    """Cut a # comment. A # starts a comment only after a space and outside a quoted scalar; a quote opens a scalar
    only where a value starts (the line start, after "- ", after ": ", after "[", "{" or a flow ","), so a quote
    or an apostrophe inside a plain value is text; \\" and '' do not close a quoted scalar."""
    quote, escaped, depth, start = None, False, 0, True
    for i, ch in enumerate(text):
        after = text[i + 1:i + 2]
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\' and quote == '"' or ch == "'" == quote and after == "'":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ' \t':
            continue
        if ch == '#' and (i == 0 or text[i - 1] in ' \t'):
            return text[:i].rstrip()
        if start and ch in '"\'':
            quote, start = ch, False
        elif start and ch in '[{':
            depth += 1
        elif depth and ch in ']}':
            depth, start = depth - 1, False
        elif depth and ch == ',':
            start = True
        elif ch == ':' and (after in ('', ' ', '\t') or depth and after in ',[]{}'):
            start = True
        elif ch == '-' and start and after in ('', ' ', '\t'):
            pass  # a sequence item: its value starts next
        else:
            start = False
    return text.rstrip()

def scalar(token: str):
    if token in ('', '~', 'null'):
        return None
    if token in ('true', 'false'):
        return token == 'true'
    if re.fullmatch(r'-?\d+', token):
        return int(token)
    if re.fullmatch(r'-?\d+\.\d+', token):
        return float(token)
    return token


def quoted(text: str, pos: int) -> tuple[str, int]:
    """A quoted scalar starting at pos; returns its value and the position after it."""
    quote = text[pos]
    if quote == "'":
        end, value = pos + 1, []
        while end < len(text):
            if text[end] == "'":
                if text[end + 1:end + 2] == "'":
                    value.append("'")
                    end += 2
                    continue
                return ''.join(value), end + 1
            value.append(text[end])
            end += 1
    else:
        end = pos + 1
        while end < len(text):
            if text[end] == '\\':
                end += 2
                continue
            if text[end] == '"':
                return json.loads(text[pos:end + 1]), end + 1
            end += 1
    raise ValueError('unterminated quoted scalar')


def flow(text: str, pos: int, stops: str) -> tuple[object, int]:
    """A flow value at pos: {…}, […], a quoted scalar, or a plain scalar ending at one of stops."""
    while text[pos:pos + 1] == ' ':
        pos += 1
    if text[pos:pos + 1] in ('{', '['):
        closing, mapping = ('}', True) if text[pos] == '{' else (']', False)
        result, pos = ({} if mapping else []), pos + 1
        while True:
            while text[pos:pos + 1] == ' ':
                pos += 1
            if text[pos:pos + 1] == closing:
                return result, pos + 1
            if pos >= len(text):
                raise ValueError(f'unclosed {"mapping" if mapping else "sequence"}')
            if mapping:
                key, pos = flow(text, pos, ':,' + closing)
                while text[pos:pos + 1] == ' ':
                    pos += 1
                if text[pos:pos + 1] != ':':
                    raise ValueError(f'expected ":" after key {key!r}')
                value, pos = flow(text, pos + 1, ',' + closing)
                if str(key) in result:
                    raise ValueError(f'duplicate key {key!r}')
                result[str(key)] = value
            else:
                if text[pos:pos + 1] == ',':
                    raise ValueError(f'empty entry at column {pos + 1}')
                value, pos = flow(text, pos, ',' + closing)
                result.append(value)
            while text[pos:pos + 1] == ' ':
                pos += 1
            if text[pos:pos + 1] == ',':
                pos += 1
            elif text[pos:pos + 1] != closing:
                raise ValueError(f'expected "," or "{closing}" at column {pos + 1}')
    if text[pos:pos + 1] in ('"', "'"):
        return quoted(text, pos)
    if text[pos:pos + 1] in ('&', '*', '!'):
        raise ValueError(f'{text[pos]!r} (an anchor, alias or tag) is outside the YAML subset')
    end = pos
    while end < len(text):
        # A ":" ends a plain key only before a space, a flow indicator or the end; "https://x" stays one scalar.
        if text[end] == ':' and ':' in stops:
            if text[end + 1:end + 2] in ('', ' ', ',', '{', '}', '[', ']'):
                break
        elif text[end] in stops:
            break
        end += 1
    token = text[pos:end].strip()
    # Inside a flow collection a plain scalar holds no ": " (YAML reads a mapping there) and no flow indicator.
    if ',' in stops and (': ' in token or token.endswith(':') or re.search(r'[{}\[\]]', token)):
        raise ValueError(f'a flow entry needs quotes: {token[:40]!r}')
    return scalar(token), end


def inline(text: str):
    if re.fullmatch(r'[|>][-+]?\d*', text) or text.startswith(('&', '*', '!')):
        raise ValueError(f'{text[:2]!r} is outside the YAML subset')
    if text[0] not in '{["\'' and (': ' in text or text.endswith(':')):
        raise ValueError(f'a plain value with ": " needs quotes: {text[:40]!r}')
    value, end = flow(text, 0, '')
    if text[end:].strip():
        raise ValueError(f'unexpected text after the value: {text[end:].strip()[:30]!r}')
    return value


KEY = re.compile(r'^("(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\'|[^\s"\'{\[\]},#&*!|>-][^:]*?|-[^\s:][^:]*?)\s*:(?:\s+(.*)|$)')


def load_yaml(text: str):
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        content = strip_comment(raw)
        if content.strip():
            if '\t' in raw[:len(raw) - len(raw.lstrip())]:
                raise ValueError(f'line {number}: a tab in the indentation')
            lines.append([number, len(content) - len(content.lstrip()), content.strip()])

    def node(i: int, indent: int):
        return sequence(i, indent) if lines[i][2].startswith('-') and lines[i][2][1:2] in ('', ' ') else mapping(i, indent)

    def item(content: str) -> bool:
        return content.startswith('-') and content[1:2] in ('', ' ')

    def nested(i: int, indent: int, same_indent_sequence: bool = True):
        """The value of a key or item with nothing after it: a deeper block, a sequence at the same indent (after a
        key, not after an item, where the next "-" is a sibling), or null."""
        if i < len(lines) and (lines[i][1] > indent or same_indent_sequence and lines[i][1] == indent and item(lines[i][2])):
            return node(i, lines[i][1])
        return None, i

    def mapping(i: int, indent: int):
        result = {}
        while i < len(lines) and lines[i][1] == indent and not lines[i][2].startswith('- '):
            number, _, content = lines[i]
            match = KEY.match(content)
            if not match:
                raise ValueError(f'line {number}: expected "key: value", got {content[:40]!r}')
            key = match.group(1)
            key = quoted(key, 0)[0] if key[0] in '"\'' else key
            if key in result:
                raise ValueError(f'line {number}: duplicate key {key!r}')
            try:
                if match.group(2) is None:
                    result[key], i = nested(i + 1, indent)
                else:
                    result[key], i = inline(match.group(2)), i + 1
            except ValueError as exc:
                raise ValueError(f'line {number}: {exc}') from None
        if i < len(lines) and lines[i][1] > indent:
            raise ValueError(f'line {lines[i][0]}: unexpected indentation')
        return result, i

    def sequence(i: int, indent: int):
        result = []
        while i < len(lines) and lines[i][1] == indent and lines[i][2].startswith('-') and lines[i][2][1:2] in ('', ' '):
            number, _, content = lines[i]
            rest = content[1:].strip()
            if rest.startswith('-') and rest[1:2] in ('', ' '):
                raise ValueError(f'line {number}: a sequence inside a sequence item is outside the YAML subset')
            if not rest:
                value, i = nested(i + 1, indent, same_indent_sequence=False)
            elif rest[0] not in '{[' and KEY.match(rest):
                # "- key: value" opens a mapping whose further keys sit at the column of that key.
                lines[i] = [number, indent + len(content) - len(content[1:].lstrip()), rest]
                value, i = mapping(i, lines[i][1])
            else:
                try:
                    value, i = inline(rest), i + 1
                except ValueError as exc:
                    raise ValueError(f'line {number}: {exc}') from None
            result.append(value)
        return result, i

    if not lines:
        return {}
    value, i = node(0, lines[0][1])
    if i < len(lines):
        raise ValueError(f'line {lines[i][0]}: unexpected content')
    return value


# --- schema --------------------------------------------------------------------------------------------------------

TYPES = {'object': dict, 'array': list, 'string': str, 'null': type(None), 'boolean': bool, 'integer': int, 'number': (int, float)}


def validate(value, schema: dict, root: dict, path: str = '$') -> list[str]:
    """The JSON Schema keywords the pack schema uses: $ref, type, enum, pattern, required, properties,
    additionalProperties and items."""
    if '$ref' in schema:
        schema = root['$defs'][schema['$ref'].rsplit('/', 1)[1]]
    errors = []
    types = schema.get('type')
    if types:
        names = types if isinstance(types, list) else [types]
        if not any(isinstance(value, TYPES[t]) and not (t in ('integer', 'number') and isinstance(value, bool)) for t in names):
            return [f'{path}: expected {" or ".join(names)}, got {type(value).__name__}']
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{path}: {value!r} is not one of {schema["enum"]}')
    if 'pattern' in schema and isinstance(value, str) and not re.search(schema['pattern'], value):
        errors.append(f'{path}: {value!r} does not match {schema["pattern"]}')
    if isinstance(value, dict):
        errors += [f'{path}: missing {key}' for key in schema.get('required', []) if key not in value]
        properties = schema.get('properties', {})
        for key, item in value.items():
            if key in properties:
                errors += validate(item, properties[key], root, f'{path}.{key}')
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}: unexpected key {key}')
    if isinstance(value, list) and 'items' in schema:
        for index, item in enumerate(value):
            errors += validate(item, schema['items'], root, f'{path}[{index}]')
    return errors


# --- packs ---------------------------------------------------------------------------------------------------------

def examine(path: Path, template: bool = False) -> tuple[list[str], dict | None]:
    try:
        data = load_yaml(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return [f'{path.name}: {exc}'], None
    if not isinstance(data, dict):
        return [f'{path.name}: expected a mapping at the top'], None
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    errors = validate(data, schema, schema)
    text = json.dumps(data, ensure_ascii=False)
    errors += [f'personal data: {what} in the pack' for pattern, what in PERSONAL if re.search(pattern, text, re.I)]
    if not template:
        if data.get('slug') != path.stem:
            errors.append(f'slug {data.get("slug")!r} is not the file name {path.stem!r}')
        try:
            datetime.date.fromisoformat(str(data.get('derived_on')))
        except ValueError:
            errors.append(f'derived_on {data.get("derived_on")!r} is not a date (YYYY-MM-DD)')
    return errors, data


def check_file(path: Path, template: bool = False) -> list[str]:
    return examine(path, template)[0]


def json_list(path: Path, key: str) -> tuple[list | None, str]:
    try:
        value = json.loads(path.read_text(encoding='utf-8')).get(key)
    except (OSError, ValueError, AttributeError) as exc:
        return None, str(exc)
    return (value, '') if isinstance(value, list) else (None, f'expected a "{key}" list')


def check_pack(slug: str, root: Path = SKILL_ROOT) -> tuple[list[str], list[str]]:
    errors, data = examine(root / 'domain-cache' / f'{slug}.yaml')
    warnings = []
    if data is None:
        return errors, warnings
    facets_file = data.get('facets_file') or ''
    if facets_file != f'assets/facets/{slug}.json':
        errors.append(f'facets_file {facets_file!r} is not assets/facets/{slug}.json')
    facets, problem = json_list(root / f'assets/facets/{slug}.json', 'facets')
    if facets is None:
        errors.append(f'facets file assets/facets/{slug}.json: {problem}')
    known = root / f'assets/known-groups/{slug}.json'
    if not known.exists():
        warnings.append(f'no known-groups list (assets/known-groups/{slug}.json): check_groups.py cannot gate publication yet')
    else:
        groups, problem = json_list(known, 'groups')
        if groups is None:
            errors.append(f'known-groups file assets/known-groups/{slug}.json: {problem}')
    return errors, warnings


def report(slug: str, root: Path = SKILL_ROOT) -> str:
    errors, warnings = check_pack(slug, root)
    data = examine(root / 'domain-cache' / f'{slug}.yaml')[1] or {}
    counts = ', '.join(f'{key} {len(data[key]) if isinstance(data.get(key), list) else "?"}'
                       for key in ('openalex_topics', 'labs', 'companies', 'keywords'))
    return (f'{"FAIL" if errors else "ok"} {slug}: {len(data)} keys; {counts}'
            + ''.join(f'\n  error: {e}' for e in errors) + ''.join(f'\n  warning: {w}' for w in warnings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('slugs', nargs='*')
    parser.add_argument('--template', action='store_true', help='also check assets/domain-map.template.yaml')
    args = parser.parse_args()
    if not args.slugs and not args.template:
        parser.error('name at least one slug, or --template')
    lines = []
    if args.template:
        errors = check_file(TEMPLATE, template=True)
        lines.append(f'{"FAIL" if errors else "ok"} template {TEMPLATE.name}' + ''.join(f'\n  error: {e}' for e in errors))
    lines += [report(slug) for slug in args.slugs]
    print('\n'.join(lines))
    sys.exit(1 if any(line.startswith('FAIL') for line in lines) else 0)


if __name__ == '__main__':
    main()
