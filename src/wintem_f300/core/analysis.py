"""Malla, derivadas y vorticidad térmica para el nivel F300."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .parser import Bulletin, WintemPoint, meteorological_components

SpatialMode = Literal["legacy_constant", "latitude_aware"]


@dataclass(frozen=True, slots=True)
class GridConfig:
    """Constantes y decisiones numéricas de un análisis."""

    spatial_mode: SpatialMode = "legacy_constant"
    degree_to_m: float = 110_000.0
    gravity_m_s2: float = 9.8
    omega_rad_s: float = 7.2e-5
    equatorial_mask_deg: float = 5.0


@dataclass(frozen=True, slots=True)
class AnalysisGrid:
    latitudes: np.ndarray
    longitudes: np.ndarray
    temperature: np.ndarray
    speed_m_s: np.ndarray
    wind_u: np.ndarray
    wind_v: np.ndarray
    d2t_dx2: np.ndarray
    d2t_dy2: np.ndarray
    laplacian: np.ndarray
    coriolis: np.ndarray
    eta_temperature: np.ndarray
    dx_m_by_latitude: np.ndarray
    dy_m: float
    config: GridConfig

    @property
    def valid_eta_count(self) -> int:
        return int(np.isfinite(self.eta_temperature).sum())


@dataclass(frozen=True, slots=True)
class BulletinSummary:
    bulletin: str
    total_points: int
    valid_points: int
    mean: float
    standard_deviation: float
    minimum: float
    maximum: float


def _regular_spacing(values: np.ndarray, coordinate_name: str) -> float:
    differences = np.diff(values)
    if differences.size == 0 or np.any(differences <= 0):
        raise ValueError(f"La coordenada {coordinate_name} no es estrictamente creciente.")
    if not np.allclose(differences, differences[0], rtol=1e-6, atol=1e-8):
        raise ValueError(f"La coordenada {coordinate_name} no forma una malla regular.")
    return float(differences[0])


def second_derivatives(
    temperature: np.ndarray,
    dx_m_by_latitude: np.ndarray,
    dy_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Calcula derivadas segundas centradas; bordes y vecinos ausentes son NaN."""
    values = np.asarray(temperature, dtype=float)
    dx = np.asarray(dx_m_by_latitude, dtype=float)
    if values.ndim != 2 or dx.shape != (values.shape[0],):
        raise ValueError("Las dimensiones de temperatura y dx no son compatibles.")
    if np.any(dx <= 0) or dy_m <= 0:
        raise ValueError("Los pasos espaciales deben ser positivos.")

    d2t_dx2 = np.full(values.shape, np.nan, dtype=float)
    d2t_dy2 = np.full(values.shape, np.nan, dtype=float)
    d2t_dx2[:, 1:-1] = (
        values[:, 2:] - 2.0 * values[:, 1:-1] + values[:, :-2]
    ) / dx[:, np.newaxis] ** 2
    d2t_dy2[1:-1, :] = (
        values[2:, :] - 2.0 * values[1:-1, :] + values[:-2, :]
    ) / dy_m**2
    return d2t_dx2, d2t_dy2


def coriolis_parameter(latitudes: np.ndarray, omega_rad_s: float = 7.2e-5) -> np.ndarray:
    """Devuelve f = 2 Ω sin(φ) para cada latitud."""
    return 2.0 * omega_rad_s * np.sin(np.deg2rad(np.asarray(latitudes, dtype=float)))


def eta_temperature(
    laplacian: np.ndarray,
    latitudes: np.ndarray,
    *,
    gravity_m_s2: float = 9.8,
    omega_rad_s: float = 7.2e-5,
    equatorial_mask_deg: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Calcula eta_T=(g/f)∇²T y enmascara la banda ecuatorial indicada."""
    field = np.asarray(laplacian, dtype=float)
    latitude_values = np.asarray(latitudes, dtype=float)
    if field.ndim != 2 or field.shape[0] != latitude_values.size:
        raise ValueError("El laplaciano debe tener una fila por latitud.")
    coriolis = coriolis_parameter(latitude_values, omega_rad_s)
    with np.errstate(divide="ignore", invalid="ignore"):
        eta = (gravity_m_s2 / coriolis[:, np.newaxis]) * field
    mask = np.abs(latitude_values) <= max(0.0, equatorial_mask_deg)
    eta[mask, :] = np.nan
    eta[~np.isfinite(field)] = np.nan
    return eta, coriolis


def build_analysis_grid(
    bulletins: dict[str, Bulletin],
    config: GridConfig | None = None,
) -> AnalysisGrid:
    """Ensambla una malla regional y calcula todos los diagnósticos."""
    settings = config or GridConfig()
    points = [point for bulletin in bulletins.values() for point in bulletin.points]
    if not points:
        raise ValueError("No existen puntos F300 para analizar.")

    latitudes = np.array(sorted({point.latitude for point in points}), dtype=float)
    longitudes = np.array(sorted({point.longitude for point in points}), dtype=float)
    if latitudes.size < 3 or longitudes.size < 3:
        raise ValueError("Se requieren al menos tres latitudes y tres longitudes.")
    latitude_step = _regular_spacing(latitudes, "latitud")
    longitude_step = _regular_spacing(longitudes, "longitud")
    dy_m = latitude_step * settings.degree_to_m
    if settings.spatial_mode == "legacy_constant":
        dx_m_by_latitude = np.full(latitudes.shape, longitude_step * settings.degree_to_m)
    elif settings.spatial_mode == "latitude_aware":
        dx_m_by_latitude = (
            longitude_step * settings.degree_to_m * np.cos(np.deg2rad(latitudes))
        )
    else:
        raise ValueError(f"Modo espacial desconocido: {settings.spatial_mode}")
    if np.any(dx_m_by_latitude <= 0):
        raise ValueError("La malla alcanza latitudes donde el paso zonal no es válido.")

    shape = (latitudes.size, longitudes.size)
    temperature = np.full(shape, np.nan)
    speed = np.full(shape, np.nan)
    wind_u = np.full(shape, np.nan)
    wind_v = np.full(shape, np.nan)
    lat_index = {value: index for index, value in enumerate(latitudes)}
    lon_index = {value: index for index, value in enumerate(longitudes)}

    for point in points:
        row, column = lat_index[point.latitude], lon_index[point.longitude]
        previous = temperature[row, column]
        if np.isfinite(previous):
            if not np.isclose(previous, point.temperature_c):
                raise ValueError(
                    "Temperaturas contradictorias en "
                    f"({point.latitude:g}°, {point.longitude:g}°)."
                )
            continue
        u_component, v_component = meteorological_components(point)
        temperature[row, column] = point.temperature_c
        speed[row, column] = point.speed_m_s
        wind_u[row, column] = u_component
        wind_v[row, column] = v_component

    d2t_dx2, d2t_dy2 = second_derivatives(temperature, dx_m_by_latitude, dy_m)
    laplacian = d2t_dx2 + d2t_dy2
    eta, coriolis = eta_temperature(
        laplacian,
        latitudes,
        gravity_m_s2=settings.gravity_m_s2,
        omega_rad_s=settings.omega_rad_s,
        equatorial_mask_deg=settings.equatorial_mask_deg,
    )
    return AnalysisGrid(
        latitudes=latitudes,
        longitudes=longitudes,
        temperature=temperature,
        speed_m_s=speed,
        wind_u=wind_u,
        wind_v=wind_v,
        d2t_dx2=d2t_dx2,
        d2t_dy2=d2t_dy2,
        laplacian=laplacian,
        coriolis=coriolis,
        eta_temperature=eta,
        dx_m_by_latitude=dx_m_by_latitude,
        dy_m=dy_m,
        config=settings,
    )


def point_diagnostic(point: WintemPoint, grid: AnalysisGrid) -> tuple[float, ...]:
    row_matches = np.flatnonzero(np.isclose(grid.latitudes, point.latitude))
    column_matches = np.flatnonzero(np.isclose(grid.longitudes, point.longitude))
    if not row_matches.size or not column_matches.size:
        raise ValueError("El punto no pertenece a la malla de análisis.")
    row, column = int(row_matches[0]), int(column_matches[0])
    return (
        grid.d2t_dx2[row, column],
        grid.d2t_dy2[row, column],
        grid.laplacian[row, column],
        grid.coriolis[row],
        grid.eta_temperature[row, column],
    )


def summarize_bulletins(
    bulletins: dict[str, Bulletin], grid: AnalysisGrid
) -> tuple[BulletinSummary, ...]:
    summaries: list[BulletinSummary] = []
    for bulletin in bulletins.values():
        values = np.array([point_diagnostic(point, grid)[-1] for point in bulletin.points])
        finite = values[np.isfinite(values)]
        summaries.append(
            BulletinSummary(
                bulletin=bulletin.name,
                total_points=int(values.size),
                valid_points=int(finite.size),
                mean=float(np.mean(finite)) if finite.size else np.nan,
                standard_deviation=float(np.std(finite, ddof=1)) if finite.size > 1 else np.nan,
                minimum=float(np.min(finite)) if finite.size else np.nan,
                maximum=float(np.max(finite)) if finite.size else np.nan,
            )
        )
    return tuple(summaries)
