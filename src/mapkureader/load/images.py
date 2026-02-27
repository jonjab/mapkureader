"""Map image loading and patchifying."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import Affine

from .geo import Bounds, get_patch_geo_bounds


@dataclass
class Patch:
    """A single patch extracted from a MapImage."""

    image: np.ndarray
    pixel_bounds: tuple[int, int, int, int]  # (x, y, width, height)
    parent_path: Path | None = None
    geo_bounds: Bounds | None = None
    row: int = 0
    col: int = 0


class PatchSet:
    """Collection of patches extracted from a parent MapImage."""

    def __init__(self, patches: list[Patch], parent: MapImage) -> None:
        self.patches = patches
        self.parent = parent

    def __len__(self) -> int:
        return len(self.patches)

    def __getitem__(self, idx: int) -> Patch:
        return self.patches[idx]

    def __iter__(self) -> Iterator[Patch]:
        return iter(self.patches)

    def to_dataframe(self):
        """Export patch metadata to a GeoDataFrame (if georeferenced) or DataFrame."""
        import pandas as pd

        records = []
        for i, p in enumerate(self.patches):
            rec = {
                "patch_idx": i,
                "row": p.row,
                "col": p.col,
                "pixel_x": p.pixel_bounds[0],
                "pixel_y": p.pixel_bounds[1],
                "pixel_w": p.pixel_bounds[2],
                "pixel_h": p.pixel_bounds[3],
            }
            if p.geo_bounds is not None:
                rec.update({
                    "geo_left": p.geo_bounds.left,
                    "geo_bottom": p.geo_bounds.bottom,
                    "geo_right": p.geo_bounds.right,
                    "geo_top": p.geo_bounds.top,
                })
            records.append(rec)

        df = pd.DataFrame(records)

        if self.parent.crs is not None and any(p.geo_bounds for p in self.patches):
            import geopandas as gpd
            from shapely.geometry import box

            geometries = []
            for p in self.patches:
                if p.geo_bounds:
                    b = p.geo_bounds
                    geometries.append(box(b.left, b.bottom, b.right, b.top))
                else:
                    geometries.append(None)
            df = gpd.GeoDataFrame(df, geometry=geometries, crs=str(self.parent.crs))

        return df


class MapImage:
    """A map image with optional georeferencing metadata.

    Supports loading from local files (PNG, JPG, TIFF, GeoTIFF).
    GeoTIFF files will have CRS and affine transform extracted automatically.
    """

    def __init__(
        self,
        data: np.ndarray,
        path: Path | None = None,
        crs: CRS | None = None,
        transform: Affine | None = None,
    ) -> None:
        self.data = data
        self.path = path
        self.crs = crs
        self.transform = transform

    @classmethod
    def from_file(cls, path: str | Path) -> MapImage:
        """Load a map image from a local file.

        For GeoTIFF files, CRS and affine transform are extracted.
        For other formats (PNG, JPG), only pixel data is loaded.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        suffix = path.suffix.lower()

        if suffix in (".tif", ".tiff"):
            return cls._load_geotiff(path)
        elif suffix in (".png", ".jpg", ".jpeg"):
            return cls._load_image(path)
        else:
            raise ValueError(f"Unsupported format: {suffix}")

    @classmethod
    def _load_geotiff(cls, path: Path) -> MapImage:
        with rasterio.open(path) as src:
            data = src.read()  # (bands, height, width)
            # Transpose to (height, width, bands) for consistency with PIL
            if data.ndim == 3:
                data = np.transpose(data, (1, 2, 0))
            crs = src.crs
            transform = src.transform
        return cls(data=data, path=path, crs=crs, transform=transform)

    @classmethod
    def _load_image(cls, path: Path) -> MapImage:
        img = Image.open(path)
        data = np.array(img)
        return cls(data=data, path=path)

    @property
    def height(self) -> int:
        return self.data.shape[0]

    @property
    def width(self) -> int:
        return self.data.shape[1]

    @property
    def shape(self) -> tuple[int, ...]:
        return self.data.shape

    @property
    def is_georeferenced(self) -> bool:
        return self.crs is not None and self.transform is not None

    @property
    def bounds(self) -> Bounds | None:
        """Geographic bounds of the full image, or None if not georeferenced."""
        if not self.is_georeferenced:
            return None
        return get_patch_geo_bounds(0, 0, self.width, self.height, self.transform)

    def patchify(
        self,
        patch_size: int = 256,
        overlap: int = 0,
        blank_threshold: float = 0.95,
        skip_blank: bool = True,
    ) -> PatchSet:
        """Split the image into a grid of patches.

        Args:
            patch_size: Size of each square patch in pixels.
            overlap: Overlap between adjacent patches in pixels.
            blank_threshold: Fraction of white/zero pixels above which a patch
                is considered blank. Only used if skip_blank is True.
            skip_blank: If True, patches that are mostly blank are excluded.

        Returns:
            A PatchSet containing the extracted patches.
        """
        stride = patch_size - overlap
        if stride <= 0:
            raise ValueError("overlap must be less than patch_size")

        patches: list[Patch] = []
        row_idx = 0

        for y in range(0, self.height, stride):
            col_idx = 0
            for x in range(0, self.width, stride):
                # Extract patch, allowing partial patches at edges
                patch_data = self.data[y : y + patch_size, x : x + patch_size]

                ph, pw = patch_data.shape[:2]
                if ph == 0 or pw == 0:
                    col_idx += 1
                    continue

                if skip_blank and self._is_blank(patch_data, blank_threshold):
                    col_idx += 1
                    continue

                geo_bounds = None
                if self.is_georeferenced:
                    geo_bounds = get_patch_geo_bounds(x, y, pw, ph, self.transform)

                patches.append(Patch(
                    image=patch_data,
                    pixel_bounds=(x, y, pw, ph),
                    parent_path=self.path,
                    geo_bounds=geo_bounds,
                    row=row_idx,
                    col=col_idx,
                ))
                col_idx += 1
            row_idx += 1

        return PatchSet(patches, parent=self)

    @staticmethod
    def _is_blank(patch: np.ndarray, threshold: float) -> bool:
        """Check if a patch is mostly blank (white or zero)."""
        if patch.dtype == np.uint8:
            white_pixels = np.all(patch >= 250, axis=-1) if patch.ndim == 3 else (patch >= 250)
            blank_ratio = np.mean(white_pixels)
        else:
            blank_ratio = np.mean(patch == 0)
        return blank_ratio > threshold
