# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mapkureader** is a standalone "Machines Reading Maps" tool combining functionality inspired by MapReader and MapKurator. It provides text extraction, visual classification, and georeferencing for historical map images. Licensed under The Unlicense (public domain).

## Build & Install

```bash
pip install -e .            # install in development mode
pip install -e ".[dev]"     # with dev tools (pytest, ruff)
pip install -e ".[text]"    # with text spotting deps (torch, transformers)
pip install -e ".[classify]" # with classification deps (torch, scikit-learn)
```

## Testing & Linting

```bash
pytest                      # run all tests
pytest tests/test_load.py   # run a single test file
ruff check src/             # lint
ruff format src/            # format
```

## Architecture

Uses `src/` layout — all source code lives under `src/mapkureader/`.

| Module | Purpose | Status |
|--------|---------|--------|
| `load/` | Image loading, patchifying, georeferencing, downloading | Core implemented |
| `classify/` | PyTorch patch classification (fine-tune pretrained CNNs) | Not yet built |
| `spot_text/` | Text detection & recognition on map patches | Not yet built |
| `postprocess/` | OCR correction, entity linking to OSM | Not yet built |
| `utils/` | Visualization helpers | Stub |

### Load module (`load/`)

- `images.py` — `MapImage` (loads PNG/JPG/TIFF/GeoTIFF, extracts CRS), `PatchSet` (grid of patches with geo bounds), `Patch` (single patch dataclass)
- `geo.py` — Coordinate transforms: `pixel_to_geo`, `geo_to_pixel`, `get_patch_geo_bounds`, `reproject_bounds`
- `downloader.py` — `TileDownloader`, `IIIFDownloader` (stubs)

### Key patterns

- GeoTIFF images carry CRS and affine transform; regular images (PNG/JPG) are pixel-only
- `MapImage.patchify()` produces a `PatchSet` — patches carry both pixel and geographic bounds
- `maps/` directory is for local GeoTIFF storage
