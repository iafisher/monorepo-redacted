import copy
import string
import unicodedata
from typing import Sequence

from py_pinyin_split import PinyinTokenizer

from app.zhongwen import ankiconnect
from iafisher.prelude import *
from lib import command


def main_colorize(*, write: bool, verbose: bool) -> None:
    notes = fetch_notes()
    updated_notes: List[ankiconnect.NoteInfo] = []
    for note in notes:
        if already_colorized(note):
            continue

        assert_expected_characters(note)
        updated_notes.append(colorize_note(note, verbose=verbose))

    if write:
        update_notes(updated_notes)


def main_add_uncolorized_fields(*, write: bool) -> None:
    notes = fetch_notes()
    updated_notes: List[ankiconnect.NoteInfo] = []
    for note in notes:
        if len(note.get_field_value("pinyin")) > 0:
            continue

        updated_note = copy.deepcopy(note)
        pinyin = strip_html_tags(updated_note.get_field_value("pinyin_colorized"))
        hanzi = strip_html_tags(updated_note.get_field_value("hanzi_colorized"))
        print(f"{hanzi} {pinyin}")
        updated_note.fields["pinyin"].value = pinyin
        updated_note.fields["hanzi"].value = hanzi
        updated_notes.append(updated_note)

    if write:
        update_notes(updated_notes)


def main_replace_audio_display_text(*, write: bool) -> None:
    # This really has nothing to do with colorizing, but this file is a convenient
    # place to put this script.
    sheng = "声"

    def replace(note: ankiconnect.NoteInfo, field: str) -> None:
        note.fields[field].value = note.fields[field].value.replace(
            "[audio]", f"[{sheng}]"
        )

    notes = fetch_notes()
    updated_notes: List[ankiconnect.NoteInfo] = []
    for note in notes:
        if sheng in note.get_field_value("word_audio"):
            continue

        updated_note = copy.deepcopy(note)
        replace(updated_note, "word_audio")
        replace(updated_note, "sentence1_audio")
        replace(updated_note, "sentence2_audio")
        replace(updated_note, "sentence3_audio")
        replace(updated_note, "question1_audio")
        replace(updated_note, "answer1_audio")
        updated_notes.append(updated_note)

    if write:
        update_notes(updated_notes)


html_tag_rgx = lazy_re(r"<[^>]+>")


def strip_html_tags(s: str) -> str:
    return html_tag_rgx.get().sub("", s)


def already_colorized(note: ankiconnect.NoteInfo) -> bool:
    return CSS_CLASS_PREFIX in note.get_field_value("pinyin_colorized")


def fetch_notes() -> List[ankiconnect.NoteInfo]:
    return ankiconnect.search_notes(f'"note:{ankiconnect.WORD_NOTE_TYPE}"')


def update_notes(notes: List[ankiconnect.NoteInfo]) -> None:
    for note in notes:
        print("updating:", note.get_field_value("pinyin"))
        ankiconnect.update_note_fields(note)


def assert_expected_characters(note: ankiconnect.NoteInfo) -> None:
    pinyin = note.get_field_value("pinyin")
    for ch in decompose_diacritics(pinyin):
        dbg = (pinyin, ch, hex(ord(ch)))
        assert ch in string.ascii_lowercase or ch in (" ", "'") or ch in DIACRITICS, dbg


def colorize_pinyin_hanzi(pinyin: str, hanzi: str) -> Tuple[str, str]:
    pinyin_syllables = break_into_pinyin_syllables(pinyin)
    tones = [tone for _, tone in pinyin_syllables if tone is not None]
    if len(tones) != len(hanzi):
        raise KgError(
            "I could not match the tones to characters because they differed in length.",
            tones=tones,
            hanzi=hanzi,
            pinyin=pinyin,
            pinyin_syllables=pinyin_syllables,
        )

    hanzi_with_tones = list(zip(hanzi, tones))
    return colorize_syllables(pinyin_syllables), colorize_syllables(hanzi_with_tones)


def colorize_note(
    note: ankiconnect.NoteInfo, *, verbose: bool = False
) -> ankiconnect.NoteInfo:
    pinyin = note.get_field_value("pinyin")
    hanzi = note.get_field_value("hanzi")
    colorized_pinyin, colorized_hanzi = colorize_pinyin_hanzi(pinyin, hanzi)

    updated_note = copy.deepcopy(note)
    updated_note.fields["pinyin_colorized"].value = colorized_pinyin
    updated_note.fields["hanzi_colorized"].value = colorized_hanzi

    if verbose:
        print(
            updated_note.get_field_value("hanzi_colorized"),
            updated_note.get_field_value("pinyin_colorized"),
        )

    return updated_note


def colorize_syllables(syllables: Sequence[Tuple[str, Optional[int]]]) -> str:
    return "".join(
        [
            f'<span class="{css_class(tone)}">{s}</span>' if tone is not None else s
            for s, tone in syllables
        ]
    )


CSS_CLASS_PREFIX = "pinyin-tone-"


def css_class(tone: int) -> str:
    return f"{CSS_CLASS_PREFIX}{tone}"


def break_into_pinyin_syllables(text: str) -> List[Tuple[str, Optional[int]]]:
    tokenizer = PinyinTokenizer()
    r: List[Tuple[str, Optional[int]]] = []
    for word in split_preserving_ws(text):
        if word.isspace() or word == "'":
            r.append((word, None))
        else:
            for syllable in tokenizer.tokenize(word):
                r.append((syllable, tone_of_syllable(syllable)))
    return r


def tone_of_syllable(syllable: str) -> int:
    for ch in decompose_diacritics(syllable):
        tone = TONE_MARKS.get(ch)
        if tone is not None:
            return tone

    return 5


def decompose_diacritics(s: str) -> str:
    return unicodedata.normalize("NFD", s)


ws_split_rgx = lazy_re(r"([\s']+)")


def split_preserving_ws(s: str) -> List[str]:
    return ws_split_rgx.get().split(s)


TONE1_MARK = "\u0304"
TONE2_MARK = "\u0301"
TONE3_MARK = "\u030C"
# This is the wrong diacritic for third tone but I sometimes use it by mistake.
# TONE3_MARK_ALT = "\u0306"
TONE4_MARK = "\u0300"
DIARESIS = "\u0308"
TONE_MARKS = {
    TONE1_MARK: 1,
    TONE2_MARK: 2,
    TONE3_MARK: 3,
    # TONE3_MARK_ALT: 3,
    TONE4_MARK: 4,
}
DIACRITICS = {
    TONE1_MARK,
    TONE2_MARK,
    TONE3_MARK,
    # TONE3_MARK_ALT,
    TONE4_MARK,
    DIARESIS,
}

if __name__ == "__main__":
    cmd = command.Group()
    cmd.add2("add-uncolorized-fields", main_add_uncolorized_fields)
    cmd.add2("colorize", main_colorize)
    cmd.add2("replace-audio-display-text", main_replace_audio_display_text)
    command.dispatch(cmd)
