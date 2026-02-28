#!/usr/bin/env python3
"""Demo: fetch a random IIIF map, patchify it, and view interactively in the browser.

Usage:
    python demo.py [--patch-size 256] [--max-size 2000]

Controls:
    Pan/zoom with mouse.  Press 'g' to toggle the patch grid.
"""

import argparse
import base64
import io
import json
import random
import tempfile
import webbrowser

from PIL import Image

from mapkureader.load import IIIFDownloader

# Two public IIIF manifest endpoints for historical maps
MANIFESTS = [
    # David Rumsey Collection via Stanford — "Atlas of the United States, Central States"
    "https://purl.stanford.edu/fh219yb6573/iiif/manifest",
    # David Rumsey Collection — "The Histomap"
    "https://www.davidrumsey.com/luna/servlet/iiif/m/RUMSEY~8~1~200375~3001080/manifest",
]


def main():
    parser = argparse.ArgumentParser(description="mapkureader interactive demo")
    parser.add_argument("--patch-size", type=int, default=256, help="Patch size in pixels")
    parser.add_argument("--max-size", type=int, default=2000, help="Max image dimension (px)")
    args = parser.parse_args()

    manifest_url = random.choice(MANIFESTS)
    print(f"Manifest: {manifest_url}")

    dl = IIIFDownloader.from_manifest(manifest_url)
    print(f"Image:    {dl}")

    map_img = dl.download(max_size=args.max_size, save=False)
    print(f"Size:     {map_img.width} x {map_img.height}")

    patches = map_img.patchify(patch_size=args.patch_size, overlap=0, skip_blank=False)
    print(f"Patches:  {len(patches)}")

    # Encode raster as base64 JPEG for embedding in the HTML page
    pil_img = Image.fromarray(map_img.data)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    # Collect patch grid rectangles
    grid = []
    for p in patches:
        x, y, w, h = p.pixel_bounds
        grid.append({"x": x, "y": y, "w": w, "h": h, "row": p.row, "col": p.col})

    title = dl.label or "IIIF Map"
    html = _build_html(img_b64, map_img.width, map_img.height, grid, title)

    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
    tmp.write(html)
    tmp.close()
    print(f"Opening:  {tmp.name}")
    webbrowser.open(f"file://{tmp.name}")


def _build_html(img_b64: str, width: int, height: int, grid: list, title: str) -> str:
    grid_json = json.dumps(grid)
    # Escaping braces for f-string: {{ and }} become literal { and }
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title} &mdash; mapkureader demo</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body {{ margin: 0; }}
  #map {{ width: 100vw; height: 100vh; background: #1a1a2e; }}
  .info {{
    position: absolute; top: 10px; right: 10px; z-index: 1000;
    background: rgba(0,0,0,0.78); color: #eee; padding: 12px 16px;
    border-radius: 8px; font: 13px/1.5 system-ui, sans-serif;
    max-width: 360px; backdrop-filter: blur(6px);
  }}
  .info h3 {{ margin: 0 0 4px; font-size: 15px; color: #fff; }}
  .info kbd {{
    background: #333; padding: 1px 5px; border-radius: 3px;
    font-size: 12px; border: 1px solid #555;
  }}
</style>
</head>
<body>
<div id="map"></div>
<div class="info">
  <h3>{title}</h3>
  <div>{len(grid)} patches &middot; {width}&times;{height}px</div>
  <div style="margin-top:4px">Press <kbd>g</kbd> to toggle grid</div>
</div>
<script>
var W = {width}, H = {height};
var grid = {grid_json};

var map = L.map('map', {{
  crs: L.CRS.Simple,
  minZoom: -3,
  maxZoom: 5,
  zoomSnap: 0.25
}});

// CRS.Simple has y-up; image has y-down — negate y so origin is top-left.
var bounds = [[0, 0], [-H, W]];
L.imageOverlay('data:image/jpeg;base64,{img_b64}', bounds).addTo(map);
map.fitBounds(bounds);

// Draw patch graticule
var gridLayer = L.layerGroup().addTo(map);
grid.forEach(function(p) {{
  var rect = L.rectangle(
    [[-p.y, p.x], [-(p.y + p.h), p.x + p.w]],
    {{ color: '#00e5ff', weight: 1, fillOpacity: 0, opacity: 0.55 }}
  );
  rect.bindTooltip(
    'r' + p.row + ', c' + p.col + '<br>' + p.w + '&times;' + p.h + 'px',
    {{ sticky: true }}
  );
  gridLayer.addLayer(rect);
}});

// Toggle grid with 'g'
var gridOn = true;
document.addEventListener('keydown', function(e) {{
  if (e.key === 'g') {{
    gridOn = !gridOn;
    if (gridOn) gridLayer.addTo(map); else gridLayer.remove();
  }}
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
