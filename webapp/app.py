"""Servidor Flask: upload de imagem → STL/OBJ (e SVG opcional)."""
import os
import sys
import uuid
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from heightmap_utils import heightmap_to_mesh, save_mesh  # noqa: E402
from image_processing import prepare_heightmap_image  # noqa: E402
from palmilha import analyze_footprint, generate_palmilha  # noqa: E402
from svg_helper import maybe_vectorize, potrace_available  # noqa: E402

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/outputs"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_MB = 20

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


def _save_upload(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Nenhum arquivo enviado.")
    name = secure_filename(file_storage.filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Extensão não suportada: {ext}")
    job_id = uuid.uuid4().hex[:10]
    dest = UPLOAD_DIR / f"{job_id}{ext}"
    file_storage.save(dest)
    return job_id, dest


def _checked(name, default=False):
    if name not in request.form:
        return default
    return request.form.get(name) == "on"


@app.route("/")
def index():
    return render_template("index.html", potrace=potrace_available())


@app.route("/api/convert", methods=["POST"])
def api_convert():
    try:
        mode = request.form.get("mode", "heightmap")
        auto_svg = request.form.get("auto_svg", "auto")  # auto | on | off

        job_id, src = _save_upload(request.files.get("image"))
        out_base = OUTPUT_DIR / job_id

        force = {"on": True, "off": False}.get(auto_svg, None)
        svg_path, clean_mask, vectorized = maybe_vectorize(str(src), force=force)
        if svg_path:
            persistent_svg = OUTPUT_DIR / f"{job_id}.svg"
            try:
                import shutil

                shutil.copy(svg_path, persistent_svg)
            except Exception:
                persistent_svg = None
        else:
            persistent_svg = None

        result = {
            "job_id": job_id,
            "mode": mode,
            "vectorized": bool(vectorized),
            "files": {},
        }

        if mode == "heightmap":
            max_height = float(request.form.get("max_height", 10.0))
            pixel_size = float(request.form.get("pixel_size", 0.3))
            base_thickness = float(request.form.get("base_thickness", 2.0))
            invert = _checked("invert")
            auto_invert = _checked("auto_invert")
            auto_crop = _checked("auto_crop")
            enhance = _checked("enhance")
            blur = int(request.form.get("blur", 1))
            threshold = int(request.form.get("threshold", 0))
            max_dim = int(request.form.get("max_dim", 400))

            mask_for_mesh = clean_mask if (vectorized or force is True) else None
            heightmap, mesh_mask, prep = prepare_heightmap_image(
                str(src),
                max_height_mm=max_height,
                max_dim=max_dim,
                foreground_mask=mask_for_mesh,
                invert=invert,
                auto_invert=auto_invert,
                blur_radius=blur,
                threshold=threshold,
                auto_crop=auto_crop,
                normalize=enhance,
                denoise=enhance,
                edge_boost=0.18 if enhance else 0.0,
            )
            mesh = heightmap_to_mesh(
                heightmap,
                pixel_size_mm=pixel_size,
                base_thickness_mm=base_thickness,
                mask=mesh_mask,
            )
            stl, obj = save_mesh(mesh, str(out_base))
            result["files"]["stl"] = Path(stl).name
            result["files"]["obj"] = Path(obj).name
            result["preprocess"] = {
                "input_size": f"{prep['input_size'][0]}x{prep['input_size'][1]}",
                "output_size": f"{prep['output_size'][0]}x{prep['output_size'][1]}",
                "mask_applied": bool(prep["mask_applied"]),
                "cropped": bool(prep["cropped"]),
                "auto_inverted": bool(prep["auto_inverted"]),
                "enhanced": bool(prep["enhanced"]),
            }
            result["stats"] = {
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces),
            }

        elif mode == "palmilha":
            num = int(request.form.get("num", 0))
            if not (28 <= num <= 50):
                raise ValueError("Numeração deve estar entre 28 e 50.")
            lado_in = request.form.get("lado", "auto")
            info = analyze_footprint(str(src))
            lado = info["lado"] if lado_in == "auto" else lado_in
            mesh, params = generate_palmilha(
                num_eur=num, tipo_pisada=info["tipo"], lado=lado
            )
            stl, obj = save_mesh(mesh, str(out_base))
            result["files"]["stl"] = Path(stl).name
            result["files"]["obj"] = Path(obj).name
            result["analise"] = {
                "tipo": info["tipo"],
                "arch_index": round(info["arch_index"], 3),
                "lado": lado,
            }
            result["palmilha"] = {
                k: round(v, 2) if isinstance(v, (int, float)) else v
                for k, v in params.items()
            }
            result["stats"] = {
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces),
            }
        else:
            raise ValueError(f"Modo inválido: {mode}")

        if persistent_svg:
            result["files"]["svg"] = Path(persistent_svg).name

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": f"Arquivo não encontrado: {e}"}), 400
    except Exception as e:
        app.logger.exception("Erro processando upload")
        return jsonify({"error": f"Erro interno: {e}"}), 500


@app.route("/download/<path:filename>")
def download(filename):
    safe = secure_filename(filename)
    full = OUTPUT_DIR / safe
    if not full.exists():
        abort(404)
    return send_from_directory(str(OUTPUT_DIR), safe, as_attachment=True)


@app.route("/health")
def health():
    return {"ok": True, "potrace": potrace_available()}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
