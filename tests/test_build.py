"""Testy spracovania krajiny: python3 -m unittest -v (v priečinku data-pipeline). Potrebuje osmium-tool."""
import gzip
import hashlib
import http.server
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
BUILD = HERE.parent / 'build.py'
FIXTURE = HERE / 'fixture.osm'


def run_build(out, *extra):
    subprocess.run([sys.executable, str(BUILD), '--id', 'testland', '--name', 'Testland', '--pbf', str(FIXTURE),
                    '--out', str(out), '--version', '2026-11-01', *extra], check=True, capture_output=True, text=True)
    lines = [json.loads(x) for x in gzip.open(out / 'testland.jsonl.gz', 'rt', encoding='utf-8')]
    meta = json.loads((out / 'testland.meta.json').read_text(encoding='utf-8'))
    return {(e['type'][0] + str(e['id'])): e for e in lines}, meta


class SparqlMock(http.server.BaseHTTPRequestHandler):
    """Simulovaná Wikidata: pozná len Q100 (hrad)."""
    queries = []

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)['query'][0]
        SparqlMock.queries.append(q)
        rows = []
        if 'wd:Q100' in q:
            ent = {'type': 'uri', 'value': 'http://www.wikidata.org/entity/Q100'}
            rows = [
                {'item': ent, 'links': {'value': '12'}, 'img': {'value': 'http://commons.wikimedia.org/wiki/Special:FilePath/Hrad%20Testov.jpg'},
                 'desc': {'value': 'hrad na Slovensku'}, 'lang': {'value': 'sk'}},
                {'item': ent, 'links': {'value': '12'}, 'desc': {'value': 'castle in Slovakia'}, 'lang': {'value': 'en'}},
            ]
        body = json.dumps({'results': {'bindings': rows}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/sparql-results+json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_vyber_miest_a_atributy(self):
        items, meta = run_build(self.out, '--no-wikidata')
        self.assertEqual(sorted(items), ['n1', 'n3', 'n4', 'n5', 'n7', 'n8', 'r30', 'w10'])
        # vrchol bez výšky, kostol bez wikidata, ulica a atrakcia bez mena nepatria do výstupu
        for k in ['n2', 'n6', 'w20', 'n9']:
            self.assertNotIn(k, items)
        hrad = items['n1']
        self.assertEqual((hrad['lat'], hrad['lon']), (48.8945, 18.0444))
        self.assertEqual(hrad['tags']['opening_hours'], 'Tu-Su 09:00-17:00')
        self.assertEqual(hrad['tags']['charge'], '8 EUR')
        self.assertNotIn('source', hrad['tags'], 'len tagy, ktoré aplikácia číta')
        self.assertIsNone(hrad['wd'], 'bez Wikidata')
        # stred cesty a relácie = stred obálky
        self.assertEqual((items['w10']['lat'], items['w10']['lon']), (48.701, 17.902))
        self.assertEqual((items['r30']['lat'], items['r30']['lon']), (49.005, 18.21))
        self.assertEqual(items['r30']['tags']['leisure'], 'nature_reserve')
        self.assertEqual(meta['count'], 8)
        self.assertEqual(meta['bbox'], [48.701, 17.902, 49.005, 18.21])
        self.assertEqual((meta['id'], meta['name'], meta['version']), ('testland', 'Testland', '2026-11-01'))
        gz = (self.out / 'testland.jsonl.gz').read_bytes()
        self.assertEqual(meta['sha256'], hashlib.sha256(gz).hexdigest())
        self.assertEqual(meta['bytes'], len(gz))
        self.assertEqual(meta['content'], hashlib.sha256(gzip.decompress(gz)).hexdigest())

    def test_rovnaky_vstup_rovnake_bajty(self):
        _, a = run_build(self.out, '--no-wikidata')
        other = self.out / 'b'
        other.mkdir()
        _, b = run_build(other, '--no-wikidata')
        self.assertEqual(a['sha256'], b['sha256'])

    def test_wikidata_znamost_fotka_popis(self):
        srv = http.server.HTTPServer(('127.0.0.1', 0), SparqlMock)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            items, _ = run_build(self.out, '--wikidata', f'http://127.0.0.1:{srv.server_port}/sparql')
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(items['n1']['wd'], {'pop': 12, 'img': 'Hrad Testov.jpg', 'desc': 'hrad na Slovensku'})
        self.assertEqual(items['n7']['wd'], {'pop': 0, 'img': None, 'desc': None}, 'QID, ktorý Wikidata nepozná')
        self.assertIsNone(items['n3']['wd'], 'bez wikidata tagu')
        self.assertTrue(any('wd:Q100' in q and 'wd:Q200' in q for q in SparqlMock.queries))


if __name__ == '__main__':
    unittest.main()
