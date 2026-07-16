import unittest

import numpy as np

from wintem_f300.core.analysis import (
    GridConfig,
    build_analysis_grid,
    eta_temperature,
    second_derivatives,
)
from wintem_f300.core.parser import Bulletin, WintemPoint


def quadratic_bulletin() -> dict[str, Bulletin]:
    points = []
    latitudes = (10.0, 11.0, 12.0, 13.0, 14.0)
    longitudes = (-80.0, -79.0, -78.0, -77.0, -76.0)
    for row, latitude in enumerate(latitudes):
        for column, longitude in enumerate(longitudes):
            points.append(
                WintemPoint(
                    bulletin="FBTEST",
                    latitude=latitude,
                    longitude=longitude,
                    direction_deg=270,
                    speed_kt=50,
                    temperature_c=row**2 + column**2,
                )
            )
    return {"FBTEST": Bulletin("FBTEST", tuple(points))}


class DerivativeTests(unittest.TestCase):
    def test_centered_derivatives_of_quadratic_field(self) -> None:
        coordinates = np.arange(5, dtype=float)
        field = coordinates[:, None] ** 2 + coordinates[None, :] ** 2
        d2x, d2y = second_derivatives(field, np.full(5, 2.0), 4.0)
        np.testing.assert_allclose(d2x[1:-1, 1:-1], 0.5)
        np.testing.assert_allclose(d2y[1:-1, 1:-1], 0.125)
        self.assertTrue(np.isnan(d2x[:, 0]).all())
        self.assertTrue(np.isnan(d2y[0, :]).all())

    def test_eta_temperature_formula_and_equatorial_mask(self) -> None:
        laplacian = np.ones((3, 3)) * 2e-11
        latitudes = np.array((-10.0, 0.0, 10.0))
        eta, coriolis = eta_temperature(laplacian, latitudes, equatorial_mask_deg=5.0)
        expected = 9.8 / coriolis[2] * 2e-11
        self.assertAlmostEqual(eta[2, 1], expected)
        self.assertTrue(np.isnan(eta[1]).all())
        self.assertAlmostEqual(eta[0, 1], -expected)


class GridTests(unittest.TestCase):
    def test_build_analysis_grid_legacy(self) -> None:
        grid = build_analysis_grid(quadratic_bulletin(), GridConfig(spatial_mode="legacy_constant"))
        expected = 2.0 / 110_000.0**2
        self.assertAlmostEqual(grid.d2t_dx2[2, 2], expected)
        self.assertAlmostEqual(grid.d2t_dy2[2, 2], expected)
        self.assertEqual(grid.valid_eta_count, 9)

    def test_latitude_aware_mode_changes_zonal_spacing(self) -> None:
        grid = build_analysis_grid(quadratic_bulletin(), GridConfig(spatial_mode="latitude_aware"))
        expected_dx = 110_000.0 * np.cos(np.deg2rad(12.0))
        self.assertAlmostEqual(grid.dx_m_by_latitude[2], expected_dx)
        self.assertAlmostEqual(grid.d2t_dx2[2, 2], 2.0 / expected_dx**2)

    def test_rejects_contradictory_temperature(self) -> None:
        bulletins = quadratic_bulletin()
        duplicate = WintemPoint("FBOTHER", 12.0, -78.0, 270, 50, 99)
        bulletins["FBOTHER"] = Bulletin("FBOTHER", (duplicate,))
        with self.assertRaisesRegex(ValueError, "contradictorias"):
            build_analysis_grid(bulletins)


if __name__ == "__main__":
    unittest.main()
