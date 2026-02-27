"""Visualization helpers for map images and patches."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from mapkureader.load.images import PatchSet


def show_patches(
    patch_set: PatchSet,
    max_patches: int = 25,
    cols: int = 5,
    figsize: tuple[float, float] | None = None,
) -> None:
    """Display patches in a matplotlib grid.

    Args:
        patch_set: PatchSet to visualize.
        max_patches: Maximum number of patches to display.
        cols: Number of columns in the grid.
        figsize: Figure size (width, height) in inches.
    """
    n = min(len(patch_set), max_patches)
    if n == 0:
        print("No patches to display.")
        return

    rows = (n + cols - 1) // cols
    if figsize is None:
        figsize = (cols * 3, rows * 3)

    fig, axes = plt.subplots(rows, cols, figsize=figsize)
    if rows == 1 and cols == 1:
        axes = np.array([axes])
    axes = np.atleast_2d(axes)

    for i in range(rows * cols):
        ax = axes[i // cols, i % cols]
        if i < n:
            patch = patch_set[i]
            ax.imshow(patch.image)
            ax.set_title(f"r{patch.row},c{patch.col}", fontsize=8)
        ax.axis("off")

    plt.tight_layout()
    plt.show()
