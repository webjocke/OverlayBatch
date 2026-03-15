"""OverlayBatch.

Watch a folder for incoming images, resize/crop them to a fixed output size,
apply a transparent overlay, and write PNG files to an output folder.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps, UnidentifiedImageError

DEFAULT_OUTPUT_WIDTH = 800
DEFAULT_OUTPUT_HEIGHT = 600
DEFAULT_WATCH_FOLDER = "input"
DEFAULT_OUTPUT_FOLDER = "output"
DEFAULT_OVERLAY_IMAGE = "overlay.png"
SUPPORTED_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1 compatibility
    RESAMPLE = Image.LANCZOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Watch a folder for images, resize them to a fixed canvas, "
            "apply a transparent overlay, and save them as PNG files."
        )
    )
    parser.add_argument(
        "--watch-folder",
        default=DEFAULT_WATCH_FOLDER,
        help=f"Folder to monitor for incoming images. Default: {DEFAULT_WATCH_FOLDER}",
    )
    parser.add_argument(
        "--output-folder",
        default=DEFAULT_OUTPUT_FOLDER,
        help=f"Folder where processed images are written. Default: {DEFAULT_OUTPUT_FOLDER}",
    )
    parser.add_argument(
        "--overlay-image",
        default=DEFAULT_OVERLAY_IMAGE,
        help=f"Transparent PNG overlay to apply. Default: {DEFAULT_OVERLAY_IMAGE}",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_OUTPUT_WIDTH,
        help=f"Output image width in pixels. Default: {DEFAULT_OUTPUT_WIDTH}",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_OUTPUT_HEIGHT,
        help=f"Output image height in pixels. Default: {DEFAULT_OUTPUT_HEIGHT}",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds to wait between folder scans. Default: 1.0",
    )
    parser.add_argument(
        "--keep-originals",
        action="store_true",
        help="Keep original files in the watch folder after processing.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process the current queue once and exit.",
    )
    return parser.parse_args()


def log(message: str) -> None:
    print(f"{message}")


def ensure_directories(watch_folder: Path, output_folder: Path) -> None:
    watch_folder.mkdir(parents=True, exist_ok=True)
    output_folder.mkdir(parents=True, exist_ok=True)


def validate_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("Output width and height must both be positive integers.")


def list_pending_images(watch_folder: Path) -> Iterable[Path]:
    for path in sorted(watch_folder.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        yield path


def load_overlay(overlay_path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(overlay_path) as image:
        overlay = image.convert("RGBA")
    if overlay.size != size:
        overlay = overlay.resize(size, RESAMPLE)
    return overlay


def compose_image(source_path: Path, overlay: Image.Image, size: tuple[int, int]) -> Image.Image:
    with Image.open(source_path) as image:
        background = ImageOps.fit(
            image.convert("RGBA"),
            size,
            method=RESAMPLE,
            centering=(0.5, 0.5),
        )

    background.alpha_composite(overlay)
    return background


def process_image(
    source_path: Path,
    output_folder: Path,
    overlay: Image.Image,
    size: tuple[int, int],
    keep_originals: bool,
) -> None:
    output_path = output_folder / f"{source_path.stem}.png"
    result = compose_image(source_path, overlay, size)
    result.save(output_path, format="PNG")

    if not keep_originals:
        source_path.unlink()

    log(f"Processed {source_path} -> {output_path}")


def run(args: argparse.Namespace) -> None:
    watch_folder = Path(args.watch_folder)
    output_folder = Path(args.output_folder)
    overlay_path = Path(args.overlay_image)
    size = (args.width, args.height)

    validate_size(*size)
    ensure_directories(watch_folder, output_folder)

    if not overlay_path.is_file():
        raise FileNotFoundError(f"Overlay image not found: {overlay_path}")

    overlay = load_overlay(overlay_path, size)
    mode = "single batch mode" if args.once else f"watch mode with a {args.poll_interval:g}s scan interval"
    originals = "kept" if args.keep_originals else "removed after processing"
    log(
        "OverlayBatch is ready. "
        f"Watching /{watch_folder} for new and saving finished PNGs to /{output_folder}. "
    )
    log(
        f"Size: {size[0]}x{size[1]} px"
    )
    log(
        f"Overlay file: {overlay_path}"
    )

    while True:
        pending_files = list(list_pending_images(watch_folder))
        for source_path in pending_files:
            try:
                process_image(
                    source_path=source_path,
                    output_folder=output_folder,
                    overlay=overlay,
                    size=size,
                    keep_originals=args.keep_originals,
                )
            except UnidentifiedImageError:
                log(f"Skipped unsupported or corrupted image file: {source_path.name}")
            except Exception as exc:
                log(f"Failed to process {source_path.name}: {exc}")

        if args.once:
            break

        time.sleep(args.poll_interval)


def main() -> int:
    args = parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        log("Stopping watcher.")
        return 0
    except Exception as exc:
        log(f"Fatal error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
