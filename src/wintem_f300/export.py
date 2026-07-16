"""Exportación de resultados sin acoplamiento a Tkinter."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .core.analysis import AnalysisGrid, point_diagnostic, summarize_bulletins
from .core.parser import Bulletin


def export_csv(
    output_dir: Path,
    bulletins: dict[str, Bulletin],
    grid: AnalysisGrid,
) -> tuple[Path, Path]:
    """Escribe la tabla por punto y el resumen por boletín."""
    output_dir.mkdir(parents=True, exist_ok=True)
    points_path = output_dir / "resultados_eta_f300.csv"
    with points_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "bulletin", "latitude", "longitude", "direction_deg", "speed_kt",
                "speed_m_s", "temperature_c", "d2T_dx2_K_m-2", "d2T_dy2_K_m-2",
                "laplacian_K_m-2", "coriolis_s-1", "eta_temperature_K_m-1_s-1",
            )
        )
        for bulletin in bulletins.values():
            for point in bulletin.points:
                writer.writerow(
                    (
                        bulletin.name,
                        point.latitude,
                        point.longitude,
                        point.direction_deg,
                        point.speed_kt,
                        point.speed_m_s,
                        point.temperature_c,
                        *point_diagnostic(point, grid),
                    )
                )

    summary_path = output_dir / "resumen_eta_por_boletin.csv"
    with summary_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("bulletin", "total_points", "valid_points", "mean", "std", "minimum", "maximum")
        )
        for summary in summarize_bulletins(bulletins, grid):
            writer.writerow(
                (
                    summary.bulletin,
                    summary.total_points,
                    summary.valid_points,
                    summary.mean,
                    summary.standard_deviation,
                    summary.minimum,
                    summary.maximum,
                )
            )
    return points_path, summary_path


def finite_text(value: float, scale: float = 1.0, decimals: int = 3) -> str:
    return "NaN" if not np.isfinite(value) else f"{value * scale:.{decimals}f}"
