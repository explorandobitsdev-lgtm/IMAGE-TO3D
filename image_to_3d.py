"""
Conversor imagem → 3D (open source).

Modos:
  heightmap  Converte qualquer imagem em mesh 3D usando tons de cinza como altura.
  palmilha   Analisa foto de pisada, classifica (pronada/normal/cava) e gera
             palmilha corretiva 3D com suporte de arco, heel cup e cunha medial.

Saída: arquivos .stl + .obj.

Exemplos:
  python image_to_3d.py heightmap minha_foto.jpg --out logo3d
  python image_to_3d.py palmilha pisada.jpg --num 41
  python image_to_3d.py palmilha pisada.jpg            (pergunta a numeração)
"""
import argparse
import os
import sys

from heightmap_utils import heightmap_to_mesh, save_mesh
from image_processing import prepare_heightmap_image
from palmilha import analyze_footprint, generate_palmilha


def cmd_heightmap(args):
    enhance = not args.no_enhance
    heightmap, mask, prep = prepare_heightmap_image(
        args.image,
        max_height_mm=args.max_height,
        max_dim=args.max_dim,
        invert=args.invert,
        auto_invert=args.auto_invert,
        blur_radius=args.blur,
        threshold=args.threshold,
        auto_crop=args.auto_crop,
        normalize=enhance,
        denoise=enhance,
        edge_boost=args.edge_boost if enhance else 0.0,
    )

    if prep["scale"] != 1.0:
        print(
            f"  -> redimensionado para "
            f"{prep['output_size'][0]}x{prep['output_size'][1]}"
        )
    if prep["cropped"]:
        print(f"  -> recorte aplicado: {prep['output_size'][0]}x{prep['output_size'][1]}")
    if prep["auto_inverted"]:
        print("  -> inversao automatica aplicada (objeto escuro virou relevo alto)")
    if prep["enhanced"]:
        print("  -> melhoria aplicada: contraste, denoise e realce leve")

    print(
        f"  gerando mesh ({heightmap.shape[0]}x{heightmap.shape[1]} pixels, "
        f"{prep['mask_pixels']} px ativos)..."
    )
    mesh = heightmap_to_mesh(
        heightmap,
        pixel_size_mm=args.pixel_size,
        base_thickness_mm=args.base_thickness,
        mask=mask,
    )

    out_base = args.out or os.path.splitext(args.image)[0] + "_3d"
    stl, obj = save_mesh(mesh, out_base)
    print(f"  STL: {stl}")
    print(f"  OBJ: {obj}")
    print(f"  vértices: {len(mesh.vertices)}  faces: {len(mesh.faces)}")


def _ask_numeracao():
    while True:
        raw = input("Numeração europeia do calçado (ex: 38, 41): ").strip()
        try:
            n = int(raw)
            if 28 <= n <= 50:
                return n
            print("  Use um valor entre 28 e 50.")
        except ValueError:
            print("  Valor inválido, digite só o número.")


def cmd_palmilha(args):
    print(f"[1/3] Analisando pisada: {args.image}")
    info = analyze_footprint(args.image)
    print(
        f"  índice de arco (Cavanagh): {info['arch_index']:.3f}"
        f"  →  pisada {info['tipo'].upper()}"
    )
    print(f"  lado estimado: pé {info['lado']}")
    print(
        f"  áreas (px): antepé={info['areas']['antepe']}  "
        f"mesopé={info['areas']['mesope']}  retropé={info['areas']['retrope']}"
    )

    if args.num is not None:
        num = args.num
    else:
        num = _ask_numeracao()

    lado = args.lado or info["lado"]

    print(f"[2/3] Gerando palmilha numeração {num}, pé {lado}, tipo {info['tipo']}...")
    mesh, params = generate_palmilha(
        num_eur=num,
        tipo_pisada=info["tipo"],
        lado=lado,
        pixel_size_mm=args.resolution,
    )
    print(
        f"  dimensões: {params['comprimento_mm']:.1f} x "
        f"{params['largura_mm']:.1f} mm"
    )
    print(
        f"  altura do arco: {params['altura_arco_mm']:.1f} mm  "
        f"cunha medial: {params['cunha_medial_mm']:.1f} mm"
    )

    print("[3/3] Salvando arquivos...")
    out_base = args.out or f"palmilha_{num}_{info['tipo']}_{lado}"
    stl, obj = save_mesh(mesh, out_base)
    print(f"  STL: {stl}")
    print(f"  OBJ: {obj}")
    print(f"  vértices: {len(mesh.vertices)}  faces: {len(mesh.faces)}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="image_to_3d",
        description="Conversor imagem → 3D (open source: numpy, opencv, trimesh).",
    )
    sub = p.add_subparsers(dest="mode", required=True)

    ph = sub.add_parser(
        "heightmap",
        help="Converte imagem genérica em 3D por relevo (tons de cinza = altura).",
    )
    ph.add_argument("image", help="Caminho da imagem de entrada.")
    ph.add_argument("--out", help="Caminho de saída sem extensão.")
    ph.add_argument(
        "--max-height", type=float, default=10.0, help="Altura máxima em mm (def: 10)."
    )
    ph.add_argument(
        "--pixel-size",
        type=float,
        default=0.3,
        help="Tamanho de cada pixel em mm (def: 0.3).",
    )
    ph.add_argument(
        "--base-thickness",
        type=float,
        default=2.0,
        help="Espessura da base em mm (def: 2).",
    )
    ph.add_argument(
        "--max-dim",
        type=int,
        default=400,
        help="Redimensiona se maior dimensão exceder N pixels (def: 400).",
    )
    ph.add_argument("--blur", type=int, default=1, help="Desfoque suave (def: 1).")
    ph.add_argument(
        "--invert", action="store_true", help="Inverte (escuro = alto)."
    )
    ph.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="Se >0, pixels abaixo do valor são removidos do mesh.",
    )
    ph.add_argument(
        "--auto-invert",
        action="store_true",
        help="Detecta objeto escuro em fundo claro e transforma em relevo alto.",
    )
    ph.add_argument(
        "--auto-crop",
        action="store_true",
        help="Recorta a area ativa quando houver mascara/threshold.",
    )
    ph.add_argument(
        "--no-enhance",
        action="store_true",
        help="Desativa normalizacao de contraste, denoise e realce.",
    )
    ph.add_argument(
        "--edge-boost",
        type=float,
        default=0.18,
        help="Realce fino antes da suavizacao (def: 0.18).",
    )
    ph.set_defaults(func=cmd_heightmap)

    pp = sub.add_parser(
        "palmilha",
        help="Analisa foto de pisada e gera palmilha 3D corretiva.",
    )
    pp.add_argument("image", help="Foto da pisada (impressão da planta do pé).")
    pp.add_argument(
        "--num",
        type=int,
        help="Numeração europeia (28–50). Se omitir, pergunta interativamente.",
    )
    pp.add_argument(
        "--lado",
        choices=["direito", "esquerdo"],
        help="Forçar lado (def: estimado pela imagem).",
    )
    pp.add_argument(
        "--resolution",
        type=float,
        default=1.5,
        help="Tamanho do pixel da palmilha em mm (def: 1.5).",
    )
    pp.add_argument("--out", help="Caminho base de saída sem extensão.")
    pp.set_defaults(func=cmd_palmilha)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
