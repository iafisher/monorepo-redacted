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

You are given a word and English translation, and you must produce three example sentences.

If the input is valid, then the last line of your output MUST be a JSON object with the
following fields:

- hanzi: the given word in simplified characters
- sentence1_pinyin: the first example sentence, in Pinyin
- sentence1_hanzi: the first example sentence, in characters
- sentence1_translation: the first example sentence, translated to English
- sentence2_pinyin: the second example sentence, in Pinyin
- sentence2_hanzi: the second example sentence, in characters
- sentence2_translation: the second example sentence, translated to English
- sentence3_pinyin: the third example sentence, in Pinyin
- sentence3_hanzi: the third example sentence, in characters
- sentence3_translation: the third example sentence, translated to English

If the input is invalid (incorrect pinyin or incorrect translation), then the last line
of your output MUST be a JSON object with a single field, `error`, containing a one-sentence
explanation of the error. If the pinyin is incorrect, you must give an error. If the
translation is seriously incorrect, you must give an error. If the translation has a minor
inaccuracy, then proceed, generating valid sentences.

Do not give an error for pinyin that is ambiguous if the translation correctly identifies
one of the possible characters. For example, if the user supplies "qiáng 'strong'", you
must not give an error even though 'qiáng' can also mean wall.

One of the sentences should be a simple clause, while two of the sentences should
have two clauses (e.g., "X, but Y" or "X, because Y", or "After X, Y" or "N said that X"
or "X, even though Y", etc.). Sentences may be declarations, commands, or questions.

Use elementary to intermediate vocabulary. Choose words that complement the target
word, e.g., for "chī 'to eat'" include words related to food, cooking, or the
kitchen.

For example:

<user>
%(correct_prompt)s
</user>

<model>
{"hanzi": "吃", "sentence1_pinyin": "Wǒ méi chī wán yīnwèi wǒ bú è.", "sentence1_hanzi": "我没吃完因为我不饿。", "sentence1_translation": "I didn't finish eating because I wasn't hungry.", "sentence2_pinyin": "Wǒ chī píngguǒ.", "sentence2_hanzi": "我吃苹果。", "sentence2_translation": "I eat an apple.", "sentence3_pinyin": "Wǒ xiǎng chī mǐfàn, dànshì wǒ méiyǒu shíjiān.", "sentence3_hanzi": "我想吃米饭，但是我没有时间。", "sentence3_translation": "I want to eat rice, but I don't have time."}
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
    sentence3_pinyin: str
    sentence3_hanzi: str
    sentence3_translation: str


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

        last_line_json = _parse_last_line_as_json(response)
        return LLMWordNote.deserialize(last_line_json)


QUESTION_PROMPT = """\
You create example question/answer exchanges in Mandarin Chinese for a language learner.

You are given a question in English, and you must translate it into Chinese and produce a
sample answer.

If the input is valid, then the last line of your output MUST be a JSON object with the
following fields:

- question_pinyin: the question translated into Chinese, in Pinyin
- question_hanzi: the question translated into Chinese, in characters
- answer_pinyin: an example answer to the question, in Pinyin
- answer_hanzi: an example answer to the question, in characters
- answer_translation: an example answer to the question, translated to English

Translate questions idiomatically, not word-for-word. Use elementary to intermediate
vocabulary.

For example:

<user>
What was your major in college?
</user>

<model>
{"question_pinyin": "Nǐ dàxué xué de shì shénme zhuānyè?", "question_hanzi": "你大学学的是什么专业？", "answer_pinyin": "Wǒ dàxué xué de shì jìsuànjī kēxué.", "answer_hanzi": "我大学学的是计算机科学。", "answer_translation": "I majored in computer science."}
</model>
"""


@dataclass
class LLMQuestionNote(kgjson.Base):
    question_pinyin: str
    question_hanzi: str
    answer_pinyin: str
    answer_hanzi: str
    answer_translation: str


def generate_question_note(question: str) -> LLMQuestionNote:
    with pgdb.connect() as db:
        LOG.info("start: generating question note (%s)", question)
        response = llm.oneshot(
            db,
            question,
            model=MODEL,
            system_prompt=QUESTION_PROMPT,
            app_name=_app_name("question"),
            options=llm.InferenceOptions.fast(),
        )
        LOG.info("end:   generating question note (%s)", question)

        last_line_json = _parse_last_line_as_json(response)
        return LLMQuestionNote.deserialize(last_line_json)


def _parse_last_line_as_json(response: llm.ModelResponse) -> StrDict:
    text = response.output_text
    last_line = text.splitlines()[-1]
    try:
        last_line_json = json.loads(last_line)
    except Exception as e:
        raise KgError(
            "I was unable to parse the last line of the LLM response's as JSON.",
            error=e,
            last_line=last_line,
        )

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
