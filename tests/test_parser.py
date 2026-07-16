from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wintem_f300.core.parser import decode_group, parse_coordinate, parse_wintem, parse_wintem_text


SAMPLE = """\
FBTEST KWBC 010000
120N 0800W 0700W 0600W
F300 27050M40 28055M39 29060M36
130N 0800W 0700W 0600W
F300 26045M39 27050M38 28055M35
140N 0800W 0700W 0600W
F300 25040M36 26045M35 27050M32
"""


class ParserTests(unittest.TestCase):
    def test_coordinates_and_group(self) -> None:
        self.assertEqual(parse_coordinate("120N"), 12.0)
        self.assertEqual(parse_coordinate("0800W"), -80.0)
        self.assertEqual(decode_group("27050M40"), (270, 50, -40))

    def test_parse_text_builds_bulletin(self) -> None:
        result = parse_wintem_text(SAMPLE)
        self.assertEqual(tuple(result.bulletins), ("FBTEST",))
        self.assertEqual(len(result.bulletins["FBTEST"].points), 9)
        self.assertEqual(result.warnings, ())

    def test_parse_path_is_independent_of_gui(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text(SAMPLE, encoding="utf-8")
            self.assertEqual(len(parse_wintem(path).bulletins), 1)


if __name__ == "__main__":
    unittest.main()
