import json
import random

from app.zhongwen import ankiconnect
from iafisher.prelude import *
from lib import kgjson, llm, pgdb

# TODO(2026-10): Upgrade to 5.5 (blocked on API error):
#   To turn thinking off on this model, send "thinking": {"type": "between_tools"} instead of {"type": "disabled"}
MODEL = "claude-sonnet-5-5"


def _make_word_prompt(*, hanzi: str, translation: str) -> str:
    return f"{hanzi} '{translation}'"


WORD_PROMPT = """\
You create example sentences in Mandarin Chinese for a language learner, to be imported
into an Anki deck.

You are given a Chinese word and English translation, and you must produce two example
sentences and a question/answer exchange.

If the input is valid, then the last line of your output MUST be a JSON object with the
following fields:

- pinyin: the given word in Pinyin
- sentence1_pinyin: the first example sentence, in Pinyin
- sentence1_hanzi: the first example sentence, in characters
- sentence1_translation: the first example sentence, translated to English
- sentence2_pinyin: the second example sentence, in Pinyin
- sentence2_hanzi: the second example sentence, in characters
- sentence2_translation: the second example sentence, translated to English
- question1_pinyin: the example question, in Pinyin
- question1_hanzi: the example question, in characters
- question1_translation: the example question, translated to English
- answer1_pinyin: a random answer to the example question, in Pinyin
- answer1_hanzi: the answer in characters
- answer1_translation: the answer translated to English

If the input is serious incorrectly (e.g., 试 'to get wet'), then the last line of your
output MUST be a JSON object with a single field, `error`, containing a one-sentence
explanation of the error. If the translation has a minor inaccuracy, then you MUST proceed
with generating valid sentences.

One of the sentences should be a simple clause, while the other sentence should have
two clauses (e.g., "X, but Y" or "X, because Y", or "After X, Y" or "N said that X"
or "X, even though Y", etc.). Sentences may be declarations or commands.

The example question and answer should be single clauses. The question should not contain
the target word, while the answer must contain the target word. Exception: if the target
word is itself a question word (e.g., 什么些), then include it in the question instead of
the answer.

Use elementary to intermediate vocabulary. Choose words that complement the target
word, e.g., for "chī 'to eat'" include words related to food, cooking, or the
kitchen.

For example:

<user>
%(correct_prompt)s
</user>

<model>
{"pinyin": "chī", "sentence1_pinyin": "Wǒ méi chī wán yīnwèi wǒ bú è.", "sentence1_hanzi": "我没吃完因为我不饿。", "sentence1_translation": "I didn't finish eating because I wasn't hungry.", "sentence2_pinyin": "Wǒ chī píngguǒ.", "sentence2_hanzi": "我吃苹果。", "sentence2_translation": "I eat an apple.", "question1_pinyin": "Nǐ wǔfàn shì shénme?", "question1_hanzi": "你午饭是什么?", "question1_translation": "What did you have for lunch?", "answer1_pinyin": "Wǒ chī le jīròu hé mǐfàn.", "answer1_hanzi": "我吃了鸡肉和米饭。", "answer1_translation": "I ate chicken and rice."}
</model>

<user>
%(incorrect_prompt)s
</user>

<model>
{"error": "The word '试' means 'to try', not 'to get wet', which is '湿'."}
</model>
""" % dict(
    correct_prompt=_make_word_prompt(hanzi="吃", translation="to eat"),
    incorrect_prompt=_make_word_prompt(hanzi="试", translation="to get wet"),
)


@dataclass
class LLMWordNote(kgjson.Base):
    pinyin: str
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


def generate_word_note(*, hanzi: str, translation: str) -> LLMWordNote:
    with pgdb.connect() as db:
        LOG.info("start: generating word note (%s)", hanzi)
        response = llm.oneshot(
            db,
            _make_word_prompt(hanzi=hanzi, translation=translation),
            model=MODEL,
            system_prompt=WORD_PROMPT,
            app_name=_app_name("word"),
            options=llm.InferenceOptions.fast(),
        )
        LOG.info("end:   generating word note (%s)", hanzi)

        try:
            last_line_json = _parse_last_line_as_json(response)
            return LLMWordNote.deserialize(last_line_json)
        except Exception as e:
            raise KgError(
                "I was unable to parse the last line of the LLM response's as JSON.",
                error=e,
                text=response.output_text,
            )


IMAGE_GENERATION_PROMPT = """\
You generate images for a Chinese-language learner to illustrate example sentences
in their Anki deck.

The image should suggest the sentence but does not need to capture every detail of it.
It is enough to depict a general scene or scenario where or about which the sentence
might be uttered.

For instance, the sentence "Because the password was too simple, his account got hacked"
could be illustrated by a person sitting at a computer.

Draw the images in a classical Chinese illustrated storybook style. The setting should be
China. Default to a historical setting unless incompatible with the prompt (e.g., if the
prompt describes computers).
"""


def generate_image(sentence: str) -> bytes:
    prompt = IMAGE_GENERATION_PROMPT + "\n\nThe sentence to illustrate: " + sentence
    return llm.imgen.generate_image(prompt, quality="low", format_="jpeg")


def _parse_last_line_as_json(response: llm.ModelResponse) -> StrDict:
    text = response.output_text
    last_line = text.splitlines()[-1]
    last_line_json = json.loads(last_line)
    error = last_line_json.get("error")
    if error:
        raise KgError("The LLM flagged an error in the request.", error=error)

    return last_line_json


# The prompt used to generate the example sentences.
#
# TODO: Originally had this but it was too hard for my level:
#
#     Use a variety of sentence lengths and structures, e.g., multiple clauses,
#     comparisons, time expressions, possibility, obligation.
#
# Restore this when I am ready.
DUI_BU_DUI_GENERATION_PROMPT = """\
You create example sentences in Mandarin Chinese for a game called 'Duì bu duì'.

In the game, the tutor says a sentence which is true or false, and the student
responds either 'duì' or 'bu duì'.

You are given a list of words. For each word, you must write a sentence in
characters that uses the word and is either true or false without further context.

Use elementary to intermediate vocabulary. Choose words that complement the target
word rather than generic words, e.g., for "吃" include words related to food, cooking,
or the kitchen.

Write simple declarative sentences.

For example:

<user>
猫
大学
</user>

<model>
猫通常比狗大。
在大学可以学习计算机科学。
</model>
"""


# The prompt used to actually play the game. This is never fed to an LLM in code,
# rather, the user copy-pastes it into Live Chat mode in, e.g., the ChatGPT app.
DUI_BU_DUI_GAME_PROMPT_PRELUDE = """\
You are a tutor for an English speaker learning Mandarin Chinese.

In this session, you will be playing a game called 'Duì bu duì'.

You are given a list of sentences. You read the sentences one at a time, and
the student responds either 'duì' or 'bu duì'. Read each sentence twice before
letting the student respond. Confirm the student's answer or correct them:
"你答对了。" or "你答错了,这句话是(对/错)的。" Then move on to the next sentence without
waiting for the student to respond.

You can repeat the sentence again if the student asks you to.

Respond to this message with '好的'. Start playing the game on the student's cue.

Do not say anything other than the sentences you are given.

After the last sentence, say "游戏结束了。"
"""


def generate_dui_bu_dui_prompt(n: int) -> str:
    notes = ankiconnect.search_notes(f'"note:{ankiconnect.WORD_NOTE_TYPE}"')
    random.shuffle(notes)
    selected_words = [note.get_field_value("hanzi") for note in notes[:n]]

    with pgdb.connect() as db:
        LOG.info("start: generating prompt")
        response = llm.oneshot(
            db,
            "\n".join(selected_words),
            model=MODEL,
            system_prompt=DUI_BU_DUI_GENERATION_PROMPT,
            app_name=_app_name("dui_bu_dui"),
            options=llm.InferenceOptions.fast(),
        )
        LOG.info("end:   generating prompt")
        return response.output_text


def _app_name(subsystem: str) -> str:
    return f"zhongwen::{subsystem}"


STORY_GENERATION_PROMPT = """\
You write texts for an English learner of Mandarin Chinese to translate into
Mandarin.

You are given a list of vocabulary items and a topic, and you should construct
a short text (around 10 sentences) in English that uses these vocabulary items.
Pick 3 new related vocab items that are not in the set to include in the story,
and provide definitions below. Do not output any extra commentary besides the
text and the new words.

Use simplified characters.

<user>
['吃 to eat', '因为 because', '苹果 apple', <more vocabulary omitted>]

Topic: daily routine
</user>

<model>
I ate at breakfast at 8 am this morning. <more sentences omitted>

New words:
- 菠萝 (bōluó) 'pineapple'
- <2 more words omitted>
</model>
"""


def generate_text(topic: str) -> str:
    word_notes = ankiconnect.search_notes('"note:Chinese 2026 word"')
    words = [
        note.get_field_value("hanzi") + " " + note.get_field_value("translation")
        for note in word_notes
    ]

    assert len(words) > 0

    with pgdb.connect() as db:
        LOG.info("start: generating prompt")
        response = llm.oneshot(
            db,
            json.dumps(words) + f"\n\nTopic: {topic}",
            model=MODEL,
            system_prompt=STORY_GENERATION_PROMPT,
            app_name=_app_name("story"),
            options=llm.InferenceOptions.normal(),
        )
        LOG.info("end:   generating prompt")
        return response.output_text


# TODO(2026-10): Generate the field documentation in the prompts directly from the
# Python classes using type annotations on each field.


CHARACTER_PROMPT = """\
You create examples of Mandarin Chinese characters for a language learner, to be imported
into an Anki deck.

You are given a character, and you must produce the pinyin and two example words.

If the input is valid, then the last line of your output MUST be a JSON object with the
following fields:

- pinyin: the given character in Pinyin (if multiple options, choose the most common one)
- example1_hanzi: the first example word, in simplified characters
- example1_pinyin: the first example word, in Pinyin
- example1_translation: the first example word, translated to English
- example2_hanzi: the second example word, in simplified characters
- example2_pinyin: the second example word, in Pinyin
- example2_translation: the second example word, translated to English

If the input is invalid (i.e., it is not a Chinese character), then the last line of your
output MUST be a JSON object with a single field, `error`, containing a one-sentence
explanation of the error.

Do not give an error for any reason other than the input not being a Chinese character.

Do not use obscure, technical, or archaic vocabulary for the example words.

For example:

<user>
店
</user>

<model>
{"pinyin": "diàn", "example1_hanzi": "商店", "example1_pinyin": "shāngdiàn", "example1_translation": "store", "example2_hanzi": 酒店", "example2_pinyin": "jiǔdiàn", "example2_translation": "hotel"}
</model>

<user>
tī
</user>

<model>
{"error": "The input was not a Chinese character."}
</model>
"""


@dataclass
class LLMCharacterNote(kgjson.Base):
    pinyin: str
    example1_hanzi: str
    example1_pinyin: str
    example1_translation: str
    example2_hanzi: str
    example2_pinyin: str
    example2_translation: str


def generate_character_note(hanzi: str) -> LLMCharacterNote:
    with pgdb.connect() as db:
        LOG.info("start: generating character note (%s)", hanzi)
        response = llm.oneshot(
            db,
            hanzi,
            model=MODEL,
            system_prompt=CHARACTER_PROMPT,
            app_name=_app_name("character"),
            options=llm.InferenceOptions.fast(),
        )
        LOG.info("end:   generating character note (%s)", hanzi)

        try:
            last_line_json = _parse_last_line_as_json(response)
            return LLMCharacterNote.deserialize(last_line_json)
        except Exception as e:
            raise KgError(
                "I was unable to parse the last line of the LLM response's as JSON.",
                error=e,
                text=response.output_text,
            )
