"""Despacha jobs para o pipeline correto."""
from pathlib import Path
from typing import Callable


def dispatch(*, job_type, model, input, workdir: Path, on_progress: Callable, s3, bucket):
    """
    Retorna lista de tuplas (kind, local_path, meta) com os assets gerados.
    """
    if job_type == "image_to_3d":
        from .triposr_pipeline import run as run_triposr

        return run_triposr(input, workdir, on_progress, s3, bucket)

    if job_type == "text_to_3d":
        raise NotImplementedError(
            "text_to_3d ainda não implementado. Stub: usar Shap-E ou serviço externo."
        )

    if job_type == "heightmap":
        from .heightmap_pipeline import run as run_hm

        return run_hm(input, workdir, on_progress, s3, bucket)

    if job_type == "palmilha":
        from .palmilha_pipeline import run as run_pal

        return run_pal(input, workdir, on_progress, s3, bucket)

    raise ValueError(f"job_type desconhecido: {job_type}")
