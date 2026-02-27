"""Georeferencing utilities for coordinate transforms between pixel and geographic space."""

from __future__ import annotations

from typing import NamedTuple

import pyproj
from rasterio.transform import Affine


class Bounds(NamedTuple):
    """Geographic or pixel bounding box (left, bottom, right, top)."""

    left: float
    bottom: float
    right: float
    top: float


def pixel_to_geo(x: float, y: float, transform: Affine) -> tuple[float, float]:
    """Convert pixel coordinates to geographic coordinates using an affine transform.

    Args:
        x: Pixel column.
        y: Pixel row.
        transform: Rasterio affine transform from the GeoTIFF.

    Returns:
        (longitude, latitude) or (easting, northing) depending on CRS.
    """
    geo_x, geo_y = transform * (x, y)
    return geo_x, geo_y


def geo_to_pixel(geo_x: float, geo_y: float, transform: Affine) -> tuple[float, float]:
    """Convert geographic coordinates to pixel coordinates.

    Args:
        geo_x: Geographic x (longitude or easting).
        geo_y: Geographic y (latitude or northing).
        transform: Rasterio affine transform from the GeoTIFF.

    Returns:
        (pixel_x, pixel_y) as floats.
    """
    inv_transform = ~transform
    px, py = inv_transform * (geo_x, geo_y)
    return px, py


def get_patch_geo_bounds(
    pixel_x: int,
    pixel_y: int,
    patch_w: int,
    patch_h: int,
    transform: Affine,
) -> Bounds:
    """Compute geographic bounding box for a patch given its pixel location and size.

    Args:
        pixel_x: Left edge of patch in pixels.
        pixel_y: Top edge of patch in pixels.
        patch_w: Patch width in pixels.
        patch_h: Patch height in pixels.
        transform: Rasterio affine transform.

    Returns:
        Bounds(left, bottom, right, top) in geographic coordinates.
    """
    left, top = pixel_to_geo(pixel_x, pixel_y, transform)
    right, bottom = pixel_to_geo(pixel_x + patch_w, pixel_y + patch_h, transform)
    return Bounds(left=left, bottom=bottom, right=right, top=top)


def reproject_bounds(
    bounds: Bounds,
    src_crs: pyproj.CRS,
    dst_crs: pyproj.CRS,
) -> Bounds:
    """Reproject a bounding box from one CRS to another.

    Args:
        bounds: Input bounding box.
        src_crs: Source coordinate reference system.
        dst_crs: Target coordinate reference system.

    Returns:
        Reprojected Bounds.
    """
    transformer = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    left, bottom = transformer.transform(bounds.left, bounds.bottom)
    right, top = transformer.transform(bounds.right, bounds.top)
    return Bounds(left=left, bottom=bottom, right=right, top=top)
