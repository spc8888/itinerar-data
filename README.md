# itinerar-data

Miesta (hrady, príroda, pamiatky, múzeá, zábava, kúpele, gastro) z **OpenStreetMap** pre celú Európu, spracované po krajinách
pre aplikáciu **Itinerár** (vylet.deaworks.eu). Aplikácia si súbory sťahuje do vlastnej databázy na webhostingu a hľadá len v nej.

- Zdroj máp: výrezy [Geofabrik](https://download.geofabrik.de/europe.html), spracovanie `osmium` (`filters.txt`) + `build.py`.
- Známosť (počet Wikipédií), fotka a popis: [Wikidata](https://www.wikidata.org/) (CC0).
- Výsledok: Release [`data`](../../releases/tag/data) – `<krajina>.jsonl.gz` (riadok = prvok ako z Overpass: type, id, lat, lon,
  tags, wd), `<krajina>.meta.json` a `index.json` (verzia, počet, veľkosť, sha256, obálka).
- Automat (`.github/workflows/build.yml`): denne krajiny, ktoré má aplikácia načítané, v nedeľu celá Európa; krajina bez zmeny
  obsahu sa nenahrá znova. Ručne: Actions → build → Run workflow → `countries: slovakia czech-republic`.

## Licencia

Údaje: © prispievatelia OpenStreetMap, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) – odvodená databáza je
voľne dostupná tu. Údaje Wikidata: CC0. Skripty: MIT.

## Vývoj

```bash
sudo apt-get install osmium-tool
python3 -m unittest -v          # testy na malej vzorovej krajine (tests/fixture.osm)
python3 build.py --id slovakia --name Slovakia --pbf slovakia-latest.osm.pbf --out out
```
