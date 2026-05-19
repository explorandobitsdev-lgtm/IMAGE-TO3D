"""Pipeline da palmilha — reusa palmilha.py do repo root (em /app no container)."""
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
for _candidate in (_APP_DIR, Path(__file__).resolve().parents[4]):
    if (_candidate / "palmilha.py").exists():
        sys.path.insert(0, str(_candidate))
        break

from palmilha import analyze_footprint, generate_palmilha  # noqa: E402
from heightmap_utils import save_mesh  # noqa: E402


def _fetch_to_file(s3, bucket, ref, dest: Path):
    if ref.startswith("http"):
        import requests

        r = requests.get(ref, timeout=20)
        r.raise_for_status()
        dest.write_bytes(r.content)
    else:
        key = ref[5:].split("/", 1)[1] if ref.startswith("s3://") else ref
        obj = s3.get_object(Bucket=bucket, Key=key)
        dest.write_bytes(obj["Body"].read())
    return dest


def run(input, workdir: Path, on_progress, s3, bucket):
    image_ref = input.get("image_url") or input.get("image_key")
    if not image_ref:
        raise ValueError("input.image_url obrigatório")
    num = int(input.get("num", 41))
    lado_in = input.get("lado", "auto")

    on_progress(10, "baixando imagem")
    local = _fetch_to_file(s3, bucket, image_ref, workdir / "input.png")

    on_progress(35, "analisando pisada")
    info = analyze_footprint(str(local))
    lado = info["lado"] if lado_in == "auto" else lado_in

    on_progress(60, "gerando palmilha 3D")
    mesh, params = generate_palmilha(
        num_eur=num, tipo_pisada=info["tipo"], lado=lado,
        pixel_size_mm=float(input.get("resolution_mm", 1.5)),
    )

    on_progress(85, "exportando")
    base = workdir / "palmilha"
    stl_path, obj_path = save_mesh(mesh, str(base))
    glb_path = workdir / "palmilha.glb"
    mesh.export(str(glb_path))

    meta = {
        "analise": {"tipo": info["tipo"], "arch_index": info["arch_index"], "lado": lado},
        "palmilha": params,
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }
    return [
        ("mesh_obj", obj_path, meta),
        ("mesh_stl", stl_path, meta),
        ("mesh_glb", str(glb_path), meta),
    ]
