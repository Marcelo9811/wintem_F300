"""Genera un informe estático de un archivo WINTEM para GitHub Pages."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import cartopy
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CARTOPY_DATA_DIR = PROJECT_ROOT / ".cartopy"
CARTOPY_DATA_DIR.mkdir(parents=True, exist_ok=True)
cartopy.config["data_dir"] = CARTOPY_DATA_DIR

from .core.analysis import AnalysisGrid, GridConfig, build_analysis_grid, summarize_bulletins
from .core.parser import Bulletin, parse_wintem
from .export import export_csv, finite_text
from .plotting import create_figure


LIGHTBOX_JAVASCRIPT = r'''(() => {
  const lightbox = document.querySelector("#image-lightbox");
  const expandedImage = lightbox?.querySelector("img");
  const closeButton = lightbox?.querySelector(".lightbox-close");
  let opener = null;

  if (!lightbox || !expandedImage || !closeButton) return;

  const close = () => {
    lightbox.hidden = true;
    expandedImage.src = "";
    expandedImage.alt = "";
    document.body.classList.remove("lightbox-open");
    opener?.focus();
  };

  document.querySelectorAll("[data-lightbox-src]").forEach((button) => {
    button.addEventListener("click", () => {
      opener = button;
      expandedImage.src = button.dataset.lightboxSrc;
      expandedImage.alt = button.dataset.lightboxAlt || "Figura ampliada";
      lightbox.hidden = false;
      document.body.classList.add("lightbox-open");
      closeButton.focus();
    });
  });

  closeButton.addEventListener("click", close);
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !lightbox.hidden) close();
  });
})();
'''


@dataclass(frozen=True, slots=True)
class SiteBuildResult:
    """Rutas y cantidades principales de una publicación generada."""

    index_path: Path
    figure_count: int
    bulletin_count: int
    observation_count: int
    valid_eta_count: int


def _save_figure(
    output_path: Path,
    view_key: str,
    grid: AnalysisGrid,
    bulletins: dict[str, Bulletin],
    bulletin: Bulletin | None = None,
) -> None:
    """Renderiza una figura sin abrir ventanas y la guarda como PNG."""
    figure = create_figure(
        view_key,
        grid,
        bulletins,
        bulletin,
        figsize=(12.5, 7.6),
    )
    figure.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    figure.clear()


def _summary_table(bulletins: dict[str, Bulletin], grid: AnalysisGrid) -> str:
    rows: list[str] = []
    for item in summarize_bulletins(bulletins, grid):
        rows.append(
            "<tr>"
            f"<th scope='row'>{escape(item.bulletin)}</th>"
            f"<td>{item.total_points}</td>"
            f"<td>{item.valid_points}</td>"
            f"<td>{finite_text(item.mean, 1e6)}</td>"
            f"<td>{finite_text(item.standard_deviation, 1e6)}</td>"
            f"<td>{finite_text(item.minimum, 1e6)}</td>"
            f"<td>{finite_text(item.maximum, 1e6)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _figure_card(filename: str, title: str, description: str) -> str:
    image_path = f"assets/figures/{filename}"
    return (
        "<article class='figure-card'>"
        f"<button class='image-button' type='button' data-lightbox-src='{image_path}' "
        f"data-lightbox-alt='{escape(title)}' aria-label='Ampliar {escape(title)}'>"
        f"<img loading='lazy' src='{image_path}' alt='{escape(title)}'>"
        "</button>"
        f"<div><h3>{escape(title)}</h3><p>{escape(description)}</p></div>"
        "</article>"
    )


def _build_html(
    source_path: Path,
    bulletins: dict[str, Bulletin],
    grid: AnalysisGrid,
    warnings: tuple[str, ...],
    regional_cards: str,
    bulletin_cards: str,
) -> str:
    observation_count = sum(len(bulletin.points) for bulletin in bulletins.values())
    observed_cells = int(np.isfinite(grid.temperature).sum())
    missing_cells = int(grid.temperature.size - observed_cells)
    warning_html = ""
    if warnings:
        warning_items = "".join(f"<li>{escape(item)}</li>" for item in warnings)
        warning_html = (
            "<section class='notice'><h2>Advertencias de lectura</h2>"
            f"<ul>{warning_items}</ul></section>"
        )

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Informe estático WINTEM F300 y vorticidad térmica.">
  <title>Informe WINTEM F300</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <header class="hero"><div class="wrap">
    <p class="eyebrow">INFORME METEOROLÓGICO ESTÁTICO</p>
    <h1>WINTEM · Nivel F300</h1>
    <p class="lead">Viento, temperatura y diagnóstico de vorticidad térmica calculados localmente.</p>
    <p class="meta">Fuente: <strong>{escape(source_path.name)}</strong></p>
  </div></header>

  <nav class="section-nav" aria-label="Secciones"><div class="wrap">
    <a href="#resumen">Resumen</a><a href="#productos">Mapas</a>
    <a href="#boletines">Boletines</a><a href="#estadisticas">Estadísticas</a>
    <a href="#metodo">Método</a>
  </div></nav>

  <main class="wrap">
    <section id="resumen">
      <h2>Resumen de control de calidad</h2>
      <div class="metrics">
        <article><strong>{len(bulletins)}</strong><span>boletines</span></article>
        <article><strong>{observation_count}</strong><span>observaciones</span></article>
        <article><strong>{grid.latitudes.size} × {grid.longitudes.size}</strong><span>malla</span></article>
        <article><strong>{observed_cells}</strong><span>celdas observadas</span></article>
        <article><strong>{missing_cells}</strong><span>celdas sin dato</span></article>
        <article><strong>{grid.valid_eta_count}</strong><span>valores válidos de η<sub>T</sub></span></article>
      </div>
      <p class="note">Una celda sin dato es una posición de la malla combinada para la que ningún boletín
      aporta temperatura. No representa necesariamente una falla instrumental. Los bordes, los huecos sin
      vecinos completos y la banda |φ| ≤ {grid.config.equatorial_mask_deg:g}° se mantienen como NaN.</p>
    </section>

    {warning_html}

    <section id="productos">
      <h2>Productos regionales</h2>
      <p>Seleccione cualquier figura para verla a resolución completa.</p>
      <div class="figure-grid">{regional_cards}</div>
    </section>

    <section id="boletines">
      <h2>Mallas por boletín</h2>
      <p>Dirección del viento, velocidad en nudos y temperatura en bloques separados por boletín.</p>
      <div class="figure-grid">{bulletin_cards}</div>
    </section>

    <section id="estadisticas">
      <h2>Resumen estadístico por boletín</h2>
      <div class="table-wrap"><table>
        <caption>η<sub>T</sub> × 10⁶ [K m⁻¹ s⁻¹]</caption>
        <thead><tr><th>Boletín</th><th>Puntos</th><th>Válidos</th><th>Media</th><th>Desv. estándar</th><th>Mínimo</th><th>Máximo</th></tr></thead>
        <tbody>{_summary_table(bulletins, grid)}</tbody>
      </table></div>
    </section>

    <section id="metodo">
      <h2>Método y alcance</h2>
      <div class="formula">η<sub>T</sub> = (g / f) [∂²T/∂x² + ∂²T/∂y²], &nbsp; f = 2 Ω sen(φ)</div>
      <p>Se analizan únicamente los grupos F300; MAXW y TROP se descartan. Se emplean
      g = {grid.config.gravity_m_s2:g} m s⁻², Ω = {grid.config.omega_rad_s:.1e} rad s⁻¹,
      1 KT = 0.5 m s⁻¹ y 1° = {grid.config.degree_to_m / 1000:g} km. Las derivadas segundas
      se calculan mediante diferencias centradas sobre la malla regular.</p>
      <p>Este sitio es una instantánea de resultados: no recalcula datos en el navegador y no contiene
      Tkinter, un servidor web ni un proceso Python remoto. Para actualizarlo se vuelve a ejecutar el
      generador local con el nuevo WINTEM y se publican los archivos modificados de <code>docs/</code>.</p>
      <p><a href="methodology.html">Metodología ampliada</a> · <a href="publishing.html">Guía de publicación</a></p>
    </section>
  </main>
  <footer><div class="wrap">WINTEM F300 · Producto científico para análisis académico. Verifique los datos antes de decisiones operativas.</div></footer>
  <div class="lightbox" id="image-lightbox" role="dialog" aria-modal="true" aria-label="Vista ampliada" hidden>
    <button class="lightbox-close" type="button" aria-label="Cerrar vista ampliada">×</button>
    <img src="" alt="">
  </div>
  <script src="assets/lightbox.js"></script>
</body>
</html>
"""


def build_static_site(
    source_path: Path,
    output_dir: Path,
    config: GridConfig | None = None,
) -> SiteBuildResult:
    """Procesa un WINTEM y crea HTML, PNG y CSV listos para GitHub Pages."""
    source_path = source_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    parse_result = parse_wintem(source_path)
    grid = build_analysis_grid(parse_result.bulletins, config)

    assets_dir = output_dir / "assets"
    figures_dir = assets_dir / "figures"
    data_dir = output_dir / "data"
    figures_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "lightbox.js").write_text(LIGHTBOX_JAVASCRIPT, encoding="utf-8")
    for stale_figure in figures_dir.glob("*.png"):
        stale_figure.unlink()

    export_csv(data_dir, parse_result.bulletins, grid)
    (output_dir / ".nojekyll").touch()

    regional_views = (
        ("overview", "00_resumen.png", "Resumen", "Indicadores de cobertura y control de calidad."),
        ("wind", "01_viento.png", "Viento y velocidad", "Vectores de viento sobre el campo de velocidad."),
        ("temperature", "02_temperatura.png", "Temperatura F300", "Distribución espacial de la temperatura observada."),
        ("d2x", "03_derivada_zonal.png", "Curvatura zonal", "Segunda derivada de T respecto de x."),
        ("d2y", "04_derivada_meridional.png", "Curvatura meridional", "Segunda derivada de T respecto de y."),
        ("laplacian", "05_laplaciano.png", "Laplaciano térmico", "Suma de las curvaturas zonal y meridional."),
        ("coriolis", "06_coriolis.png", "Parámetro de Coriolis", "Variación de f con la latitud; escala 10⁻⁵ s⁻¹."),
        ("eta", "07_vorticidad_termica.png", "Vorticidad térmica", "Diagnóstico η_T con la banda ecuatorial enmascarada."),
    )
    regional_cards: list[str] = []
    for view_key, filename, title, description in regional_views:
        _save_figure(figures_dir / filename, view_key, grid, parse_result.bulletins)
        regional_cards.append(_figure_card(filename, title, description))

    bulletin_cards: list[str] = []
    for index, bulletin in enumerate(parse_result.bulletins.values(), start=1):
        filename = f"boletin_{index:02d}_{bulletin.name.lower()}.png"
        _save_figure(
            figures_dir / filename,
            "bulletin",
            grid,
            parse_result.bulletins,
            bulletin,
        )
        bulletin_cards.append(
            _figure_card(
                filename,
                bulletin.name,
                f"{len(bulletin.points)} observaciones decodificadas en F300.",
            )
        )

    index_path = output_dir / "index.html"
    index_path.write_text(
        _build_html(
            source_path,
            parse_result.bulletins,
            grid,
            parse_result.warnings,
            "".join(regional_cards),
            "".join(bulletin_cards),
        ),
        encoding="utf-8",
    )
    observation_count = sum(len(item.points) for item in parse_result.bulletins.values())
    return SiteBuildResult(
        index_path=index_path,
        figure_count=len(regional_views) + len(parse_result.bulletins),
        bulletin_count=len(parse_result.bulletins),
        observation_count=observation_count,
        valid_eta_count=grid.valid_eta_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera un informe WINTEM F300 estático para GitHub Pages."
    )
    parser.add_argument("wintem", type=Path, help="Archivo WINTEM .txt de entrada.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs"),
        help="Carpeta de salida (predeterminado: docs).",
    )
    args = parser.parse_args()
    result = build_static_site(args.wintem, args.output)
    print(f"Sitio generado: {result.index_path}")
    print(
        f"{result.figure_count} figuras, {result.bulletin_count} boletines, "
        f"{result.observation_count} observaciones y "
        f"{result.valid_eta_count} valores válidos de eta_T."
    )


if __name__ == "__main__":
    main()
