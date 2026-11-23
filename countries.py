#!/usr/bin/env python3
"""Krajiny Európy z indexu Geofabrik (index-v1-nogeom.json) → [{id, name, url}] zoradené podľa id.

Berú sa len priame deti „europe" s kódom krajiny (ISO 3166-1 alebo 3166-2, napr. great-britain); spojené oblasti
(dach, alps, britain-and-ireland) kód nemajú a prekrývali by sa s krajinami.
"""
import argparse
import json
import pathlib


def europe(index: dict) -> list:
    out = []
    for f in index.get('features', []):
        p = f.get('properties', {})
        url = p.get('urls', {}).get('pbf', '')
        if p.get('parent') == 'europe' and (p.get('iso3166-1:alpha2') or p.get('iso3166-2')) and url.endswith('.osm.pbf'):
            out.append({'id': p['id'], 'name': p['name'], 'url': url})
    return sorted(out, key=lambda c: c['id'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--geofabrik-index', required=True, type=pathlib.Path)
    a = ap.parse_args()
    print(json.dumps(europe(json.loads(a.geofabrik_index.read_text(encoding='utf-8'))), ensure_ascii=False))
