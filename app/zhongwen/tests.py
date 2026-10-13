from app.zhongwen import colorize
from iafisher.prelude import *
from lib.testing import *


class Test(Base):
    def test_tone_of_syllable(self):
        self.assertEqual(colorize.tone_of_syllable("tiān"), 1)
        self.assertEqual(colorize.tone_of_syllable("hái"), 2)
        self.assertEqual(colorize.tone_of_syllable("nǚ"), 3)
        self.assertEqual(colorize.tone_of_syllable("guò"), 4)
        self.assertEqual(colorize.tone_of_syllable("le"), 5)

    def test_break_into_pinyin_syllables(self):
        phrase = "tīng de dào"
        syllables = colorize.break_into_pinyin_syllables(phrase)
        self.assertEqual(
            syllables,
            [("tīng", 1), (" ", None), ("de", 5), (" ", None), ("dào", 4)],
        )
        self.assertEqual("".join(s for s, _ in syllables), phrase)

    def test_decompose_diacritics(self):
        word = "nǚhái"
        self.assertEqual(
            list(colorize.decompose_diacritics(word)),
            [
                "n",
                "u",
                colorize.DIARESIS,
                colorize.TONE3_MARK,
                "h",
                "a",
                colorize.TONE2_MARK,
                "i",
            ],
        )
