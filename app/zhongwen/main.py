import base64
import os

from app.zhongwen import ankiconnect, colorize, llmgen, tts
from iafisher import timehelper
from iafisher.prelude import *
from lib import command


# Anki copies the media files into its own directory (~/Library/Application Support/Anki2/User 1/collection.media)
# so we could use a temporary directory, but it's useful to save them permanently in case the Anki
# upload fails.
MEDIA_DIRECTORY = pathlib.Path.home() / "Documents" / "AnkiMedia"


def main_anki_character(hanzi: str) -> None:
    # TODO(2026-10): Check if already in deck.
    llm_character_note = llmgen.generate_character_note(hanzi)
    note = ankiconnect.AnkiCharacterNote(
        hanzi=hanzi,
        pinyin=llm_character_note.pinyin,
        example1_hanzi=llm_character_note.example1_hanzi,
        example1_pinyin=llm_character_note.example1_pinyin,
        example1_translation=llm_character_note.example1_translation,
        example2_pinyin=llm_character_note.example2_pinyin,
        example2_hanzi=llm_character_note.example2_hanzi,
        example2_translation=llm_character_note.example2_translation,
    )
    ankiconnect.upload_note(note)

    print()
    print(f"{hanzi} ({note.pinyin})")
    print()
    print(
        f"{note.example1_hanzi} ({note.example1_pinyin}) '{note.example1_translation}'"
    )
    print(
        f"{note.example2_hanzi} ({note.example2_pinyin}) '{note.example2_translation}'"
    )


def main_anki_word(hanzi: str, translation: str, *, image: bool) -> None:
    _ensure_not_already_in_deck(hanzi)

    llm_word_note = llmgen.generate_word_note(hanzi=hanzi, translation=translation)

    today = timehelper.today()
    d = MEDIA_DIRECTORY / f"{hanzi.replace(' ', '-')}-{today}-{_four_random_chars()}"
    d.mkdir()
    LOG.info("saving MP3 files to %s", d)

    word_audio = d / "word.mp3"
    tts.save_mp3(hanzi, word_audio)
    sentence1_audio = d / "sentence1.mp3"
    tts.save_mp3(llm_word_note.sentence1_hanzi, sentence1_audio)
    sentence2_audio = d / "sentence2.mp3"
    tts.save_mp3(llm_word_note.sentence2_hanzi, sentence2_audio)
    question1_audio = d / "question1.mp3"
    tts.save_mp3(llm_word_note.question1_hanzi, question1_audio)
    answer1_audio = d / "answer1.mp3"
    tts.save_mp3(llm_word_note.answer1_hanzi, answer1_audio)

    # TODO(2026-10): Generate images in parallel with audio.
    if image:
        sentence1_image_bytes = llmgen.generate_image(
            llm_word_note.sentence1_translation
        )
        sentence2_image_bytes = llmgen.generate_image(
            llm_word_note.sentence2_translation
        )
        question1_image_bytes = llmgen.generate_image(
            f"{llm_word_note.question1_translation} {llm_word_note.answer1_translation}"
        )

        sentence1_image = f"{hanzi}_sentence1.jpg"
        sentence2_image = f"{hanzi}_sentence2.jpg"
        question1_image = f"{hanzi}_question1.jpg"

        ankiconnect.store_media_file(sentence1_image, sentence1_image_bytes)
        ankiconnect.store_media_file(sentence2_image, sentence2_image_bytes)
        ankiconnect.store_media_file(question1_image, question1_image_bytes)
    else:
        sentence1_image = None
        sentence2_image = None
        question1_image = None

    pinyin = llm_word_note.pinyin
    colorized_pinyin, colorized_hanzi = colorize.colorize_pinyin_hanzi(pinyin, hanzi)
    note = ankiconnect.AnkiWordNote(
        word_audio=word_audio,
        sentence1_audio=sentence1_audio,
        sentence2_audio=sentence2_audio,
        question1_audio=question1_audio,
        answer1_audio=answer1_audio,
        pinyin=pinyin,
        pinyin_colorized=colorized_pinyin,
        hanzi=hanzi,
        hanzi_colorized=colorized_hanzi,
        translation=translation,
        sentence1_pinyin=llm_word_note.sentence1_pinyin,
        sentence1_hanzi=llm_word_note.sentence1_hanzi,
        sentence1_translation=llm_word_note.sentence1_translation,
        sentence2_pinyin=llm_word_note.sentence2_pinyin,
        sentence2_hanzi=llm_word_note.sentence2_hanzi,
        sentence2_translation=llm_word_note.sentence2_translation,
        question1_pinyin=llm_word_note.question1_pinyin,
        question1_hanzi=llm_word_note.question1_hanzi,
        question1_translation=llm_word_note.question1_translation,
        answer1_pinyin=llm_word_note.answer1_pinyin,
        answer1_hanzi=llm_word_note.answer1_hanzi,
        answer1_translation=llm_word_note.answer1_translation,
        sentence1_image=sentence1_image,
        sentence2_image=sentence2_image,
        question1_image=question1_image,
    )
    ankiconnect.upload_note(note)

    print()
    print(f"{note.hanzi} ({note.pinyin}) – '{note.translation}'")
    print()
    print(f"{note.sentence1_hanzi} ({note.sentence1_pinyin})")
    print(note.sentence1_translation)
    print()
    print(f"{note.sentence2_hanzi} ({note.sentence2_pinyin})")
    print(note.sentence2_translation)
    print()
    print(f"{note.question1_hanzi} ({note.question1_pinyin})")
    print(note.question1_translation)
    print()
    print(f"{note.answer1_hanzi} ({note.answer1_pinyin})")
    print(note.answer1_translation)


def main_anki_vocab(*, cutoff_days: int = 10, only_print_count: bool):
    cards = ankiconnect.search_cards(f'"note:{ankiconnect.WORD_NOTE_TYPE}"')
    note_ids = {c.note for c in cards if c.interval >= cutoff_days}
    if only_print_count:
        print(len(note_ids))
    else:
        notes = ankiconnect.fetch_notes_by_id(list(note_ids))
        print(
            ", ".join(
                f"{n.fields['hanzi'].value} '{n.fields['translation'].value}'"
                for n in notes
            )
        )


"""
- Anki practice
- Watch Street Talk video: first watch with only character subtitles, then watch with character + pinyin subtitles, then watch again and repeat each sentence
- Live chat games
    - Duì bu duì: Tutor says a sentence, I say duì or bu duì
    - Guess the word: Random noun picked, tutor describes in 2 sentences, I guess the word
"""


def main_games_dui_bu_dui(*, n: int = 8) -> None:
    sentences = llmgen.generate_dui_bu_dui_prompt(n)
    prompt = llmgen.DUI_BU_DUI_GAME_PROMPT_PRELUDE + "\n\n" + sentences
    print(prompt)
    print()
    print("---")
    print()
    print("Copy-paste the above into Live Chat mode to play the game 'Duì bu duì'.")


def main_games_translate_text(*, topic: str) -> None:
    print(llmgen.generate_text(topic))


def main_test_check_word(hanzi: str) -> None:
    _ensure_not_already_in_deck(hanzi)
    print("OK.")


def main_test_llmgen(hanzi: str, translation: str) -> None:
    llm_word_note = llmgen.generate_word_note(hanzi=hanzi, translation=translation)
    print(llm_word_note)


def _ensure_not_already_in_deck(hanzi: str) -> None:
    matching_notes = ankiconnect.search_notes(
        f'"note:{ankiconnect.WORD_NOTE_TYPE}" "{hanzi}"'
    )
    existing_notes = [n for n in matching_notes if n.has_field_value("hanzi", hanzi)]
    if len(existing_notes) != 0:
        raise KgError(
            "There is already a word with the same characters in the Anki deck.",
            hanzi=hanzi,
            existing_notes=existing_notes,
        )


def _four_random_chars() -> str:
    return base64.urlsafe_b64encode(os.urandom(3)).decode("utf8")


cmd = command.Group()

anki_cmd = command.Group(help="Commands for interacting with my Anki deck.")
cmd.add("anki", anki_cmd)
anki_cmd.add2(
    "character",
    main_anki_character,
    less_logging=False,
    help="Create an Anki note for a character.",
)
anki_cmd.add2(
    "word",
    main_anki_word,
    less_logging=False,
    help="Create an Anki note for a word and example sentences.",
)
anki_cmd.add2(
    "vocab", main_anki_vocab, help="Print my learned words from my Anki deck."
)

games_cmd = command.Group(help="Commands for playing language-learning games.")
cmd.add("games", games_cmd)
games_cmd.add2("dui-bu-dui", main_games_dui_bu_dui)
games_cmd.add2(
    "translate-text",
    main_games_translate_text,
    help="Generate a text to translate to Chinese.",
)

test_cmd = command.Group(help="Test commands for development.")
cmd.add("test", test_cmd)
test_cmd.add2("check-word", main_test_check_word)
test_cmd.add2("llmgen", main_test_llmgen)


if __name__ == "__main__":
    command.dispatch(cmd)
