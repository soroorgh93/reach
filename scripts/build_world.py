"""Build web/assets/world.json from Natural Earth 1:50m admin-0 countries (public domain):
iso3, name, and polygons rounded to 0.01 degree. Run once:  python scripts/build_world.py [path.geojson]"""
import json, sys, urllib.request
from pathlib import Path
SRC = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
ROOT = Path(__file__).resolve().parent.parent

def rnd(ring):
    out, last = [], None
    for x, y in ring:
        p = [round(x, 2), round(y, 2)]
        if p != last: out.append(p); last = p
    return out if len(out) >= 4 else None

def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else json.loads(urllib.request.urlopen(SRC).read())
    feats = []
    for f in data["features"]:
        p, g = f["properties"], f["geometry"]
        if not g: continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        mp = [[r for r in (rnd(ring) for ring in poly) if r] for poly in polys]
        mp = [poly for poly in mp if poly]
        feats.append({"type": "Feature", "id": p.get("ADM0_A3"), "properties": {"name": p.get("NAME"), "iso3": p.get("ADM0_A3")}, "geometry": {"type": "MultiPolygon", "coordinates": mp}})
    out = ROOT / "web" / "assets" / "world.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "source": "Natural Earth 1:50m (public domain)", "features": feats}, separators=(",", ":")), encoding="utf-8")
    print("wrote", out, len(feats), "countries", round(out.stat().st_size / 1e6, 2), "MB")

if __name__ == "__main__":
    main()
