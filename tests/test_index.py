"""Testy zoznamu krajín (Geofabrik) a zlučovania indexu."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

GEOFABRIK = {'type': 'FeatureCollection', 'features': [
    {'type': 'Feature', 'properties': {'id': 'europe', 'name': 'Europe', 'urls': {'pbf': 'https://download.geofabrik.de/europe-latest.osm.pbf'}}},
    {'type': 'Feature', 'properties': {'id': 'slovakia', 'parent': 'europe', 'name': 'Slovakia', 'iso3166-1:alpha2': ['SK'],
                                       'urls': {'pbf': 'https://download.geofabrik.de/europe/slovakia-latest.osm.pbf'}}},
    {'type': 'Feature', 'properties': {'id': 'great-britain', 'parent': 'europe', 'name': 'Great Britain', 'iso3166-2': ['GB-ENG'],
                                       'urls': {'pbf': 'https://download.geofabrik.de/europe/great-britain-latest.osm.pbf'}}},
    # spojené oblasti (DACH, Alpy) sa prekrývajú s krajinami → nie
    {'type': 'Feature', 'properties': {'id': 'dach', 'parent': 'europe', 'name': 'Germany, Austria, Switzerland',
                                       'urls': {'pbf': 'https://download.geofabrik.de/europe/dach-latest.osm.pbf'}}},
    {'type': 'Feature', 'properties': {'id': 'bayern', 'parent': 'germany', 'name': 'Bayern', 'iso3166-2': ['DE-BY'],
                                       'urls': {'pbf': 'https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf'}}},
    {'type': 'Feature', 'properties': {'id': 'russia', 'name': 'Russian Federation', 'iso3166-1:alpha2': ['RU'],
                                       'urls': {'pbf': 'https://download.geofabrik.de/russia-latest.osm.pbf'}}},
]}


def meta(cid, name, built, version='2026-11-20'):
    return {'id': cid, 'name': name, 'version': version, 'count': 10, 'bytes': 100, 'sha256': 'a' * 64, 'content': 'b' * 64,
            'bbox': [48, 17, 49, 18], 'built': built}


class IndexTest(unittest.TestCase):
    def test_krajiny_europy_z_indexu_geofabrik(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / 'index.json'
            f.write_text(json.dumps(GEOFABRIK))
            out = json.loads(subprocess.run([sys.executable, str(ROOT / 'countries.py'), '--geofabrik-index', str(f)],
                                            check=True, capture_output=True, text=True).stdout)
        self.assertEqual(out, [
            {'id': 'great-britain', 'name': 'Great Britain', 'url': 'https://download.geofabrik.de/europe/great-britain-latest.osm.pbf'},
            {'id': 'slovakia', 'name': 'Slovakia', 'url': 'https://download.geofabrik.de/europe/slovakia-latest.osm.pbf'},
        ])

    def test_zlucenie_indexu(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / 'a.meta.json').write_text(json.dumps(meta('slovakia', 'Slovakia', '2026-11-20T02:00:00Z', '2026-11-19')))
            (d / 'a2.meta.json').write_text(json.dumps(meta('slovakia', 'Slovakia', '2026-11-22T02:00:00Z', '2026-11-21')))
            (d / 'b.meta.json').write_text(json.dumps(meta('austria', 'Austria', '2026-11-21T02:00:00Z')))
            (d / 'zle.meta.json').write_text('{nie je json')
            (d / 'neuplne.meta.json').write_text(json.dumps({'id': 'x'}))
            out = d / 'index.json'
            subprocess.run([sys.executable, str(ROOT / 'merge_index.py'), '-o', str(out), *sorted(map(str, d.glob('*.meta.json')))],
                           check=True, capture_output=True, text=True)
            idx = json.loads(out.read_text())
        self.assertEqual([c['id'] for c in idx['countries']], ['austria', 'slovakia'], 'podľa názvu, bez poškodených')
        self.assertEqual(idx['countries'][1]['version'], '2026-11-21', 'novšie spracovanie vyhráva')
        self.assertRegex(idx['generated'], r'^\d{4}-\d\d-\d\dT')


if __name__ == '__main__':
    unittest.main()
