"""One-off Phase 0 helper: scan sample_data/raw and print format/size/resolution/EXIF stats.

Not part of the pipeline; run manually to regenerate the numbers in docs/dataset-notes.md.
"""
import json
import statistics
from pathlib import Path

from PIL import Image

RAW_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "raw"


def main() -> None:
    rows = []
    errors = []
    for path in sorted(RAW_DIR.iterdir()):
        if path.name == ".gitkeep" or not path.is_file():
            continue
        try:
            with Image.open(path) as im:
                im.load()
                exif = im.getexif()
                orientation = exif.get(0x0112) if exif else None
                rows.append(
                    {
                        "name": path.name,
                        "format": im.format,
                        "mode": im.mode,
                        "width": im.width,
                        "height": im.height,
                        "size_bytes": path.stat().st_size,
                        "has_exif": bool(exif),
                        "exif_orientation": orientation,
                    }
                )
        except Exception as e:  # noqa: BLE001 - recon script, not production code
            errors.append({"name": path.name, "error": str(e)})

    widths = [r["width"] for r in rows]
    heights = [r["height"] for r in rows]
    sizes = [r["size_bytes"] for r in rows]
    formats = {}
    modes = {}
    orientations = {}
    for r in rows:
        formats[r["format"]] = formats.get(r["format"], 0) + 1
        modes[r["mode"]] = modes.get(r["mode"], 0) + 1
        key = r["exif_orientation"] if r["exif_orientation"] is not None else ("no_exif" if not r["has_exif"] else "exif_no_orientation_tag")
        orientations[key] = orientations.get(key, 0) + 1

    summary = {
        "total_images": len(rows),
        "errors": errors,
        "format_breakdown": formats,
        "color_mode_breakdown": modes,
        "exif_orientation_breakdown": orientations,
        "width": {"min": min(widths), "max": max(widths), "median": statistics.median(widths)},
        "height": {"min": min(heights), "max": max(heights), "median": statistics.median(heights)},
        "size_bytes": {"min": min(sizes), "max": max(sizes), "median": statistics.median(sizes)},
    }
    print(json.dumps(summary, indent=2))

    out_path = Path(__file__).resolve().parent.parent / "sample_data" / "outputs" / "dataset_stats.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(f"\nFull per-file rows written to {out_path}")


if __name__ == "__main__":
    main()
