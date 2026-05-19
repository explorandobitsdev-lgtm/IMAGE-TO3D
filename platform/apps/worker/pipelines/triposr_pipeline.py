"""
Image-to-3D usando TripoSR (Stability AI / VAST-AI, MIT).
Repo: https://github.com/VAST-AI-Research/TripoSR
Modelo HF: stabilityai/TripoSR (~5 GB)

Input esperado:
  {"image_url": "...", "remove_bg": true, "mc_resolution": 256, "foreground_ratio": 0.85}
"""
import os
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image

_model = None
_device = os.environ.get("WORKER_DEVICE", "cuda")


def _load_model():
    global _model
    if _model is not None:
        return _model

    import torch
    from tsr.system import TSR  # noqa: F401  (do pacote TripoSR)

    print("[triposr] carregando modelo stabilityai/TripoSR...")
    _model = TSR.from_pretrained(
        "stabilityai/TripoSR",
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    _model.renderer.set_chunk_size(8192)
    _model.to(_device)
    print(f"[triposr] modelo em {_device}")
    return _model


def _fetch_image(url_or_key: str, s3, bucket) -> Image.Image:
    """Aceita http(s) URL, s3://key ou chave relativa do bucket."""
    if url_or_key.startswith("http://") or url_or_key.startswith("https://"):
        # se for endpoint MinIO no compose, o host é "minio:9000" — tenta direto
        r = requests.get(url_or_key, timeout=20)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    if url_or_key.startswith("s3://"):
        key = url_or_key[5:].split("/", 1)[1]
    else:
        key = url_or_key
    obj = s3.get_object(Bucket=bucket, Key=key)
    return Image.open(BytesIO(obj["Body"].read())).convert("RGB")


def _remove_bg(img: Image.Image) -> Image.Image:
    try:
        from rembg import remove

        out = remove(img)
        if out.mode != "RGBA":
            return img
        bg = Image.new("RGB", out.size, (255, 255, 255))
        bg.paste(out, mask=out.split()[3])
        return bg
    except Exception as e:
        print(f"[triposr] rembg falhou: {e} — seguindo sem bg removal")
        return img


def run(input: dict, workdir: Path, on_progress, s3, bucket):
    image_ref = input.get("image_url") or input.get("image_key")
    if not image_ref:
        raise ValueError("input.image_url ou image_key obrigatório")

    on_progress(5, "carregando imagem")
    img = _fetch_image(image_ref, s3, bucket)

    if input.get("remove_bg", True):
        on_progress(15, "removendo fundo")
        img = _remove_bg(img)

    on_progress(25, "carregando modelo TripoSR")
    model = _load_model()

    import torch

    on_progress(40, "inferência multi-view + NeRF")
    with torch.no_grad():
        scene_codes = model([img], device=_device)
        mesh = model.extract_mesh(
            scene_codes,
            has_vertex_color=True,
            resolution=int(input.get("mc_resolution", 256)),
        )[0]

    on_progress(80, "exportando OBJ / GLB / STL")
    obj_path = workdir / "mesh.obj"
    glb_path = workdir / "mesh.glb"
    stl_path = workdir / "mesh.stl"
    mesh.export(str(obj_path))
    mesh.export(str(glb_path))
    mesh.export(str(stl_path))

    preview_path = workdir / "preview.png"
    try:
        from PIL import ImageDraw

        thumb = Image.new("RGB", (512, 512), (20, 22, 28))
        ImageDraw.Draw(thumb).text((20, 240), "preview", fill=(180, 200, 255))
        thumb.save(preview_path)
    except Exception:
        preview_path = None

    meta = {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "model": "triposr",
        "ts": time.time(),
    }
    out = [
        ("mesh_obj", str(obj_path), meta),
        ("mesh_glb", str(glb_path), meta),
        ("mesh_stl", str(stl_path), meta),
    ]
    if preview_path is not None:
        out.append(("preview", str(preview_path), {}))
    return out
