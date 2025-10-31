import asyncio
import json
import os

from .schemas import JobState, JobType
from .store import job_store
from .file_store import file_store
from .settings import ENABLE_INSTANTSEG, TILE_OVERLAP, TILE_SIZE
from .instanseg_runner import (
    is_available as instanseg_available,
    segment_cells_on_tile,
    tissue_mask_on_tile,
)

try:
    import openslide  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openslide = None  # type: ignore
from PIL import Image


async def run_job(job_id: str) -> None:
    await job_store.update_job_state(job_id, JobState.RUNNING)
    job = await job_store.get_job(job_id)
    if job is None:
        return

    src_path = await file_store.get_disk_path(job.file_id)
    job_dir = file_store.get_job_dir(job.job_id)
    out_path = os.path.join(job_dir, "manifest.json")

    try:
        result: dict[str, object]

        def iter_tiles(img_w: int, img_h: int):
            step = TILE_SIZE - TILE_OVERLAP
            y = 0
            while y < img_h:
                x = 0
                h = min(TILE_SIZE, img_h - y)
                while x < img_w:
                    w = min(TILE_SIZE, img_w - x)
                    yield x, y, w, h
                    x += step
                y += step

        if job.job_type == JobType.SEGMENT_CELLS and ENABLE_INSTANTSEG and instanseg_available():
            tiles_info: list[dict[str, object]] = []
            artifacts: list[str] = []

            # Open via OpenSlide if possible, else PIL
            if openslide is not None:
                slide = openslide.OpenSlide(src_path)  # type: ignore[arg-type]
                try:
                    width, height = slide.dimensions  # type: ignore[attr-defined]
                    total = sum(1 for _ in iter_tiles(width, height))
                    processed = 0

                    for x, y, w, h in iter_tiles(width, height):
                        def _process_tile() -> str | None:
                            region = slide.read_region((x, y), 0, (w, h)).convert("RGB")  # type: ignore[attr-defined]
                            seg = segment_cells_on_tile(region)
                            mask = seg.get("mask")
                            if isinstance(mask, Image.Image):
                                mask_path = os.path.join(job_dir, f"mask_{x}_{y}.png")
                                mask.save(mask_path)
                                return mask_path
                            return None

                        mask_path = await asyncio.to_thread(_process_tile)
                        if mask_path:
                            artifacts.append(mask_path)
                        tiles_info.append({"x": x, "y": y})
                        processed += 1
                        await job_store.set_job_progress(job_id, processed / total, tiles_processed=processed, tiles_total=total)
                finally:
                    try:
                        slide.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            else:
                img = Image.open(src_path).convert("RGB")
                try:
                    width, height = img.size
                    total = sum(1 for _ in iter_tiles(width, height))
                    processed = 0

                    for x, y, w, h in iter_tiles(width, height):
                        def _process_tile() -> str | None:
                            tile = img.crop((x, y, x + w, y + h))
                            seg = segment_cells_on_tile(tile)
                            mask = seg.get("mask")
                            if isinstance(mask, Image.Image):
                                mask_path = os.path.join(job_dir, f"mask_{x}_{y}.png")
                                mask.save(mask_path)
                                return mask_path
                            return None

                        mask_path = await asyncio.to_thread(_process_tile)
                        if mask_path:
                            artifacts.append(mask_path)
                        tiles_info.append({"x": x, "y": y})
                        processed += 1
                        await job_store.set_job_progress(job_id, processed / total, tiles_processed=processed, tiles_total=total)
                finally:
                    try:
                        img.close()
                    except Exception:
                        pass

            def _build_preview(color: tuple[int, int, int, int]) -> str:
                max_preview = 2048
                scale = min(1.0, max_preview / max(width, height)) if max(width, height) > 0 else 1.0
                preview_w = max(1, int(width * scale))
                preview_h = max(1, int(height * scale))
                preview = Image.new("RGBA", (preview_w, preview_h), (0, 0, 0, 0))
                for x, y, w, h in iter_tiles(width, height):
                    mask_path = os.path.join(job_dir, f"mask_{x}_{y}.png")
                    if os.path.exists(mask_path):
                        with Image.open(mask_path).convert("L") as m:
                            resized = m.resize((int(w * scale), int(h * scale)))
                            overlay = Image.new("RGBA", resized.size, color)
                            preview.paste(overlay, (int(x * scale), int(y * scale)), mask=resized)
                preview_path_local = os.path.join(job_dir, "preview.png")
                preview.save(preview_path_local)
                return preview_path_local

            preview_path = await asyncio.to_thread(_build_preview, (255, 0, 0, 120))

            result = {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "source_file": src_path,
                "tiles": tiles_info,
                "artifacts": artifacts,
                "preview": preview_path,
                "tile_size": TILE_SIZE,
                "overlap": TILE_OVERLAP,
                "note": "InstanSeg path wired (stub per tile). Replace stub with real predictions.",
            }
        elif job.job_type == JobType.TISSUE_MASK:
            tiles_info: list[dict[str, object]] = []
            artifacts: list[str] = []

            if openslide is not None:
                slide = openslide.OpenSlide(src_path)  # type: ignore[arg-type]
                try:
                    width, height = slide.dimensions  # type: ignore[attr-defined]
                    total = sum(1 for _ in iter_tiles(width, height))
                    processed = 0

                    for x, y, w, h in iter_tiles(width, height):
                        def _process_tile() -> str | None:
                            region = slide.read_region((x, y), 0, (w, h)).convert("RGB")  # type: ignore[attr-defined]
                            seg = tissue_mask_on_tile(region)
                            mask = seg.get("mask")
                            if isinstance(mask, Image.Image):
                                mask_path = os.path.join(job_dir, f"mask_{x}_{y}.png")
                                mask.save(mask_path)
                                return mask_path
                            return None

                        mask_path = await asyncio.to_thread(_process_tile)
                        if mask_path:
                            artifacts.append(mask_path)
                        tiles_info.append({"x": x, "y": y})
                        processed += 1
                        await job_store.set_job_progress(job_id, processed / total, tiles_processed=processed, tiles_total=total)
                finally:
                    try:
                        slide.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            else:
                img = Image.open(src_path).convert("RGB")
                try:
                    width, height = img.size
                    total = sum(1 for _ in iter_tiles(width, height))
                    processed = 0

                    for x, y, w, h in iter_tiles(width, height):
                        def _process_tile() -> str | None:
                            tile = img.crop((x, y, x + w, y + h))
                            seg = tissue_mask_on_tile(tile)
                            mask = seg.get("mask")
                            if isinstance(mask, Image.Image):
                                mask_path = os.path.join(job_dir, f"mask_{x}_{y}.png")
                                mask.save(mask_path)
                                return mask_path
                            return None

                        mask_path = await asyncio.to_thread(_process_tile)
                        if mask_path:
                            artifacts.append(mask_path)
                        tiles_info.append({"x": x, "y": y})
                        processed += 1
                        await job_store.set_job_progress(job_id, processed / total, tiles_processed=processed, tiles_total=total)
                finally:
                    try:
                        img.close()
                    except Exception:
                        pass

            def _build_preview_green() -> str:
                max_preview = 2048
                scale = min(1.0, max_preview / max(width, height)) if max(width, height) > 0 else 1.0
                preview_w = max(1, int(width * scale))
                preview_h = max(1, int(height * scale))
                preview = Image.new("RGBA", (preview_w, preview_h), (0, 0, 0, 0))
                for x, y, w, h in iter_tiles(width, height):
                    mask_path = os.path.join(job_dir, f"mask_{x}_{y}.png")
                    if os.path.exists(mask_path):
                        with Image.open(mask_path).convert("L") as m:
                            resized = m.resize((int(w * scale), int(h * scale)))
                            overlay = Image.new("RGBA", resized.size, (0, 255, 0, 120))
                            preview.paste(overlay, (int(x * scale), int(y * scale)), mask=resized)
                preview_path_local = os.path.join(job_dir, "preview.png")
                preview.save(preview_path_local)
                return preview_path_local

            preview_path = await asyncio.to_thread(_build_preview_green)

            result = {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "source_file": src_path,
                "tiles": tiles_info,
                "artifacts": artifacts,
                "preview": preview_path,
                "tile_size": TILE_SIZE,
                "overlap": TILE_OVERLAP,
                "note": "Tissue mask generated via threshold per tile.",
            }
        else:
            # Simulated path
            total_tiles = 20 if job.job_type == JobType.SEGMENT_CELLS else 12
            for i in range(1, total_tiles + 1):
                await asyncio.sleep(0.15)
                await job_store.set_job_progress(job_id, i / total_tiles)

            result = {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "source_file": src_path,
                "tiles_processed": total_tiles,
                "note": "Simulated output. Set ENABLE_INSTANTSEG=True to run tiling path.",
            }

        with open(out_path, "w") as f:
            json.dump(result, f)
        await job_store.set_job_result_path(job_id, out_path)
        await job_store.update_job_state(job_id, JobState.SUCCEEDED)
    except Exception as e:
        fail_path = os.path.join(job_dir, "error.json")
        try:
            with open(fail_path, "w") as f:
                json.dump({"error": str(e)}, f)
            await job_store.set_job_result_path(job_id, fail_path)
        finally:
            await job_store.update_job_state(job_id, JobState.FAILED)



