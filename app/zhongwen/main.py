import asyncio
import traceback

import edge_tts

from iafisher.prelude import *
from iafisher.scripting import q
from lib import command, kghttp, llm, pgdb


# Anki copies the media files into its own directory (~/Library/Application Support/Anki2/User 1/collection.media)
# so we could use a temporary directory, but it's useful to save them permanently in case the Anki
# upload fails.
ANKI_MEDIA_DIRECTORY = pathlib.Path.home() / "Documents" / "AnkiMedia"
ANKI_DECK = "Chinese 2026"
ANKI_MODEL = "Chinese audio"


def main_anki_upload(
    *,
    pinyin: str,
    translation: str,
    audio_word_path: pathlib.Path,
    audio_sentence_path: pathlib.Path,
) -> None:
    pinyin_word = _extract_word(pinyin)
    word_translation = _extract_word(translation)
    _upload_to_anki(
        pinyin_word=pinyin_word,
        word_translation=word_translation,
        pinyin_sentence=pinyin,
        sentence_translation=translation,
        audio_word_path=audio_word_path,
        audio_sentence_path=audio_sentence_path,
    )


def main_tts(*, pinyin: str, translation: str, overwrite: bool) -> None:
    pinyin_word = _extract_word(pinyin)
    word_translation = _extract_word(translation)
    h = sha256(pinyin)[:12]
    pinyin_word_for_filename = pinyin_word.replace(" ", "-")
    audio_word_path = ANKI_MEDIA_DIRECTORY / f"{pinyin_word_for_filename}-{h}-word.mp3"
    audio_sentence_path = (
        ANKI_MEDIA_DIRECTORY / f"{pinyin_word_for_filename}-{h}-sentence.mp3"
    )
    if not overwrite:
        _raise_if_existing(audio_word_path)
        _raise_if_existing(audio_sentence_path)

    hanzi = _pinyin_to_hanzi(pinyin)
    hanzi_word = _extract_word(hanzi)
    LOG.info("transliterated: %s", hanzi)
    asyncio.run(_save_mp3(hanzi_word, audio_word_path))
    LOG.info("wrote to file: %s", audio_word_path)
    asyncio.run(_save_mp3(hanzi, audio_sentence_path))
    LOG.info("wrote to file: %s", audio_sentence_path)

    try:
        _upload_to_anki(
            pinyin_word=pinyin_word,
            word_translation=word_translation,
            pinyin_sentence=pinyin,
            sentence_translation=translation,
            audio_word_path=audio_word_path,
            audio_sentence_path=audio_sentence_path,
        )
    except Exception:
        eprint(traceback.format_exc())
        eprint(
            "\n\nFailed to upload to Anki."
            f" Re-run with `anki-upload -translation {q(translation)}"
            f" -pinyin {q(pinyin)}"
            f" -audio-word-path {q(audio_word_path.as_posix())}"
            f" -audio-sentence-path {q(audio_sentence_path.as_posix())}`."
        )
        sys.exit(1)


def _raise_if_existing(path: pathlib.Path) -> None:
    if path.exists():
        raise KgError(
            "I will not overwrite an existing file unless the -overwrite flag is passed.",
            path=path,
        )


bracketed_word_rgx = lazy_re(r"^[^[]+\[([^\]]+)\].+$")


def _extract_word(sentence: str) -> str:
    m = bracketed_word_rgx.get().match(sentence)
    if m is None:
        raise KgError(
            "The sentence does not contain a bracketed word.", sentence=sentence
        )
    return m.group(1)


PINYIN_TO_HANZI_SYSTEM_PROMPT = """\
You transliterate Chinese sentences from Pinyin to Chinese characters.

If ambiguous, make your best guess. Assume elementary vocabulary for a language
learner.

Retain all punctuation, including square brackets.

Respond with just the Chinese characters. Do not output anything else.
"""


def _pinyin_to_hanzi(pinyin: str) -> str:
    with pgdb.connect() as db:
        response = llm.oneshot(
            db,
            pinyin,
            model=llm.ANY_FAST_MODEL,
            system_prompt=PINYIN_TO_HANZI_SYSTEM_PROMPT,
            app_name="zhongwen::pinyin",
            options=llm.InferenceOptions.fast(),
        )
        return response.output_text


async def _save_mp3(hanzi: str, path: pathlib.Path) -> None:
    voice = "zh-CN-XiaoxiaoNeural"
    LOG.info("start: generating audio: %s", hanzi)
    await edge_tts.Communicate(hanzi, voice).save(path.as_posix())
    LOG.info("end:   generating audio: %s", hanzi)


def _upload_to_anki(
    *,
    pinyin_word: str,
    word_translation: str,
    pinyin_sentence: str,
    sentence_translation: str,
    audio_word_path: pathlib.Path,
    audio_sentence_path: pathlib.Path,
) -> None:
    def _audio(path: pathlib.Path) -> StrDict:
        return {"path": path.as_posix(), "filename": path.name, "fields": ["Front"]}

    payload = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": {
                "deckName": ANKI_DECK,
                "modelName": ANKI_MODEL,
                "fields": {
                    "Front": "🔊 ",
                    "Word Pinyin": pinyin_word,
                    "Word translation": word_translation,
                    "Sentence Pinyin": pinyin_sentence,
                    "Sentence translation": sentence_translation,
                },
                "options": {"allowDuplicate": False},
                "audio": [
                    _audio(audio_word_path),
                    _audio(audio_sentence_path),
                    _audio(audio_word_path),
                ],
            }
        },
    }

    LOG.info("start: uploading to Anki")
    http_response = kghttp.post("http://127.0.0.1:8765", json=payload)
    LOG.info("end:   uploading to Anki")

    json_response = http_response.json()
    if json_response["result"] is None:
        raise KgError("AnkiConnect response missing", error=json_response.get("error"))


cmd = command.Group()
cmd.add2(
    "anki-upload",
    main_anki_upload,
    less_logging=False,
    help="Add an existing recording to my Anki deck.",
)
cmd.add2(
    "tts",
    main_tts,
    less_logging=False,
    help="Synthesize an audio recording using text-to-speech (TTS) and add it to my Anki deck.",
)

if __name__ == "__main__":
    command.dispatch(cmd)
