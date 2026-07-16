"""Decodificación de boletines WINTEM sin dependencias gráficas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

TARGET_LEVEL: Final = "F300"
KT_TO_M_S: Final = 0.5
EXCLUDED_SECTIONS: Final = frozenset({"TROP", "MAXW"})

LATITUDE_RE: Final = re.compile(r"^(\d{3})([NS])$")
LONGITUDE_RE: Final = re.compile(r"^(\d{4})([EW])$")
BULLETIN_RE: Final = re.compile(r"^(FB\w+)\s+KWBC\b")
GROUP_RE: Final = re.compile(
    r"^(?P<direction>\d{2})(?P<speed>\d{3})(?P<minus>M?)(?P<temperature>\d{2})$"
)


@dataclass(frozen=True, slots=True)
class WintemPoint:
    """Observación WINTEM decodificada en un punto isobárico."""

    bulletin: str
    latitude: float
    longitude: float
    direction_deg: int
    speed_kt: int
    temperature_c: int

    @property
    def speed_m_s(self) -> float:
        """Convierte nudos con la equivalencia docente original 1 KT = 0.5 m/s."""
        return self.speed_kt * KT_TO_M_S


@dataclass(frozen=True, slots=True)
class Bulletin:
    """Observaciones de un boletín, ordenadas de norte a sur y oeste a este."""

    name: str
    points: tuple[WintemPoint, ...]

    @property
    def latitudes(self) -> tuple[float, ...]:
        return tuple(sorted({point.latitude for point in self.points}, reverse=True))

    @property
    def longitudes(self) -> tuple[float, ...]:
        return tuple(sorted({point.longitude for point in self.points}))


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Boletines decodificados y advertencias recuperables."""

    bulletins: dict[str, Bulletin]
    warnings: tuple[str, ...]


def read_text(path: Path) -> str:
    """Lee un archivo probando las codificaciones habituales de los boletines."""
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"No fue posible decodificar el archivo: {path}")


def parse_coordinate(token: str) -> float:
    """Convierte 300N o 0800W a grados decimales con signo."""
    normalized = token.strip().upper()
    pattern = LATITUDE_RE if normalized.endswith(("N", "S")) else LONGITUDE_RE
    match = pattern.fullmatch(normalized)
    if match is None:
        raise ValueError(f"Coordenada no válida: {token!r}")
    value = int(match.group(1)) / 10.0
    return -value if match.group(2) in {"S", "W"} else value


def decode_group(token: str) -> tuple[int, int, int]:
    """Decodifica dirección, velocidad en KT y temperatura en °C."""
    match = GROUP_RE.fullmatch(token.strip().upper())
    if match is None:
        raise ValueError(f"Grupo F300 no válido: {token!r}")
    direction = int(match.group("direction")) * 10
    speed = int(match.group("speed"))
    temperature = int(match.group("temperature"))
    if match.group("minus") == "M":
        temperature *= -1
    return direction, speed, temperature


def parse_wintem_text(text: str, target_level: str = TARGET_LEVEL) -> ParseResult:
    """Extrae puntos del nivel solicitado a partir del contenido de un WINTEM."""
    points_by_bulletin: dict[str, list[WintemPoint]] = {}
    warnings: list[str] = []
    current_bulletin: str | None = None
    current_latitude: float | None = None
    current_longitudes: list[float] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        bulletin_match = BULLETIN_RE.match(line)
        if bulletin_match:
            current_bulletin = bulletin_match.group(1)
            points_by_bulletin.setdefault(current_bulletin, [])
            current_latitude = None
            current_longitudes = []
            continue

        tokens = line.split()
        first = tokens[0].upper()
        if LATITUDE_RE.fullmatch(first):
            if current_bulletin is None:
                raise ValueError(
                    f"Línea {line_number}: coordenada antes del encabezado FB... KWBC."
                )
            current_latitude = parse_coordinate(first)
            if len(tokens) > 1:
                current_longitudes = [parse_coordinate(token) for token in tokens[1:]]
            if not current_longitudes:
                raise ValueError(
                    f"Línea {line_number}: no existe una cabecera de longitudes reutilizable."
                )
            continue

        if first in EXCLUDED_SECTIONS or first != target_level.upper():
            continue
        if current_bulletin is None or current_latitude is None or not current_longitudes:
            raise ValueError(f"Línea {line_number}: {target_level} fuera de un bloque válido.")

        groups = tokens[1:]
        if len(groups) != len(current_longitudes):
            warnings.append(
                f"Línea {line_number}: {len(groups)} grupos para "
                f"{len(current_longitudes)} longitudes."
            )
        for longitude, group in zip(current_longitudes, groups):
            try:
                direction, speed, temperature = decode_group(group)
            except ValueError as error:
                warnings.append(f"Línea {line_number}: {error}")
                continue
            points_by_bulletin[current_bulletin].append(
                WintemPoint(
                    bulletin=current_bulletin,
                    latitude=current_latitude,
                    longitude=longitude,
                    direction_deg=direction,
                    speed_kt=speed,
                    temperature_c=temperature,
                )
            )

    bulletins = {
        name: Bulletin(
            name=name,
            points=tuple(sorted(points, key=lambda point: (-point.latitude, point.longitude))),
        )
        for name, points in points_by_bulletin.items()
        if points
    }
    if not bulletins:
        raise ValueError(f"No se encontraron observaciones {target_level} decodificables.")
    return ParseResult(bulletins=bulletins, warnings=tuple(warnings))


def parse_wintem(path: Path, target_level: str = TARGET_LEVEL) -> ParseResult:
    """Lee y decodifica un archivo WINTEM."""
    return parse_wintem_text(read_text(path), target_level)


def meteorological_components(point: WintemPoint) -> tuple[float, float]:
    """Convierte viento meteorológico "desde" a componentes cartesianas u, v."""
    import numpy as np

    angle = np.deg2rad(point.direction_deg)
    return (
        -point.speed_m_s * float(np.sin(angle)),
        -point.speed_m_s * float(np.cos(angle)),
    )


def format_latitude(value: float) -> str:
    return f"{abs(value):g}°{'N' if value >= 0 else 'S'}"


def format_longitude(value: float) -> str:
    return f"{abs(value):g}°{'E' if value >= 0 else 'W'}"
