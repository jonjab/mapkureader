"""Map tile and IIIF downloading."""

from __future__ import annotations

import json
import math
import re
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image


class IIIFDownloader:
    """Download map images from IIIF Image API endpoints.

    Supports two entry points:
      - From a IIIF manifest URL (parses to find image services)
      - From a direct IIIF image service URL

    Downloads large images in tiles and stitches them together, respecting
    the server's tile size configuration.

    Example usage::

        dl = IIIFDownloader.from_manifest("https://purl.stanford.edu/fh219yb6573/iiif/manifest")
        map_img = dl.download()           # full resolution
        map_img = dl.download(max_size=2000)  # scaled down
    """

    def __init__(
        self,
        image_service_url: str,
        width: int,
        height: int,
        tile_size: int = 1024,
        scale_factors: list[int] | None = None,
        label: str = "",
        output_dir: str | Path = "maps",
    ) -> None:
        self.image_service_url = image_service_url.rstrip("/")
        self.width = width
        self.height = height
        self.tile_size = tile_size
        self.scale_factors = scale_factors or [1]
        self.label = label
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_manifest(cls, manifest_url: str, **kwargs) -> IIIFDownloader:
        """Create an IIIFDownloader by parsing a IIIF manifest.

        Extracts the first image service URL, dimensions, and tile config.
        """
        data = _fetch_json(manifest_url)
        label = data.get("label", "")
        if isinstance(label, dict):
            # IIIF v3 labels are {"en": ["..."]}
            for vals in label.values():
                label = vals[0] if vals else ""
                break

        # Navigate manifest structure to find the image resource
        service_url, width, height = _parse_manifest_image(data)

        # Fetch the info.json for tile configuration
        info = _fetch_json(f"{service_url}/info.json")
        tile_size = 1024
        scale_factors = [1]
        if "tiles" in info and info["tiles"]:
            tile_info = info["tiles"][0]
            tile_size = tile_info.get("width", 1024)
            scale_factors = tile_info.get("scaleFactors", [1])

        return cls(
            image_service_url=service_url,
            width=width,
            height=height,
            tile_size=tile_size,
            scale_factors=scale_factors,
            label=str(label),
            **kwargs,
        )

    @classmethod
    def from_image_url(cls, image_service_url: str, **kwargs) -> IIIFDownloader:
        """Create an IIIFDownloader from a direct IIIF image service URL."""
        info = _fetch_json(f"{image_service_url}/info.json")
        width = info["width"]
        height = info["height"]

        tile_size = 1024
        scale_factors = [1]
        if "tiles" in info and info["tiles"]:
            tile_info = info["tiles"][0]
            tile_size = tile_info.get("width", 1024)
            scale_factors = tile_info.get("scaleFactors", [1])

        label = info.get("label", "")

        return cls(
            image_service_url=image_service_url,
            width=width,
            height=height,
            tile_size=tile_size,
            scale_factors=scale_factors,
            label=str(label),
            **kwargs,
        )

    def download(self, max_size: int | None = None, save: bool = True) -> "MapImage":
        """Download the image and return a MapImage.

        Args:
            max_size: If set, the longer edge is scaled to this many pixels.
                Uses the IIIF size parameter for server-side scaling.
            save: If True, saves the downloaded image to output_dir.

        Returns:
            A MapImage instance with the downloaded pixel data.
        """
        from .images import MapImage

        if max_size and max(self.width, self.height) > max_size:
            return self._download_scaled(max_size, save=save)

        return self._download_tiled(save=save)

    def _download_scaled(self, max_size: int, save: bool) -> "MapImage":
        """Download a scaled-down version in a single request."""
        from .images import MapImage

        size_param = f"!{max_size},{max_size}"
        url = f"{self.image_service_url}/full/{size_param}/0/default.jpg"
        print(f"Downloading scaled image ({max_size}px)...")

        img = _fetch_image(url)
        data = np.array(img)

        path = None
        if save:
            filename = _make_filename(self.image_service_url, self.label, suffix=f"_{max_size}px")
            path = self.output_dir / filename
            img.save(path)
            print(f"Saved to {path}")

        return MapImage(data=data, path=path)

    def _download_tiled(self, save: bool) -> "MapImage":
        """Download full-resolution image by fetching tiles and stitching."""
        from .images import MapImage

        tile_sz = self.tile_size
        cols = math.ceil(self.width / tile_sz)
        rows = math.ceil(self.height / tile_sz)
        total = cols * rows

        print(f"Downloading {self.width}x{self.height} in {total} tiles ({cols}x{rows})...")

        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        for row in range(rows):
            for col in range(cols):
                tile_num = row * cols + col + 1
                x = col * tile_sz
                y = row * tile_sz
                w = min(tile_sz, self.width - x)
                h = min(tile_sz, self.height - y)

                region = f"{x},{y},{w},{h}"
                url = f"{self.image_service_url}/{region}/full/0/default.jpg"

                print(f"  Tile {tile_num}/{total} [{region}]", end="\r")
                tile_img = _fetch_image(url)
                tile_arr = np.array(tile_img)

                # Handle tiles that may be slightly different sizes
                th, tw = tile_arr.shape[:2]
                canvas[y : y + th, x : x + tw] = tile_arr[:, :, :3]

        print(f"  Done — {total} tiles stitched.         ")

        path = None
        if save:
            filename = _make_filename(self.image_service_url, self.label)
            path = self.output_dir / filename
            Image.fromarray(canvas).save(path, quality=95)
            print(f"Saved to {path}")

        return MapImage(data=canvas, path=path)

    def get_region(self, x: int, y: int, w: int, h: int, scale: float = 1.0) -> np.ndarray:
        """Download a specific region of the image.

        Args:
            x: Left edge in pixels.
            y: Top edge in pixels.
            w: Width in pixels.
            h: Height in pixels.
            scale: Scale factor (0-1). E.g., 0.5 returns half resolution.

        Returns:
            numpy array of the region.
        """
        region = f"{x},{y},{w},{h}"
        if scale < 1.0:
            sw = max(1, int(w * scale))
            sh = max(1, int(h * scale))
            size = f"{sw},{sh}"
        else:
            size = "full"

        url = f"{self.image_service_url}/{region}/{size}/0/default.jpg"
        img = _fetch_image(url)
        return np.array(img)

    def __repr__(self) -> str:
        label_part = f" '{self.label}'" if self.label else ""
        return (
            f"IIIFDownloader({self.width}x{self.height}{label_part}, "
            f"tiles={self.tile_size}px)"
        )


class TileDownloader:
    """Download map tiles from XYZ tile servers.

    Not yet implemented.
    """

    def __init__(self, url_template: str, output_dir: str | Path = "maps") -> None:
        self.url_template = url_template
        self.output_dir = Path(output_dir)
        raise NotImplementedError("TileDownloader is not yet implemented")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str) -> dict:
    """Fetch and parse JSON from a URL."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _fetch_image(url: str) -> Image.Image:
    """Fetch an image from a URL and return a PIL Image."""
    import io

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    return Image.open(io.BytesIO(data)).convert("RGB")


def _parse_manifest_image(manifest: dict) -> tuple[str, int, int]:
    """Extract the first image service URL and dimensions from a IIIF manifest.

    Supports IIIF Presentation API v2 and v3.
    """
    # Try v2 structure: sequences -> canvases -> images -> resource -> service
    sequences = manifest.get("sequences", [])
    for seq in sequences:
        for canvas in seq.get("canvases", []):
            for image in canvas.get("images", []):
                resource = image.get("resource", {})
                service = resource.get("service", {})
                if isinstance(service, list):
                    service = service[0] if service else {}
                service_id = service.get("@id") or service.get("id", "")
                if service_id:
                    w = resource.get("width") or canvas.get("width", 0)
                    h = resource.get("height") or canvas.get("height", 0)
                    return service_id.rstrip("/"), int(w), int(h)

    # Try v3 structure: items -> items -> body -> service
    for canvas in manifest.get("items", []):
        for anno_page in canvas.get("items", []):
            for anno in anno_page.get("items", []):
                body = anno.get("body", {})
                services = body.get("service", [])
                if isinstance(services, dict):
                    services = [services]
                for svc in services:
                    svc_id = svc.get("@id") or svc.get("id", "")
                    if svc_id:
                        w = body.get("width") or canvas.get("width", 0)
                        h = body.get("height") or canvas.get("height", 0)
                        return svc_id.rstrip("/"), int(w), int(h)

    raise ValueError("Could not find an image service in the manifest")


def _make_filename(service_url: str, label: str, suffix: str = "") -> str:
    """Generate a filename from the service URL or label."""
    if label:
        name = re.sub(r"[^\w\s-]", "", label).strip()
        name = re.sub(r"\s+", "_", name)[:80]
    else:
        # Use last path segments of the URL
        parts = service_url.rstrip("/").split("/")
        name = "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        name = re.sub(r"[^\w-]", "_", name)

    return f"{name}{suffix}.jpg"
