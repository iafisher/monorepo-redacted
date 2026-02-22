import tempfile

from iafisher_foundation.prelude import *
from lib.testing import *

from .linereader import LineReader


class Test(Base):
    def test_linereader(self):
        test_content = """line1
line2

line4
END
line6
line7"""

        with tempfile.NamedTemporaryFile(mode="w") as f:
            f.write(test_content)
            f.flush()
            temp_path = pathlib.Path(f.name)

            with LineReader(temp_path) as reader:
                # Test basic read functionality
                self.assertEqual(reader.read(), "line1")
                self.assertEqual(reader.read(), "line2")
                self.assertEqual(reader.read(), "")
                self.assertEqual(reader.read(), "line4")

                # Test pushback functionality by reading and pushing back
                line = reader.read()
                self.assertEqual(line, "END")
                reader.pushback = line
                self.assertEqual(reader.read(), "END")  # should get the same line again

                # Test read_until functionality
                remaining_lines, found = reader.read_until("nonexistent")
                self.assertEqual(remaining_lines, ["line6", "line7"])
                self.assertFalse(found)

            # Test skip_blank_lines functionality
            with LineReader(temp_path) as reader:
                reader.read()  # line1
                reader.read()  # line2
                reader.skip_blank_lines()  # should skip blank line and position at line4
                self.assertEqual(reader.read(), "line4")

            # Test read_until with found end marker
            with LineReader(temp_path) as reader:
                lines, found = reader.read_until("END")
                self.assertEqual(lines, ["line1", "line2", "", "line4"])
                self.assertTrue(found)
