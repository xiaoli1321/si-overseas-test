"""LRU-cached image encoding utilities."""

from __future__ import annotations

import base64
import functools
import io
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@functools.lru_cache(maxsize=None)
def encode_and_resize_image(
    image_path: Path,
    max_side: int = 2048,
    quality: int = 95,
) -> tuple[str, str]:
    """Load, auto-orient, resize, and encode image to base64 JPEG payload."""
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path.resolve()}")

    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_side, max_side))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return data, "image/jpeg"


def list_reference_files(reference_dir: Path) -> list[Path]:
    """List image files in a reference directory, sorted by name."""
    if not reference_dir.exists():
        return []
    return sorted(
        [
            path
            for path in reference_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda item: item.name.lower(),
    )
