import json
import random

from app.zhongwen import ankiconnect
from iafisher.prelude import *
from lib import kgjson, llm, pgdb

MODEL = "sonnet"


def _make_word_prompt(*, pinyin: str, translation: str) -> str:
    return f"{pinyin} '{translation}'"


WORD_PROMPT = """\
You create example sentences in Mandarin Chinese for a language learner.

You are given a word and English translation, and you must produce two example sentences
and a question/answer exchange.

If the input is valid, then the last line of your output MUST be a JSON object with the
following fields:

- hanzi: the given word in simplified characters
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

If the input is invalid (incorrect pinyin or incorrect translation), then the last line
of your output MUST be a JSON object with a single field, `error`, containing a one-sentence
explanation of the error. If the pinyin is incorrect, you must give an error. If the
translation is seriously incorrect, you must give an error. If the translation has a minor
inaccuracy, then proceed, generating valid sentences.

Do not give an error for pinyin that is ambiguous if the translation correctly identifies
one of the possible characters. For example, if the user supplies "qiáng 'strong'", you
must not give an error even though 'qiáng' can also mean wall.

One of the sentences should be a simple clause, while the other sentence should have
two clauses (e.g., "X, but Y" or "X, because Y", or "After X, Y" or "N said that X"
or "X, even though Y", etc.). Sentences may be declarations or commands.

The example question and answer should be single clauses. The question should not contain
the target word, while the answer must contain the target word.

Use elementary to intermediate vocabulary. Choose words that complement the target
word, e.g., for "chī 'to eat'" include words related to food, cooking, or the
kitchen.

For example:

<user>
%(correct_prompt)s
</user>

<model>
{"hanzi": "吃", "sentence1_pinyin": "Wǒ méi chī wán yīnwèi wǒ bú è.", "sentence1_hanzi": "我没吃完因为我不饿。", "sentence1_translation": "I didn't finish eating because I wasn't hungry.", "sentence2_pinyin": "Wǒ chī píngguǒ.", "sentence2_hanzi": "我吃苹果。", "sentence2_translation": "I eat an apple.", "question1_pinyin": "Nǐ wǔfàn shì shénme?", "question1_hanzi": "你午饭是什么?", "answer1_pinyin": "Wǒ chī le jīròu hé mǐfàn.", "answer1_hanzi": "我吃了鸡肉和米饭。", "answer1_translation": "I ate chicken and rice."}
</model>

<user>
%(incorrect_prompt)s
</user>

<model>
{"error": "The word 'xīguā' means 'watermelon', not 'pineapple'."}
</model>
""" % dict(
    correct_prompt=_make_word_prompt(pinyin="chī", translation="to eat"),
    incorrect_prompt=_make_word_prompt(pinyin="xīguā", translation="pineapple"),
)


@dataclass
class LLMWordNote(kgjson.Base):
    hanzi: str
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


def generate_word_note(*, pinyin: str, translation: str) -> LLMWordNote:
    with pgdb.connect() as db:
        LOG.info("start: generating word note (%s)", pinyin)
        response = llm.oneshot(
            db,
            _make_word_prompt(pinyin=pinyin, translation=translation),
            model=MODEL,
            system_prompt=WORD_PROMPT,
            app_name=_app_name("word"),
            options=llm.InferenceOptions.fast(),
        )
        LOG.info("end:   generating word note (%s)", pinyin)

        try:
            last_line_json = _parse_last_line_as_json(response)
            return LLMWordNote.deserialize(last_line_json)
        except Exception as e:
            raise KgError(
                "I was unable to parse the last line of the LLM response's as JSON.",
                error=e,
                text=response.output_text,
            )


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
    selected_words = [note.fields["hanzi"].value for note in notes[:n]]

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
        note.fields["hanzi"].value + " " + note.fields["translation"].value
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
