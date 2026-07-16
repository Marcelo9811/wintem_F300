"""Figuras Matplotlib/Cartopy reutilizables por interfaces de usuario."""

from __future__ import annotations

from collections.abc import Callable

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.figure import Figure

from .core.analysis import AnalysisGrid
from .core.parser import Bulletin, meteorological_components

MAP_PADDING_DEG = 5.0


def _map_axis(figure: Figure, grid: AnalysisGrid):
    axis = figure.add_subplot(111, projection=ccrs.PlateCarree())
    axis.set_extent(
        [
            max(-180.0, float(grid.longitudes.min()) - MAP_PADDING_DEG),
            min(180.0, float(grid.longitudes.max()) + MAP_PADDING_DEG),
            max(-90.0, float(grid.latitudes.min()) - MAP_PADDING_DEG),
            min(90.0, float(grid.latitudes.max()) + MAP_PADDING_DEG),
        ],
        crs=ccrs.PlateCarree(),
    )
    axis.add_feature(cfeature.LAND, facecolor="#f1eee4", zorder=0)
    axis.add_feature(cfeature.OCEAN, facecolor="#dceef8", zorder=0)
    axis.add_feature(cfeature.COASTLINE, linewidth=0.55, edgecolor="#374151", zorder=3)
    axis.add_feature(cfeature.BORDERS, linewidth=0.4, edgecolor="#6b7280", zorder=3)
    axis.gridlines(draw_labels=True, linewidth=0.3, color="#6b7280", alpha=0.6)
    return axis


def scalar_map(
    figure: Figure,
    grid: AnalysisGrid,
    field: np.ndarray,
    title: str,
    label: str,
    cmap: str,
    *,
    centered: bool = False,
) -> None:
    axis = _map_axis(figure, grid)
    finite = field[np.isfinite(field)]
    norm = None
    if centered and finite.size:
        limit = float(np.max(np.abs(finite)))
        if limit > 0:
            norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    image = axis.pcolormesh(
        grid.longitudes,
        grid.latitudes,
        np.ma.masked_invalid(field),
        transform=ccrs.PlateCarree(),
        shading="nearest",
        cmap=cmap,
        norm=norm,
        alpha=0.83,
        zorder=1,
    )
    axis.set_title(title, fontsize=14, fontweight="bold")
    colorbar = figure.colorbar(image, ax=axis, orientation="horizontal", pad=0.08, shrink=0.78)
    colorbar.set_label(label)
    figure.subplots_adjust(left=0.06, right=0.96, bottom=0.14, top=0.91)


def wind_map(figure: Figure, grid: AnalysisGrid, bulletins: dict[str, Bulletin]) -> None:
    axis = _map_axis(figure, grid)
    heatmap = axis.pcolormesh(
        grid.longitudes,
        grid.latitudes,
        np.ma.masked_invalid(grid.speed_m_s),
        transform=ccrs.PlateCarree(),
        shading="nearest",
        cmap="turbo",
        alpha=0.72,
        zorder=1,
    )
    colors = matplotlib.colormaps["tab10"](np.linspace(0, 1, max(2, len(bulletins))))
    for color, bulletin in zip(colors, bulletins.values()):
        longitudes = np.array([point.longitude for point in bulletin.points])
        latitudes = np.array([point.latitude for point in bulletin.points])
        components = np.array([meteorological_components(point) for point in bulletin.points])
        axis.scatter(
            longitudes, latitudes, s=24, color=color, edgecolor="black", linewidth=0.25,
            label=bulletin.name, transform=ccrs.PlateCarree(), zorder=4,
        )
        axis.quiver(
            longitudes, latitudes, components[:, 0], components[:, 1], color=[color],
            scale=420, width=0.0024, transform=ccrs.PlateCarree(), zorder=4,
        )
    axis.legend(title="Boletín", bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    axis.set_title("Viento y velocidad regional — F300", fontsize=14, fontweight="bold")
    figure.colorbar(heatmap, ax=axis, orientation="horizontal", pad=0.08, shrink=0.75, label="m/s")
    figure.subplots_adjust(left=0.05, right=0.82, bottom=0.14, top=0.91)


def bulletin_grid(figure: Figure, bulletin: Bulletin) -> None:
    latitudes = bulletin.latitudes
    longitudes = bulletin.longitudes
    lat_index = {value: index for index, value in enumerate(latitudes)}
    lon_index = {value: index for index, value in enumerate(longitudes)}
    direction_axis = figure.add_subplot(121)
    speed_axis = figure.add_subplot(122)
    speeds = np.full((len(latitudes), len(longitudes)), np.nan)
    for axis, title in ((direction_axis, "Dirección"), (speed_axis, "Velocidad y temperatura")):
        axis.set_xlim(-0.5, len(longitudes) - 0.5)
        axis.set_ylim(len(latitudes) - 0.5, -0.5)
        axis.set_xticks(range(len(longitudes)), [f"{value:g}°" for value in longitudes], rotation=40)
        axis.set_yticks(range(len(latitudes)), [f"{value:g}°" for value in latitudes])
        axis.set_xticks(np.arange(-0.5, len(longitudes), 1), minor=True)
        axis.set_yticks(np.arange(-0.5, len(latitudes), 1), minor=True)
        axis.grid(which="minor", color="#9ca3af", linewidth=0.7)
        axis.tick_params(which="minor", bottom=False, left=False)
        axis.set_title(title, fontweight="bold")
    for point in bulletin.points:
        row, column = lat_index[point.latitude], lon_index[point.longitude]
        u, v = meteorological_components(point)
        magnitude = max(point.speed_m_s, 1e-12)
        direction_axis.arrow(
            column, row, 0.28 * u / magnitude, -0.28 * v / magnitude,
            width=0.015, head_width=0.1, color="#1d4ed8", length_includes_head=True,
        )
        direction_axis.text(column, row + 0.33, f"{point.direction_deg:03d}°", ha="center", fontsize=7)
        speeds[row, column] = point.speed_m_s
    image = speed_axis.imshow(speeds, cmap="YlOrRd", aspect="auto", interpolation="nearest")
    for point in bulletin.points:
        row, column = lat_index[point.latitude], lon_index[point.longitude]
        speed_axis.text(
            column, row, f"{point.speed_kt} KT\n{point.temperature_c}°C",
            ha="center", va="center", fontsize=7,
            bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "alpha": 0.7, "lw": 0},
        )
    figure.colorbar(image, ax=speed_axis, shrink=0.8, label="m/s")
    figure.suptitle(f"{bulletin.name} — F300", fontsize=15, fontweight="bold")
    figure.subplots_adjust(left=0.07, right=0.94, bottom=0.16, top=0.88, wspace=0.34)


def overview(figure: Figure, grid: AnalysisGrid, bulletins: dict[str, Bulletin]) -> None:
    axis = figure.add_subplot(111)
    axis.axis("off")
    point_count = sum(len(item.points) for item in bulletins.values())
    mode = "110 km/°" if grid.config.spatial_mode == "legacy_constant" else "cos(latitud)"
    cards = (
        ("Boletines", str(len(bulletins))),
        ("Puntos", str(point_count)),
        ("Malla", f"{grid.latitudes.size} × {grid.longitudes.size}"),
        ("η_T válidos", str(grid.valid_eta_count)),
        ("Modo espacial", mode),
        ("Banda ecuatorial", f"±{grid.config.equatorial_mask_deg:g}°"),
    )
    positions = ((0.18, 0.72), (0.5, 0.72), (0.82, 0.72), (0.18, 0.35), (0.5, 0.35), (0.82, 0.35))
    for (title, value), (x, y) in zip(cards, positions):
        axis.text(
            x, y, f"{value}\n{title}", ha="center", va="center", fontsize=12, linespacing=1.7,
            bbox={"boxstyle": "round,pad=0.9", "facecolor": "#eef4fb", "edgecolor": "#7aa6d1"},
        )
    axis.set_title("Resumen y control de calidad", fontsize=17, fontweight="bold", pad=18)


def create_figure(
    view_key: str,
    grid: AnalysisGrid,
    bulletins: dict[str, Bulletin],
    bulletin: Bulletin | None = None,
    *,
    figsize: tuple[float, float] = (11, 7),
) -> Figure:
    """Construye una figura nueva para una vista registrada."""
    figure = Figure(figsize=figsize, dpi=100)
    scalar_views: dict[str, tuple[np.ndarray, str, str, str, bool]] = {
        "temperature": (grid.temperature, "Temperatura regional F300", "Temperatura (°C)", "coolwarm", False),
        "d2x": (grid.d2t_dx2 * 1e11, "Segunda derivada zonal", "10⁻¹¹ K m⁻²", "PuOr_r", True),
        "d2y": (grid.d2t_dy2 * 1e11, "Segunda derivada meridional", "10⁻¹¹ K m⁻²", "PuOr_r", True),
        "laplacian": (grid.laplacian * 1e11, "Laplaciano horizontal ∇²T", "10⁻¹¹ K m⁻²", "BrBG_r", True),
        "eta": (grid.eta_temperature * 1e6, "Vorticidad térmica η_T", "η_T × 10⁶ [K m⁻¹ s⁻¹]", "RdBu_r", True),
    }
    if view_key == "overview":
        overview(figure, grid, bulletins)
    elif view_key == "wind":
        wind_map(figure, grid, bulletins)
    elif view_key == "bulletin":
        if bulletin is None:
            raise ValueError("Seleccione un boletín para esta vista.")
        bulletin_grid(figure, bulletin)
    elif view_key in scalar_views:
        field, title, label, cmap, centered = scalar_views[view_key]
        scalar_map(figure, grid, field, title, label, cmap, centered=centered)
    elif view_key == "coriolis":
        axis = figure.add_subplot(111)
        axis.plot(grid.coriolis * 1e5, grid.latitudes, marker="o", color="#1d4ed8")
        axis.axvline(0, color="black", linewidth=0.8)
        axis.axhspan(-grid.config.equatorial_mask_deg, grid.config.equatorial_mask_deg, color="#9ca3af", alpha=0.25)
        axis.set(title="Parámetro de Coriolis", xlabel="f (10⁻⁵ s⁻¹)", ylabel="Latitud (°)")
        axis.grid(alpha=0.25)
        figure.subplots_adjust(left=0.11, right=0.95, bottom=0.12, top=0.9)
    else:
        raise KeyError(f"Vista desconocida: {view_key}")
    return figure
