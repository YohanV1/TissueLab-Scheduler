from __future__ import annotations

import importlib
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw


def is_available() -> bool:
    return importlib.util.find_spec("instanseg") is not None


_model_singleton: Optional[object] = None


def _get_device() -> str:
    try:
        import torch  # type: ignore
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():  # type: ignore[attr-defined]
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _load_instanseg_model() -> Optional[object]:
    global _model_singleton
    if _model_singleton is not None:
        return _model_singleton
    try:
        import instanseg  # type: ignore
        InstanSegClass = None
        # Prefer top-level InstanSeg
        if hasattr(instanseg, "InstanSeg"):
            InstanSegClass = getattr(instanseg, "InstanSeg")
        elif hasattr(instanseg, "inference_class") and hasattr(instanseg.inference_class, "InstanSeg"):  # type: ignore[attr-defined]
            InstanSegClass = getattr(instanseg.inference_class, "InstanSeg")  # type: ignore[attr-defined]
        if InstanSegClass is None:
            return None

        device = _get_device()
        try:
            # Some packages accept device argument; if not, fall back to default ctor
            _model_singleton = InstanSegClass(device=device)
        except Exception:
            _model_singleton = InstanSegClass()
        return _model_singleton
    except Exception:
        return None


def _to_mask_image(output: Any, width: int, height: int) -> Optional[Image.Image]:
    """Best-effort conversion of arbitrary model output to a grayscale PIL mask."""
    try:
        import numpy as np  # type: ignore
        # If output already looks like a mask array
        if isinstance(output, Image.Image):
            return output.convert("L")
        if isinstance(output, dict):
            for key in ("mask", "seg", "segmentation"):
                if key in output:
                    v = output[key]
                    if isinstance(v, Image.Image):
                        return v.convert("L")
                    try:
                        arr = np.array(v)
                        return Image.fromarray(arr.astype("uint8"), mode="L")
                    except Exception:
                        continue
        # Assume ndarray-like
        arr = np.array(output)
        if arr.ndim == 3:
            # If probabilities or multi-channel, take argmax or first channel
            if arr.shape[2] > 1:
                arr = arr.argmax(axis=2)
            else:
                arr = arr[:, :, 0]
        arr = (arr > 0).astype("uint8") * 255
        return Image.fromarray(arr, mode="L")
    except Exception:
        return None


def segment_cells_on_tile(tile_image: Image.Image) -> Dict[str, Any]:
    """Return a dict with at least a grayscale mask Image under key 'mask'.

    Tries real InstanSeg if available; otherwise falls back to a simple threshold
    or a drawn mask so downstream code continues to work.
    """
    width, height = tile_image.size
    # Try real model
    model = _load_instanseg_model() if is_available() else None
    if model is not None:
        try:
            import numpy as np  # type: ignore
            img_np = np.array(tile_image.convert("RGB"))

            # InstanSeg exposes eval_small_image / eval_medium_image; prefer the
            # small-image path for per-tile inference.
            labels = model.eval_small_image(  # type: ignore[attr-defined]
                img_np,
                return_image_tensor=False,
                target="cells",
            )

            import torch  # type: ignore

            if isinstance(labels, torch.Tensor):
                labels_np = labels.cpu().numpy()
            else:
                labels_np = np.array(labels)
            if labels_np.ndim == 4:
                labels_np = labels_np[0]
            if labels_np.ndim == 3:
                labels_np = labels_np[0]

            binary = (labels_np > 0).astype("uint8") * 255
            mask = Image.fromarray(binary, mode="L")
            return {"mask": mask}
        except Exception:
            pass

    # Fallback: threshold luminance
    try:
        import numpy as np  # type: ignore
        gray = tile_image.convert("L")
        arr = np.array(gray)
        thresh = int(arr.mean())
        mask_arr = (arr > thresh).astype("uint8") * 255
        mask = Image.fromarray(mask_arr, mode="L")
        return {"mask": mask}
    except Exception:
        # Last-resort: draw concentric blobs
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        r = min(width, height)
        for k in range(5, 0, -1):
            rad = int(r * k / 10)
            bbox = (width // 2 - rad, height // 2 - rad, width // 2 + rad, height // 2 + rad)
            draw.ellipse(bbox, fill=255 if k % 2 == 1 else 0)
        return {"mask": mask}


def tissue_mask_on_tile(tile_image: Image.Image) -> Dict[str, Any]:
    """Make a binary tissue mask for a tile.

    Uses Otsu threshold from scikit-image if available; otherwise mean threshold.
    Returns a dict with key 'mask' (PIL.Image in L mode).
    """
    gray = tile_image.convert("L")
    try:
        import numpy as np  # type: ignore
        from skimage.filters import threshold_otsu  # type: ignore

        arr = np.array(gray)
        t = threshold_otsu(arr)
        mask_arr = (arr > t).astype("uint8") * 255
        mask = Image.fromarray(mask_arr, mode="L")
        return {"mask": mask}
    except Exception:
        # Fallback to simple mean threshold
        import numpy as np  # type: ignore

        arr = np.array(gray)
        t = int(arr.mean())
        mask_arr = (arr > t).astype("uint8") * 255
        mask = Image.fromarray(mask_arr, mode="L")
        return {"mask": mask}


