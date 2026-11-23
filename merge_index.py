#!/usr/bin/env python3
"""Zlúči <krajina>.meta.json do index.json, ktorý číta aplikácia na WEDOS (zoznam krajín, verzie, veľkosti, sha256).

Poškodené alebo neúplné súbory preskočí; pri viacerých verziách tej istej krajiny ostane novšie spracovanie (built).
"""
import argparse
import datetime
import json
import pathlib
import sys

KEYS = ('id', 'name', 'version', 'count', 'bytes', 'sha256', 'content', 'bbox', 'built')


def merge(paths) -> dict:
    best = {}
    for p in paths:
        try:
            m = json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
        except (OSError, ValueError) as ex:
            print(f'preskakujem {p}: {ex}', file=sys.stderr)
            continue
        if not isinstance(m, dict) or any(k not in m for k in KEYS):
            print(f'preskakujem {p}: neúplné', file=sys.stderr)
            continue
        if m['id'] not in best or m['built'] > best[m['id']]['built']:
            best[m['id']] = {k: m[k] for k in KEYS}
    return {
        'generated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'countries': sorted(best.values(), key=lambda m: m['name']),
    }


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('-o', '--out', required=True, type=pathlib.Path)
    ap.add_argument('meta', nargs='*')
    a = ap.parse_args()
    a.out.write_text(json.dumps(merge(a.meta), ensure_ascii=False, indent=1), encoding='utf-8')
