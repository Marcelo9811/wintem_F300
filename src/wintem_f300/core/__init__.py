"""Lógica científica independiente de cualquier interfaz gráfica."""

from .analysis import (
    AnalysisGrid,
    BulletinSummary,
    GridConfig,
    build_analysis_grid,
    coriolis_parameter,
    eta_temperature,
    second_derivatives,
    summarize_bulletins,
)
from .parser import Bulletin, ParseResult, WintemPoint, parse_wintem, parse_wintem_text

__all__ = [
    "AnalysisGrid",
    "Bulletin",
    "BulletinSummary",
    "GridConfig",
    "ParseResult",
    "WintemPoint",
    "build_analysis_grid",
    "coriolis_parameter",
    "eta_temperature",
    "parse_wintem",
    "parse_wintem_text",
    "second_derivatives",
    "summarize_bulletins",
]
