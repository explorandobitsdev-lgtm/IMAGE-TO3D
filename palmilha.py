"""Análise de pisada e geração de palmilha corretiva 3D."""
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

from heightmap_utils import heightmap_to_mesh


def analyze_footprint(image_path):
    """
    Analisa uma foto de pisada (impressão da planta) e classifica o tipo de pisada
    usando o índice do arco de Cavanagh.

    Retorna dict com:
      - arch_index: float (Cavanagh)
      - tipo: 'cavo' | 'normal' | 'pronado'
      - lado: 'direito' | 'esquerdo' (estimado pela posição do arco)
      - bbox: (x, y, w, h) da pisada
    """
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Não consegui abrir a imagem: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Nenhuma impressão de pisada detectada na imagem.")

    main = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(main)

    foot_mask = np.zeros_like(binary)
    cv2.drawContours(foot_mask, [main], -1, 255, thickness=cv2.FILLED)
    foot_mask = cv2.bitwise_and(foot_mask, binary)

    if h > w:
        toes_top = True
    else:
        toes_top = True

    toe_exclusion = int(h * 0.16)
    foot_y0 = y + toe_exclusion
    foot_h = h - toe_exclusion
    third = foot_h // 3
    if third < 2:
        raise ValueError("Imagem muito pequena para análise confiável.")

    region_ante = foot_mask[foot_y0 : foot_y0 + third, x : x + w]
    region_meso = foot_mask[foot_y0 + third : foot_y0 + 2 * third, x : x + w]
    region_retro = foot_mask[foot_y0 + 2 * third : foot_y0 + 3 * third, x : x + w]

    area_a = int(np.sum(region_ante > 0))
    area_b = int(np.sum(region_meso > 0))
    area_c = int(np.sum(region_retro > 0))
    total = area_a + area_b + area_c

    if total == 0:
        raise ValueError("Áreas detectadas vazias — verifique a imagem.")

    arch_index = area_b / total

    if arch_index < 0.21:
        tipo = "cavo"
    elif arch_index < 0.26:
        tipo = "normal"
    else:
        tipo = "pronado"

    meso_col_sums = np.sum(region_meso > 0, axis=0)
    if len(meso_col_sums) > 0 and meso_col_sums.sum() > 0:
        cx = np.argmax(meso_col_sums)
        if cx < w / 2:
            lado = "esquerdo"
        else:
            lado = "direito"
    else:
        lado = "direito"

    return {
        "arch_index": float(arch_index),
        "tipo": tipo,
        "lado": lado,
        "bbox": (int(x), int(y), int(w), int(h)),
        "areas": {"antepe": area_a, "mesope": area_b, "retrope": area_c},
    }


def _foot_outline(num_eur, lado="direito", pixel_size_mm=1.5):
    """
    Gera a máscara 2D da silhueta da palmilha para a numeração dada.
    Numeração europeia → comprimento ≈ (n - 2) * 6.667 mm + 50 mm aprox.
    """
    length_mm = (num_eur - 2) * 6.667 + 50.0
    width_mm = length_mm * 0.37

    H = int(np.ceil(length_mm / pixel_size_mm))
    W = int(np.ceil(width_mm / pixel_size_mm))

    yy = np.linspace(0.0, 1.0, H)
    xx = np.linspace(-1.0, 1.0, W)
    Y, X = np.meshgrid(yy, xx, indexing="ij")

    profile = (
        0.55
        + 0.42 * np.exp(-((Y - 0.82) ** 2) / 0.012)
        + 0.30 * np.exp(-((Y - 0.08) ** 2) / 0.010)
        - 0.18 * np.exp(-((Y - 0.45) ** 2) / 0.020)
    )

    medial_offset = 0.08 * np.exp(-((Y - 0.55) ** 2) / 0.05)
    if lado == "direito":
        center = -medial_offset
    else:
        center = medial_offset

    upper = center + profile
    lower = center - profile

    mask = (X >= lower) & (X <= upper) & (Y >= 0.02) & (Y <= 0.98)
    mask = mask.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = mask > 0

    return mask, pixel_size_mm, length_mm, width_mm


def generate_palmilha(num_eur, tipo_pisada, lado="direito", pixel_size_mm=1.5):
    """
    Gera o mesh 3D da palmilha corretiva.

    num_eur: numeração europeia do calçado (ex: 38, 41)
    tipo_pisada: 'pronado' | 'cavo' | 'normal'
    lado: 'direito' | 'esquerdo'
    """
    mask, ps, length_mm, width_mm = _foot_outline(num_eur, lado, pixel_size_mm)
    H, W = mask.shape

    yy = np.linspace(0.0, 1.0, H)
    xx = np.linspace(-1.0, 1.0, W)
    Y, X = np.meshgrid(yy, xx, indexing="ij")

    if tipo_pisada == "pronado":
        arch_height = 11.0
        medial_wedge = 4.5
        heel_cup_depth = 5.0
        met_pad = 2.0
    elif tipo_pisada == "cavo":
        arch_height = 7.0
        medial_wedge = 0.5
        heel_cup_depth = 4.0
        met_pad = 4.0
    else:
        arch_height = 8.5
        medial_wedge = 1.5
        heel_cup_depth = 4.0
        met_pad = 2.5

    medial_sign = -1.0 if lado == "direito" else 1.0

    heel_cup = heel_cup_depth * np.exp(
        -(((Y - 0.10) ** 2) / 0.010 + (X ** 2) / 0.25)
    )

    arch_x_center = medial_sign * 0.45
    arch = arch_height * np.exp(
        -(((Y - 0.48) ** 2) / 0.025 + ((X - arch_x_center) ** 2) / 0.18)
    )

    wedge_x = medial_sign * X
    wedge = (
        medial_wedge
        * np.clip(-wedge_x + 0.1, 0.0, 1.2)
        * np.exp(-((Y - 0.42) ** 2) / 0.12)
    )

    met_dome = met_pad * np.exp(
        -(((Y - 0.72) ** 2) / 0.006 + (X ** 2) / 0.30)
    )

    border = 1.5 * np.exp(-((1.0 - np.abs(X)) ** 2) / 0.004) * (Y > 0.05) * (Y < 0.95)

    heightmap = heel_cup + arch + wedge + met_dome + border
    heightmap = np.where(mask, heightmap, 0.0)
    heightmap = gaussian_filter(heightmap, sigma=1.5)
    heightmap = np.where(mask, heightmap, 0.0)

    mesh = heightmap_to_mesh(
        heightmap,
        pixel_size_mm=ps,
        base_thickness_mm=3.0,
        mask=mask,
    )
    return mesh, {
        "comprimento_mm": float(length_mm),
        "largura_mm": float(width_mm),
        "altura_arco_mm": float(arch_height),
        "cunha_medial_mm": float(medial_wedge),
        "lado": lado,
        "tipo": tipo_pisada,
    }
