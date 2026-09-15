from abc import ABC, abstractmethod

from iafisher.prelude import *
from lib import kghttp, kgjson

ANKI_DECK = "Chinese 2026"
WORD_NOTE_TYPE = "Chinese 2026 word"
QUESTION_NOTE_TYPE = "Chinese 2026 question"


class AnkiNote(ABC):
    @abstractmethod
    def to_params(self, deck: str) -> StrDict:
        pass


# AnkiConnect API documentation:
# https://github.com/amikey/anki-connect#application-interface-for-developers


def upload_note(note: AnkiNote) -> None:
    _submit("addNote", note.to_params(ANKI_DECK))


@dataclass
class NoteField(kgjson.Base):
    value: str
    order: int


@dataclass
class NoteInfo(kgjson.Base):
    note_id: int
    fields: Dict[str, NoteField]
    tags: List[str]
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)

    def has_field_value(self, fieldname: str, value: str) -> bool:
        field = self.fields.get(fieldname)
        return field is not None and field.value == value


def search_notes(query: str) -> List[NoteInfo]:
    query = f'"deck:{ANKI_DECK}" {query}'
    note_ids = _submit("findNotes", dict(query=query))
    note_info_dicts = _submit("notesInfo", dict(notes=note_ids))
    return [NoteInfo.deserialize(d, camel_case=True) for d in note_info_dicts]


def _submit(action: str, params: StrDict) -> Any:
    payload = {"action": action, "version": 6, "params": params}

    LOG.info("start: querying Anki (%s)", action)
    http_response = kghttp.post("http://127.0.0.1:8765", json=payload)
    LOG.info("end:   querying Anki (%s)", action)

    json_response = http_response.json()
    result = json_response.get("result")
    if result is None:
        raise KgError(
            "AnkiConnect response missing",
            error=json_response.get("error"),
            payload=payload,
        )

    return result


@dataclass
class AnkiWordNote(AnkiNote):
    # Front: audio of word, then audio of sentence

    word_audio: pathlib.Path
    sentence1_audio: pathlib.Path
    sentence2_audio: pathlib.Path
    sentence3_audio: pathlib.Path
    pinyin: str
    hanzi: str
    translation: str
    sentence1_pinyin: str
    sentence1_hanzi: str
    sentence1_translation: str
    sentence2_pinyin: str
    sentence2_hanzi: str
    sentence2_translation: str
    sentence3_pinyin: str
    sentence3_hanzi: str
    sentence3_translation: str

    @override
    def to_params(self, deck: str) -> StrDict:
        return _add_note_params(
            deck,
            WORD_NOTE_TYPE,
            _replace_paths(dataclasses.asdict(self)),
            [
                ("word_audio", self.word_audio),
                ("sentence1_audio", self.sentence1_audio),
                ("sentence2_audio", self.sentence2_audio),
                ("sentence3_audio", self.sentence3_audio),
            ],
        )


@dataclass
class AnkiQuestionNote(AnkiNote):
    # Front: audio of question, plus English answer

    question_audio: pathlib.Path
    question_pinyin: str
    question_hanzi: str
    question_translation: str
    answer_audio: pathlib.Path
    answer_pinyin: str
    answer_hanzi: str
    answer_translation: str

    @override
    def to_params(self, deck: str) -> StrDict:
        return _add_note_params(
            deck,
            QUESTION_NOTE_TYPE,
            _replace_paths(dataclasses.asdict(self)),
            [
                ("question_audio", self.question_audio),
                ("answer_audio", self.answer_audio),
            ],
        )


def _add_note_params(
    deck: str, model: str, fields: StrDict, audio: List[Tuple[str, pathlib.Path]]
) -> StrDict:
    return {
        "note": {
            "deckName": deck,
            "modelName": model,
            "fields": fields,
            "options": {"allowDuplicate": False},
            "audio": [_audio_param(field, a) for field, a in audio],
        }
    }


def _replace_paths(d: StrDict) -> StrDict:
    return {k: "[audio]" if isinstance(v, pathlib.Path) else v for k, v in d.items()}


def _audio_param(field: str, path: pathlib.Path) -> StrDict:
    return {"path": path.as_posix(), "filename": path.name, "fields": [field]}
