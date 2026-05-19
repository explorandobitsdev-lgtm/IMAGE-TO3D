"""Reuso da lógica de heightmap do repo root (montado em /app no container)."""
import sys
from pathlib import Path

import cv2
import numpy as np

# No container, heightmap_utils.py e image_processing.py ficam em /app/ (vide Dockerfile).
# Em dev local, o repo root também é o WORKDIR — fallback para parents[4].
_APP_DIR = Path(__file__).resolve().parents[1]
for _candidate in (_APP_DIR, Path(__file__).resolve().parents[4]):
    if (_candidate / "heightmap_utils.py").exists():
        sys.path.insert(0, str(_candidate))
        break

from heightmap_utils import heightmap_to_mesh, save_mesh  # noqa: E402
from image_processing import prepare_heightmap  # noqa: E402


def _fetch(s3, bucket, image_ref) -> np.ndarray:
    if image_ref.startswith("http"):
        import requests

        r = requests.get(image_ref, timeout=20)
        r.raise_for_status()
        arr = np.frombuffer(r.content, dtype=np.uint8)
    else:
        key = image_ref[5:].split("/", 1)[1] if image_ref.startswith("s3://") else image_ref
        obj = s3.get_object(Bucket=bucket, Key=key)
        arr = np.frombuffer(obj["Body"].read(), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)


def run(input, workdir: Path, on_progress, s3, bucket):
    image_ref = input.get("image_url") or input.get("image_key")
    if not image_ref:
        raise ValueError("input.image_url obrigatório")

    on_progress(10, "lendo imagem")
    gray = _fetch(s3, bucket, image_ref)

    on_progress(30, "pré-processamento")
    heightmap, mask, info = prepare_heightmap(
        gray,
        max_height_mm=float(input.get("max_height_mm", 10.0)),
        max_dim=int(input.get("max_dim", 400)),
        auto_invert=bool(input.get("auto_invert", True)),
        auto_crop=bool(input.get("auto_crop", True)),
        blur_radius=int(input.get("blur", 1)),
        threshold=int(input.get("threshold", 0)),
    )

    on_progress(60, "gerando mesh")
    mesh = heightmap_to_mesh(
        heightmap,
        pixel_size_mm=float(input.get("pixel_size_mm", 0.3)),
        base_thickness_mm=float(input.get("base_thickness_mm", 2.0)),
        mask=mask,
    )

    on_progress(85, "exportando")
    base = workdir / "mesh"
    stl_path, obj_path = save_mesh(mesh, str(base))
    glb_path = workdir / "mesh.glb"
    mesh.export(str(glb_path))

    meta = {"vertices": int(len(mesh.vertices)), "faces": int(len(mesh.faces)), **info}
    return [
        ("mesh_obj", obj_path, meta),
        ("mesh_stl", stl_path, meta),
        ("mesh_glb", str(glb_path), meta),
    ]
