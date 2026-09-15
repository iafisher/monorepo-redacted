import base64
import os

from app.zhongwen import ankiconnect, llmgen, tts
from iafisher import timehelper
from iafisher.prelude import *
from lib import command


# Anki copies the media files into its own directory (~/Library/Application Support/Anki2/User 1/collection.media)
# so we could use a temporary directory, but it's useful to save them permanently in case the Anki
# upload fails.
MEDIA_DIRECTORY = pathlib.Path.home() / "Documents" / "AnkiMedia"


def main_anki_question(question: str) -> None:
    llm_question_note = llmgen.generate_question_note(question)

    today = timehelper.today()
    hsh = sha256(question)[:8]
    d = MEDIA_DIRECTORY / f"question-{today}-{sha256(hsh)}"
    d.mkdir()
    LOG.info("saving MP3 files to %s", d)

    question_audio = d / "question.mp3"
    tts.save_mp3(llm_question_note.question_hanzi, question_audio)
    answer_audio = d / "answer.mp3"
    tts.save_mp3(llm_question_note.answer_hanzi, answer_audio)

    note = ankiconnect.AnkiQuestionNote(
        question_audio=question_audio,
        question_pinyin=llm_question_note.question_pinyin,
        question_hanzi=llm_question_note.question_hanzi,
        question_translation=question,
        answer_audio=answer_audio,
        answer_pinyin=llm_question_note.answer_pinyin,
        answer_hanzi=llm_question_note.answer_hanzi,
        answer_translation=llm_question_note.answer_translation,
    )
    ankiconnect.upload_note(note)

    print()
    print(f"{note.question_hanzi} ({note.question_pinyin}) – '{question}'")
    print()
    print(f"{note.answer_hanzi} ({note.answer_pinyin} - '{note.answer_translation}')")


def main_anki_word(
    *, pinyin: str, translation: str, skip_duplicate_check: bool
) -> None:
    if not skip_duplicate_check:
        _ensure_not_already_in_deck(pinyin)

    llm_word_note = llmgen.generate_word_note(pinyin=pinyin, translation=translation)

    today = timehelper.today()
    d = MEDIA_DIRECTORY / f"{pinyin.replace(' ', '-')}-{today}-{_four_random_chars()}"
    d.mkdir()
    LOG.info("saving MP3 files to %s", d)

    word_audio = d / "word.mp3"
    tts.save_mp3(llm_word_note.hanzi, word_audio)
    sentence1_audio = d / "sentence1.mp3"
    tts.save_mp3(llm_word_note.sentence1_hanzi, sentence1_audio)
    sentence2_audio = d / "sentence2.mp3"
    tts.save_mp3(llm_word_note.sentence2_hanzi, sentence2_audio)
    sentence3_audio = d / "sentence3.mp3"
    tts.save_mp3(llm_word_note.sentence3_hanzi, sentence3_audio)

    note = ankiconnect.AnkiWordNote(
        word_audio=word_audio,
        sentence1_audio=sentence1_audio,
        sentence2_audio=sentence2_audio,
        sentence3_audio=sentence3_audio,
        pinyin=pinyin,
        hanzi=llm_word_note.hanzi,
        translation=translation,
        sentence1_pinyin=llm_word_note.sentence1_pinyin,
        sentence1_hanzi=llm_word_note.sentence1_hanzi,
        sentence1_translation=llm_word_note.sentence1_translation,
        sentence2_pinyin=llm_word_note.sentence2_pinyin,
        sentence2_hanzi=llm_word_note.sentence2_hanzi,
        sentence2_translation=llm_word_note.sentence2_translation,
        sentence3_pinyin=llm_word_note.sentence3_pinyin,
        sentence3_hanzi=llm_word_note.sentence3_hanzi,
        sentence3_translation=llm_word_note.sentence3_translation,
    )
    ankiconnect.upload_note(note)

    print()
    print(f"{note.hanzi} ({pinyin}) – '{translation}'")
    print()
    print(f"{note.sentence1_hanzi} ({note.sentence1_pinyin})")
    print(note.sentence1_translation)
    print()
    print(f"{note.sentence2_hanzi} ({note.sentence2_pinyin})")
    print(note.sentence2_translation)
    print()
    print(f"{note.sentence3_hanzi} ({note.sentence3_pinyin})")
    print(note.sentence3_translation)


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


def main_test_check_word(pinyin: str) -> None:
    _ensure_not_already_in_deck(pinyin)
    print("OK.")


def _ensure_not_already_in_deck(pinyin: str) -> None:
    matching_notes = ankiconnect.search_notes(pinyin)
    existing_notes = [n for n in matching_notes if n.has_field_value("pinyin", pinyin)]
    if len(existing_notes) != 0:
        raise KgError(
            "There is already a word with the same pinyin in the Anki deck."
            " If the new word uses different characters, then use a flag to override this check.",
            pinyin=pinyin,
            existing_notes=existing_notes,
        )


def _four_random_chars() -> str:
    return base64.urlsafe_b64encode(os.urandom(3)).decode("utf8")


cmd = command.Group()

anki_cmd = command.Group(help="Commands for interacting with my Anki deck.")
cmd.add("anki", anki_cmd)
anki_cmd.add2("question", main_anki_question, less_logging=False)
anki_cmd.add2("word", main_anki_word, less_logging=False)

games_cmd = command.Group(help="Commands for playing language-learning games.")
cmd.add("games", games_cmd)
games_cmd.add2("dui-bu-dui", main_games_dui_bu_dui)

test_cmd = command.Group(help="Test commands for development.")
cmd.add("test", test_cmd)
test_cmd.add2("check-word", main_test_check_word)

if __name__ == "__main__":
    command.dispatch(cmd)
