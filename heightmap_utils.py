"""Conversão de heightmap (matriz 2D de alturas) em mesh 3D sólido."""
import numpy as np
import trimesh


def _quad_wall_faces(v_top_a, v_top_b, n_top):
    """
    Constrói as 2 triângulos de uma parede vertical entre dois vértices do topo.
    v_top_a, v_top_b: arrays de índices no plano superior, ordem CCW vista de fora.
    Retorna array (N*2, 3).
    """
    b_a = v_top_a + n_top
    b_b = v_top_b + n_top
    return np.column_stack([v_top_a, v_top_b, b_b, v_top_a, b_b, b_a]).reshape(-1, 3)


def heightmap_to_mesh(heightmap, pixel_size_mm=1.0, base_thickness_mm=2.0, mask=None):
    """
    Converte um heightmap em mesh 3D sólido com base plana.

    heightmap: array 2D (H, W) com alturas em mm acima da base
    pixel_size_mm: tamanho de cada pixel em mm
    base_thickness_mm: espessura mínima da base (a altura total = base + heightmap)
    mask: opcional, array booleano 2D. Onde False, não há mesh.
    """
    heightmap = np.asarray(heightmap, dtype=np.float64)
    H, W = heightmap.shape

    if mask is None:
        mask = np.ones_like(heightmap, dtype=bool)
    mask = np.asarray(mask, dtype=bool)

    z_top = heightmap + base_thickness_mm
    z_bot = np.zeros_like(heightmap)

    xs = np.arange(W) * pixel_size_mm
    ys = np.arange(H) * pixel_size_mm
    X, Y = np.meshgrid(xs, ys)

    top_verts = np.column_stack([X.ravel(), Y.ravel(), z_top.ravel()])
    bot_verts = np.column_stack([X.ravel(), Y.ravel(), z_bot.ravel()])
    vertices = np.vstack([top_verts, bot_verts])
    n_top = H * W

    valid_cell = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, :-1] & mask[1:, 1:]
    cell_i, cell_j = np.where(valid_cell)

    v00 = cell_i * W + cell_j
    v01 = cell_i * W + cell_j + 1
    v11 = (cell_i + 1) * W + cell_j + 1
    v10 = (cell_i + 1) * W + cell_j

    top_faces = np.column_stack([v00, v01, v11, v00, v11, v10]).reshape(-1, 3)

    b00 = v00 + n_top
    b01 = v01 + n_top
    b11 = v11 + n_top
    b10 = v10 + n_top
    bot_faces = np.column_stack([b00, b11, b01, b00, b10, b11]).reshape(-1, 3)

    walls = []

    if H >= 2:
        above = valid_cell[:-1, :]
        below = valid_cell[1:, :]
        i_idx, j_idx = np.where(above & ~below)
        if i_idx.size:
            va = (i_idx + 1) * W + j_idx
            vb = (i_idx + 1) * W + j_idx + 1
            walls.append(_quad_wall_faces(va, vb, n_top))
        i_idx, j_idx = np.where(~above & below)
        if i_idx.size:
            va = (i_idx + 1) * W + j_idx + 1
            vb = (i_idx + 1) * W + j_idx
            walls.append(_quad_wall_faces(va, vb, n_top))

        j_top = np.where(valid_cell[0])[0]
        if j_top.size:
            va = j_top + 1
            vb = j_top
            walls.append(_quad_wall_faces(va, vb, n_top))
        j_bot = np.where(valid_cell[-1])[0]
        if j_bot.size:
            va = (H - 1) * W + j_bot
            vb = (H - 1) * W + j_bot + 1
            walls.append(_quad_wall_faces(va, vb, n_top))

    if W >= 2:
        left = valid_cell[:, :-1]
        right = valid_cell[:, 1:]
        i_idx, j_idx = np.where(left & ~right)
        if i_idx.size:
            va = i_idx * W + j_idx + 1
            vb = (i_idx + 1) * W + j_idx + 1
            walls.append(_quad_wall_faces(va, vb, n_top))
        i_idx, j_idx = np.where(~left & right)
        if i_idx.size:
            va = (i_idx + 1) * W + j_idx + 1
            vb = i_idx * W + j_idx + 1
            walls.append(_quad_wall_faces(va, vb, n_top))

        i_left = np.where(valid_cell[:, 0])[0]
        if i_left.size:
            va = i_left * W
            vb = (i_left + 1) * W
            walls.append(_quad_wall_faces(va, vb, n_top))
        i_right = np.where(valid_cell[:, -1])[0]
        if i_right.size:
            va = (i_right + 1) * W + (W - 1)
            vb = i_right * W + (W - 1)
            walls.append(_quad_wall_faces(va, vb, n_top))

    if walls:
        side_faces = np.vstack(walls)
        faces = np.vstack([top_faces, bot_faces, side_faces])
    else:
        faces = np.vstack([top_faces, bot_faces])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    return mesh


def save_mesh(mesh, base_path):
    """Salva o mesh em STL e OBJ. base_path sem extensão."""
    stl_path = f"{base_path}.stl"
    obj_path = f"{base_path}.obj"
    mesh.export(stl_path)
    mesh.export(obj_path)
    return stl_path, obj_path
