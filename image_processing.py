"""Shared image preprocessing for image-to-3D heightmaps."""
import cv2
import numpy as np


def read_grayscale(path):
    """Load an image as grayscale uint8."""
    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(f"Imagem nao encontrada ou ilegivel: {path}")
    return gray


def _coerce_mask(mask, shape):
    if mask is None:
        return None

    mask = np.asarray(mask)
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

    if mask.shape != shape:
        mask = cv2.resize(
            mask.astype(np.uint8),
            (shape[1], shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    return mask > 0


def _crop_to_mask(gray, mask, margin_px=8):
    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        return gray, mask, None

    h, w = gray.shape
    margin = max(2, int(margin_px))
    x0 = max(0, int(xs.min()) - margin)
    x1 = min(w, int(xs.max()) + margin + 1)
    y0 = max(0, int(ys.min()) - margin)
    y1 = min(h, int(ys.max()) + margin + 1)

    return gray[y0:y1, x0:x1], mask[y0:y1, x0:x1], (x0, y0, x1 - x0, y1 - y0)


def _resize_pair(gray, mask, max_dim):
    if not max_dim or max(gray.shape) <= max_dim:
        return gray, mask, 1.0

    scale = max_dim / max(gray.shape)
    new_size = (
        max(2, int(round(gray.shape[1] * scale))),
        max(2, int(round(gray.shape[0] * scale))),
    )
    gray = cv2.resize(gray, new_size, interpolation=cv2.INTER_AREA)
    if mask is not None:
        mask = cv2.resize(
            mask.astype(np.uint8),
            new_size,
            interpolation=cv2.INTER_NEAREST,
        ) > 0
    return gray, mask, scale


def _normalize_gray(gray, mask=None, low_pct=2.0, high_pct=98.0):
    values = gray[mask] if mask is not None and np.any(mask) else gray.ravel()
    if values.size == 0:
        return gray

    low, high = np.percentile(values, [low_pct, high_pct])
    if high <= low + 1.0:
        return gray.copy()

    out = (gray.astype(np.float32) - float(low)) * (255.0 / (float(high) - float(low)))
    return np.clip(out, 0, 255).astype(np.uint8)


def _should_auto_invert(gray, mask):
    if mask is None or not np.any(mask) or not np.any(~mask):
        return False

    fg = gray[mask]
    bg = gray[~mask]
    if fg.size < 20 or bg.size < 20:
        return False

    return float(np.median(fg)) < float(np.median(bg))


def _smooth(gray, blur_radius):
    if blur_radius <= 0:
        return gray
    kernel = max(3, int(blur_radius) * 2 + 1)
    return cv2.GaussianBlur(gray, (kernel, kernel), 0)


def prepare_heightmap(
    gray,
    *,
    max_height_mm=10.0,
    max_dim=400,
    foreground_mask=None,
    invert=False,
    auto_invert=False,
    blur_radius=1,
    threshold=0,
    auto_crop=False,
    normalize=True,
    denoise=True,
    edge_boost=0.18,
):
    """
    Convert grayscale image data into a cleaner heightmap and mesh mask.

    Returns (heightmap, mask, info). The mask is always a boolean array the same
    shape as the returned heightmap.
    """
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    gray = np.asarray(gray, dtype=np.uint8).copy()

    mask = _coerce_mask(foreground_mask, gray.shape)
    info = {
        "input_size": (int(gray.shape[1]), int(gray.shape[0])),
        "output_size": None,
        "cropped": False,
        "crop_box": None,
        "scale": 1.0,
        "mask_applied": mask is not None,
        "auto_inverted": False,
        "enhanced": bool(normalize or denoise or edge_boost > 0),
    }

    if auto_crop and mask is not None and np.any(mask):
        margin = max(8, int(round(max(gray.shape) * 0.02)))
        gray, mask, crop_box = _crop_to_mask(gray, mask, margin)
        if crop_box is not None:
            info["cropped"] = True
            info["crop_box"] = tuple(int(v) for v in crop_box)

    gray, mask, scale = _resize_pair(gray, mask, max_dim)
    info["scale"] = float(scale)

    if denoise:
        gray = cv2.bilateralFilter(gray, d=5, sigmaColor=45, sigmaSpace=5)

    applied_invert = bool(invert)
    if not applied_invert and auto_invert and _should_auto_invert(gray, mask):
        applied_invert = True
        info["auto_inverted"] = True

    if applied_invert:
        gray = 255 - gray

    if normalize:
        gray = _normalize_gray(gray, mask)

    if edge_boost > 0:
        soft = cv2.GaussianBlur(gray, (0, 0), 1.2)
        gray = cv2.addWeighted(gray, 1.0 + edge_boost, soft, -edge_boost, 0)

    gray = _smooth(gray, blur_radius)

    if threshold > 0:
        threshold_mask = gray >= int(threshold)
        mask = threshold_mask if mask is None else (mask & threshold_mask)
        info["mask_applied"] = True

        if auto_crop and not info["cropped"] and np.any(mask):
            margin = max(8, int(round(max(gray.shape) * 0.02)))
            gray, mask, crop_box = _crop_to_mask(gray, mask, margin)
            if crop_box is not None:
                info["cropped"] = True
                info["crop_box"] = tuple(int(v) for v in crop_box)

    if mask is None:
        mask = np.ones_like(gray, dtype=bool)

    heightmap = (gray.astype(np.float64) / 255.0) * float(max_height_mm)
    heightmap = np.where(mask, heightmap, 0.0)

    info["output_size"] = (int(gray.shape[1]), int(gray.shape[0]))
    info["mask_pixels"] = int(np.count_nonzero(mask))
    info["height_min_mm"] = float(heightmap[mask].min()) if np.any(mask) else 0.0
    info["height_max_mm"] = float(heightmap[mask].max()) if np.any(mask) else 0.0
    return heightmap, mask, info


def prepare_heightmap_image(path, **kwargs):
    """Load an image file and run prepare_heightmap."""
    return prepare_heightmap(read_grayscale(path), **kwargs)
