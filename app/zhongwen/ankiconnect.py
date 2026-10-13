import base64
from abc import ABC, abstractmethod

from iafisher.prelude import *
from lib import kghttp, kgjson

ANKI_DECK = "Chinese 2026"
CHARACTER_NOTE_TYPE = "Chinese 2026 character"
WORD_NOTE_TYPE = "Chinese 2026 word"


class AnkiNote(ABC):
    @abstractmethod
    def to_params(self, deck: str) -> StrDict:
        pass


# AnkiConnect API documentation:
# https://github.com/amikey/anki-connect#application-interface-for-developers


def upload_note(note: AnkiNote) -> None:
    _submit("addNote", note.to_params(ANKI_DECK), expect_result=True)


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

    def get_field_value(self, fieldname: str) -> str:
        field = self.fields.get(fieldname)
        return field.value if field is not None else ""

    def has_field_value(self, fieldname: str, value: str) -> bool:
        return self.get_field_value(fieldname) == value


def update_note_fields(note: NoteInfo) -> None:
    fields = {fieldname: field.value for fieldname, field in note.fields.items()}
    _submit(
        "updateNoteFields",
        {"note": {"id": note.note_id, "fields": fields}},
        expect_result=False,
    )


def search_notes(query: str) -> List[NoteInfo]:
    query = f'"deck:{ANKI_DECK}" {query}'
    note_ids = _submit("findNotes", dict(query=query), expect_result=True)
    return fetch_notes_by_id(note_ids)


@dataclass
class CardInfo(kgjson.Base):
    card_id: int
    answer: str
    question: str
    interval: int
    note: int
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


def search_cards(query: str) -> List[CardInfo]:
    query = f'"deck:{ANKI_DECK}" {query}'
    card_ids = _submit("findCards", dict(query=query), expect_result=True)
    card_info_dicts = _submit("cardsInfo", dict(cards=card_ids), expect_result=True)
    return [CardInfo.deserialize(d, camel_case=True) for d in card_info_dicts]


def fetch_notes_by_id(note_ids: List[int]) -> List[NoteInfo]:
    note_info_dicts = _submit("notesInfo", dict(notes=note_ids), expect_result=True)
    return [NoteInfo.deserialize(d, camel_case=True) for d in note_info_dicts]


def store_media_file(filename: str, file_bytes: bytes) -> None:
    _submit(
        "storeMediaFile",
        dict(filename=filename, data=base64.b64encode(file_bytes).decode("ascii")),
        expect_result=False,
    )


def _submit(action: str, params: StrDict, *, expect_result: bool) -> Any:
    payload = {"action": action, "version": 6, "params": params}

    LOG.info("start: querying Anki (%s)", action)
    http_response = kghttp.post("http://127.0.0.1:8765", json=payload)
    LOG.info("end:   querying Anki (%s)", action)

    json_response = http_response.json()
    result = json_response.get("result")
    if expect_result and result is None:
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
    question1_audio: pathlib.Path
    answer1_audio: pathlib.Path
    pinyin: str
    pinyin_colorized: str
    hanzi: str
    hanzi_colorized: str
    translation: str
    sentence1_pinyin: str
    sentence1_hanzi: str
    sentence1_translation: str
    sentence2_pinyin: str
    sentence2_hanzi: str
    sentence2_translation: str
    question1_pinyin: str
    question1_hanzi: str
    question1_translation: str
    answer1_pinyin: str
    answer1_hanzi: str
    answer1_translation: str
    sentence1_image: Optional[str] = None
    sentence2_image: Optional[str] = None
    question1_image: Optional[str] = None

    @override
    def to_params(self, deck: str) -> StrDict:
        return _add_note_params(
            deck,
            WORD_NOTE_TYPE,
            _replace_audio_paths(dataclasses.asdict(self)),
            [
                ("word_audio", self.word_audio),
                ("sentence1_audio", self.sentence1_audio),
                ("sentence2_audio", self.sentence2_audio),
                ("question1_audio", self.question1_audio),
                ("answer1_audio", self.answer1_audio),
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


def _replace_audio_paths(d: StrDict) -> StrDict:
    return {
        k: "[声]" if isinstance(v, pathlib.Path) and "audio" in k else v
        for k, v in d.items()
    }


def _audio_param(field: str, path: pathlib.Path) -> StrDict:
    return {"path": path.as_posix(), "filename": path.name, "fields": [field]}


@dataclass
class AnkiCharacterNote(AnkiNote):
    hanzi: str
    pinyin: str
    example1_hanzi: str
    example1_pinyin: str
    example1_translation: str
    example2_hanzi: str
    example2_pinyin: str
    example2_translation: str

    @override
    def to_params(self, deck: str) -> StrDict:
        return _add_note_params(
            deck, CHARACTER_NOTE_TYPE, dataclasses.asdict(self), audio=[]
        )
