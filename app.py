"""Streamlit app: interactive pan/zoom viewer for a IIIF historical map."""

import base64
import io
import json
import random

import streamlit as st
from PIL import Image

from mapkureader.load import IIIFDownloader

MANIFESTS = [
    "https://purl.stanford.edu/fh219yb6573/iiif/manifest",
    "https://www.davidrumsey.com/luna/servlet/iiif/m/RUMSEY~8~1~200375~3001080/manifest",
]

st.set_page_config(page_title="mapkureader", layout="wide")


@st.cache_data(show_spinner="Downloading from IIIF...")
def load_map(manifest_url: str, max_size: int, patch_size: int):
    dl = IIIFDownloader.from_manifest(manifest_url)
    map_img = dl.download(max_size=max_size, save=False)
    patches = map_img.patchify(patch_size=patch_size, overlap=0, skip_blank=False)

    pil_img = Image.fromarray(map_img.data)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    grid = []
    for p in patches:
        x, y, w, h = p.pixel_bounds
        grid.append({"x": x, "y": y, "w": w, "h": h, "row": p.row, "col": p.col})

    return {
        "img_b64": img_b64,
        "width": map_img.width,
        "height": map_img.height,
        "grid": grid,
        "title": dl.label or "IIIF Map",
        "n_patches": len(patches),
    }


def leaflet_html(data: dict) -> str:
    grid_json = json.dumps(data["grid"])
    W, H = data["width"], data["height"]
    title = data["title"]
    n = data["n_patches"]
    img_b64 = data["img_b64"]

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; }}
  #map {{ width: 100%; height: 100%; background: #1a1a2e; }}
  .info {{
    position: absolute; top: 10px; right: 10px; z-index: 1000;
    background: rgba(0,0,0,0.78); color: #eee; padding: 10px 14px;
    border-radius: 8px; font: 13px/1.5 system-ui, sans-serif;
    max-width: 340px; backdrop-filter: blur(6px);
  }}
  .info h3 {{ margin: 0 0 4px; font-size: 14px; color: #fff; }}
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
  <div>{n} patches &middot; {W}&times;{H}px</div>
  <div style="margin-top:4px">Press <kbd>g</kbd> to toggle grid</div>
</div>
<script>
var W = {W}, H = {H};
var grid = {grid_json};

var map = L.map('map', {{
  crs: L.CRS.Simple,
  minZoom: -3,
  maxZoom: 5,
  zoomSnap: 0.25
}});

var bounds = [[0, 0], [-H, W]];
L.imageOverlay('data:image/jpeg;base64,{img_b64}', bounds).addTo(map);
map.fitBounds(bounds);

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


# --- Pick a random manifest (stable per session) ---
if "manifest" not in st.session_state:
    st.session_state.manifest = random.choice(MANIFESTS)

manifest = st.session_state.manifest

with st.sidebar:
    st.header("mapkureader")
    patch_size = st.slider("Patch size (px)", 64, 512, 256, step=64)
    max_size = st.slider("Max download size (px)", 1000, 4000, 2000, step=500)
    if st.button("Re-roll map"):
        st.session_state.manifest = random.choice(MANIFESTS)
        st.rerun()
    st.caption(f"Source: {manifest}")

data = load_map(manifest, max_size, patch_size)

st.components.v1.html(leaflet_html(data), height=750, scrolling=False)
