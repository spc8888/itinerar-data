#!/usr/bin/env python3
"""Spracovanie jednej krajiny pre aplikáciu Itinerár.

Výrez OpenStreetMap (Geofabrik .osm.pbf, v testoch aj .osm) → miesta kategórií aplikácie → <id>.jsonl.gz + <id>.meta.json.
Riadok = prvok ako z Overpass (`out center tags`): type, id, lat, lon (pri cestách a reláciách stred obálky), tags
(len tie, ktoré aplikácia číta) a wd (známosť, fotka, popis z Wikidata) – triedenie do kategórií robí aplikácia
(osm_classify v PHP), aby pravidlá boli na jednom mieste.

Potrebuje osmium-tool (osmium tags-filter, osmium export). Len štandardná knižnica Pythonu.
"""
import argparse
import datetime
import gzip
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
FILTERS = HERE / 'filters.txt'
SPARQL = 'https://query.wikidata.org/sparql'
USER_AGENT = 'itinerar-data/1.0 (https://github.com/spc8888/itinerar-data)'
WD_BATCH = 200
TYPE_ORDER = {'node': 0, 'way': 1, 'relation': 2}

# Tagy, ktoré čítajú osm_classify() a osm_parse() v aplikácii; ostatné sa zahodia (menší súbor aj databáza).
KEEP_TAGS = {
    'name', 'name:sk', 'name:cs', 'historic', 'ruins', 'castle_type', 'tourism', 'natural', 'amenity', 'leisure', 'building',
    'ele', 'wikidata', 'wikipedia', 'opening_hours', 'fee', 'charge', 'dog', 'wheelchair', 'website', 'contact:website',
    'phone', 'contact:phone', 'addr:street', 'addr:place', 'addr:housenumber', 'addr:city',
}
QID = re.compile(r'^Q\d+$')


def wanted(t: dict, osm_type: str) -> bool:
    """Rovnaké podmienky ako osm_statements() v aplikácii (bez obmedzenia pre veľký okruh) + gastro."""
    if not t.get('name'):
        return False
    tour, nat, lei, hist, am = (t.get(k, '') for k in ('tourism', 'natural', 'leisure', 'historic', 'amenity'))
    return (
        tour in ('viewpoint', 'attraction', 'museum', 'gallery', 'zoo', 'theme_park', 'aquarium')
        or nat in ('waterfall', 'cave_entrance', 'gorge', 'arch', 'rock', 'hot_spring')
        or (nat == 'peak' and osm_type == 'node' and ('ele' in t or QID.match(t.get('wikidata', ''))))
        or lei in ('nature_reserve', 'water_park')
        or hist in ('castle', 'fort', 'manor', 'monument', 'archaeological_site', 'monastery')
        or (hist == 'ruins' and t.get('ruins') == 'castle')
        or (am == 'place_of_worship' and bool(QID.match(t.get('wikidata', ''))))
        or am in ('public_bath', 'restaurant', 'cafe')
    )


def bbox_center(coords):
    """Stred obálky súradníc GeoJSON (ľubovoľne vnorené [lon, lat])."""
    lons, lats = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            lons.append(c[0])
            lats.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(coords)
    return round((min(lats) + max(lats)) / 2, 6), round((min(lons) + max(lons)) / 2, 6)


def extract(pbf: pathlib.Path) -> list:
    """osmium: výber podľa filters.txt → GeoJSON → prvky v tvare Overpass."""
    with tempfile.TemporaryDirectory() as tmp:
        small = pathlib.Path(tmp) / 'f.osm.pbf'
        seq = pathlib.Path(tmp) / 'f.geojsonseq'
        subprocess.run(['osmium', 'tags-filter', str(pbf), '-e', str(FILTERS), '-o', str(small), '--overwrite'], check=True)
        subprocess.run(['osmium', 'export', str(small), '-f', 'geojsonseq', '-a', 'type,id',
                        '--geometry-types=point,linestring,polygon', '-o', str(seq), '--overwrite'], check=True)
        out = {}
        with open(seq, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip().lstrip('\x1e')
                if not line:
                    continue
                f = json.loads(line)
                p = f['properties']
                typ, oid = p.pop('@type'), int(p.pop('@id'))
                # Uzavretá cesta môže prísť ako čiara aj ako plocha – stačí raz.
                if (typ, oid) in out or not wanted(p, typ):
                    continue
                lat, lon = bbox_center(f['geometry']['coordinates'])
                out[(typ, oid)] = {'type': typ, 'id': oid, 'lat': lat, 'lon': lon,
                                   'tags': {k: v for k, v in sorted(p.items()) if k in KEEP_TAGS}, 'wd': None}
    return [out[k] for k in sorted(out, key=lambda k: (TYPE_ORDER[k[0]], k[1]))]


def sparql_batch(endpoint: str, qids: list) -> dict:
    query = ('SELECT ?item ?links ?img ?desc ?lang WHERE { VALUES ?item { ' + ' '.join('wd:' + q for q in qids) + ' } '
             'OPTIONAL { ?item wikibase:sitelinks ?links } OPTIONAL { ?item wdt:P18 ?img } '
             'OPTIONAL { ?item schema:description ?desc FILTER(LANG(?desc) IN ("sk", "cs", "en")) BIND(LANG(?desc) AS ?lang) } }')
    req = urllib.request.Request(endpoint + '?format=json&query=' + urllib.parse.quote(query),
                                 headers={'Accept': 'application/sparql-results+json', 'User-Agent': USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                rows = json.load(r)['results']['bindings']
            break
        except Exception as ex:  # sieť, 429, 504 – skúsiť znova, potom vzdať (build nespadne)
            print(f'wikidata: {ex}', file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    else:
        return {}
    pri = {'sk': 0, 'cs': 1, 'en': 2}
    res, best = {}, {}
    for r in rows:
        q = r['item']['value'].rsplit('/', 1)[-1]
        e = res.setdefault(q, {'pop': 0, 'img': None, 'desc': None})
        if 'links' in r:
            e['pop'] = max(e['pop'], int(r['links']['value']))
        if 'img' in r and not e['img']:
            e['img'] = urllib.parse.unquote(r['img']['value'].rsplit('Special:FilePath/', 1)[-1])
        if 'desc' in r and pri.get(r.get('lang', {}).get('value'), 9) < best.get(q, 9):
            best[q] = pri[r['lang']['value']]
            e['desc'] = r['desc']['value']
    return res


def enrich(items: list, endpoint: str = None, fixed: dict = None) -> None:
    qids = sorted({e['tags']['wikidata'] for e in items if QID.match(e['tags'].get('wikidata', ''))})
    found, failed = dict(fixed or {}), set()
    if endpoint:
        for i in range(0, len(qids), WD_BATCH):
            batch = qids[i:i + WD_BATCH]
            res = sparql_batch(endpoint, batch)
            if not res and batch:
                failed.update(batch)
            found.update(res)
            time.sleep(0.2)   # Wikidata: najviac 60 s výpočtu za minútu na IP
    for e in items:
        q = e['tags'].get('wikidata', '')
        if QID.match(q) and q not in failed and (endpoint or fixed is not None):
            e['wd'] = found.get(q, {'pop': 0, 'img': None, 'desc': None})


def data_version(pbf: pathlib.Path) -> str:
    try:
        ts = subprocess.run(['osmium', 'fileinfo', '-g', 'header.option.osmosis_replication_timestamp', str(pbf)],
                            check=True, capture_output=True, text=True).stdout.strip()
        if ts:
            return ts
    except subprocess.CalledProcessError:
        pass
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def write(out: pathlib.Path, cid: str, name: str, version: str, items: list) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    raw = ''.join(json.dumps(e, ensure_ascii=False, separators=(',', ':')) + '\n' for e in items).encode('utf-8')
    buf = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(raw)
    data = buf.getvalue()
    (out / f'{cid}.jsonl.gz').write_bytes(data)
    lats = [e['lat'] for e in items] or [0]
    lons = [e['lon'] for e in items] or [0]
    meta = {
        'id': cid, 'name': name, 'version': version, 'count': len(items), 'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(), 'content': hashlib.sha256(raw).hexdigest(),
        'bbox': [min(lats), min(lons), max(lats), max(lons)],
        'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    (out / f'{cid}.meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--id', required=True, help='id výrezu Geofabrik, napr. slovakia')
    ap.add_argument('--name', required=True)
    ap.add_argument('--pbf', required=True, type=pathlib.Path)
    ap.add_argument('--out', required=True, type=pathlib.Path)
    ap.add_argument('--version')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--wikidata', default=SPARQL, help='adresa SPARQL (predvolene query.wikidata.org)')
    g.add_argument('--no-wikidata', action='store_true')
    g.add_argument('--wd-json', type=pathlib.Path, help='pevné údaje Wikidata {QID: {pop, img, desc}} (testy)')
    a = ap.parse_args(argv)
    items = extract(a.pbf)
    if a.wd_json:
        enrich(items, fixed=json.loads(a.wd_json.read_text(encoding='utf-8')))
    elif not a.no_wikidata:
        enrich(items, endpoint=a.wikidata)
    meta = write(a.out, a.id, a.name, a.version or data_version(a.pbf), items)
    print(json.dumps({k: meta[k] for k in ('id', 'count', 'bytes', 'version')}))


if __name__ == '__main__':
    main()
