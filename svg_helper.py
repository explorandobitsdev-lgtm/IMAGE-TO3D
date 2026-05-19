"""
Conversão automática de imagem → SVG → bitmap limpo, usando potrace.
Útil quando a imagem é "vetor-friendly" (poucas cores, linhas, silhuetas):
o potrace suaviza as bordas, e depois rasterizamos de volta para alimentar
a geração do 3D com contornos limpos.
"""
import os
import shutil
import subprocess
import tempfile

import cv2
import numpy as np


def potrace_available():
    return shutil.which("potrace") is not None


def is_vector_friendly(gray, color_threshold=24):
    """
    Heurística simples: imagens com poucas variações tonais (logos, silhuetas,
    desenhos, pisadas com tinta) se beneficiam de vetorização.
    """
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).ravel()
    nonzero = np.count_nonzero(hist > (gray.size * 0.005))
    return nonzero <= color_threshold


def vectorize_to_clean_mask(image_path, out_svg_path=None, upscale=2):
    """
    Recebe um caminho de imagem, gera SVG suavizado via potrace e devolve:
      - svg_path: caminho do SVG gerado (ou None se falhou)
      - clean_mask: array 2D uint8 (0/255) com bordas limpas, mesmo tamanho da
        imagem original (depois redimensionado).
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(image_path)

    blur = cv2.GaussianBlur(img, (5, 5), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if not potrace_available():
        return None, binary

    H, W = binary.shape
    with tempfile.TemporaryDirectory() as tmp:
        pbm_path = os.path.join(tmp, "in.pbm")
        svg_path = out_svg_path or os.path.join(tmp, "out.svg")

        with open(pbm_path, "wb") as f:
            f.write(f"P4\n{W} {H}\n".encode())
            packed = np.packbits(binary // 255, axis=1)
            f.write(packed.tobytes())

        try:
            subprocess.run(
                [
                    "potrace",
                    pbm_path,
                    "-s",
                    "-o",
                    svg_path,
                    "--turdsize",
                    "8",
                    "--alphamax",
                    "1.0",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None, binary

        try:
            import cairosvg

            png_path = os.path.join(tmp, "out.png")
            cairosvg.svg2png(
                url=svg_path,
                write_to=png_path,
                output_width=W * upscale,
                output_height=H * upscale,
            )
            rendered = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
            if rendered is None:
                return svg_path, binary
            rendered = cv2.resize(rendered, (W, H), interpolation=cv2.INTER_AREA)
            _, clean = cv2.threshold(rendered, 127, 255, cv2.THRESH_BINARY_INV)
        except Exception:
            return svg_path, binary

        if out_svg_path is None:
            persistent = tempfile.NamedTemporaryFile(
                delete=False, suffix=".svg"
            ).name
            shutil.copy(svg_path, persistent)
            svg_path = persistent

        return svg_path, clean


def maybe_vectorize(image_path, force=None):
    """
    Decide automaticamente se vale a pena vetorizar.
    force: True/False para forçar, None para decidir pela heurística.
    Retorna (svg_path_ou_None, mask_limpa, foi_vetorizado_bool).
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(image_path)

    should = force if force is not None else is_vector_friendly(img)
    if not should or not potrace_available():
        _, binary = cv2.threshold(
            cv2.GaussianBlur(img, (5, 5), 0),
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
        return None, binary, False

    svg_path, clean = vectorize_to_clean_mask(image_path)
    return svg_path, clean, svg_path is not None
