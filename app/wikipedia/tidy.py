import time
from typing import Annotated, NewType

from app.wikipedia.common import USER_AGENT
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, githelper, kgenv, kghttp, kgjson, llm, pdb, simplemail


class EditableArticle:
    wikitext: str

    def __init__(self, wikitext: str) -> None:
        self.wikitext = wikitext

    def edit(self, new_text: str) -> None:
        self.wikitext = new_text

    def get(self) -> str:
        return self.wikitext


class EditArticleTool(llm.BaseTool):
    article: EditableArticle

    @classmethod
    @override
    def get_name(cls) -> str:
        return "edit_article"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Edit a single line of the article. The edit will be applied to all matching lines."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                old_line=dict(
                    type="string",
                    description="The exact line to be replaced. This MUST be the full text of the line. Do not include a trailing newline.",
                ),
                new_line=dict(
                    type="string",
                    description="The line to replace the old line with. This MUST be the full text of the line.",
                ),
            ),
            required=["old_text", "new_text"],
        )

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    def __init__(self, article: EditableArticle) -> None:
        self.article = article

    @override
    def call(self, params: Any) -> Any:
        old_text = self.get_param(params, "old_line")
        new_text = self.get_param(params, "new_line")

        full_text = self.article.get()
        index = full_text.find(old_text)
        if index == -1:
            raise llm.ToolError("old_line not found in the article's current text")

        self.article.edit(full_text.replace(old_text, new_text))


# TODO(2026-02): Replace `GetArticleTool` with token-efficient `SearchArticleTool` that only
# returns a few lines at a time.


class GetArticleTool(llm.BaseTool):
    @classmethod
    @override
    def get_name(cls) -> str:
        return "get_article"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Get the current text of the article."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(type="object", properties={})

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return dict(
            type="string",
            description="The current text of the article, with all edits applied.",
        )

    def __init__(self, article: EditableArticle) -> None:
        self.article = article

    @override
    def call(self, params: Any) -> Any:
        return self.article.get()


class SubmitArticleTool(llm.BaseTool):
    is_finished: bool

    @classmethod
    @override
    def get_name(cls) -> str:
        return "submit_article"

    @classmethod
    @override
    def get_plain_description(cls) -> str:
        return "Call this tool to submit the finished article once all edits have been made."

    @classmethod
    @override
    def get_input_schema(cls) -> StrDict:
        return dict(type="object", properties={})

    @classmethod
    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    def __init__(self) -> None:
        self.is_finished = False

    @override
    def call(self, _params: Any) -> Any:
        self.is_finished = True


SYSTEM_PROMPT = f"""\
Your job is to copy-edit English Wikipedia articles. Make these corrections:

- Replace a hyphen with an unspaced en-dash when used to express a numeric range.
    - FIX: "5-6 different people" --> "5–6 different people"
- Replace a hyphen with a spaced en-dash when used to mark off a parenthetical.
    - FIX: "The man - later found dead - was..." --> "The man – later found dead – was..."
- Replace a spaced em-dash with an unspaced em-dash.
- Replace abbreviated decade names with the full name, and remove any apostrophe.
    - FIX: "In the 50's" --> "In the 1950's"
    - OK: "in his 50s" (not a decade name)
- Replace abbreviated year names.
    - FIX: "In '83" --> "In 1983"
    - OK: "1855–60" (second part of range can be abbreviated)
    - FIX: "1855–6" --> "1855–56"
- Ensure that footnotes appear after punctuation, unspaced. Multiple footnotes should not have spaces in between them.
    - FIX: "It snows often in Los Angeles{{citation needed}}." --> "It snows often in Los Angeles.{{citation needed}}"
    - FIX: "It snows often in Los Angeles. {{citation needed}}" --> "It snows often in Los Angeles.{{citation needed}}"
    - Common syntax that creates footnotes: <ref>...</ref>, {{citation needed}}, {{cn}}, {{efn}}
- Change section titles to sentence case.
    - FIX: "== Early Life and Education ==" --> "== Early life and education =="
- Expand contractions.
    - FIX: "wasn't" --> "was not"
- Replace USA with US (except when part of a proper noun).
- Replace the slash character when used to indicate conjunction, or "per" for a unit of measurement.
    - FIX: "the late 1960s/early 1970s" --> "the late 1960s and early 1970s" or "the late 1960s or early 1970s" depending on context
    - FIX: "meter/second" --> "meter per second" (though abbreviated "m/s" is OK)
    - Exception: Leave slash for month names in citations, e.g., "March/April".
- Add comma separators to large numbers.
    - FIX: "1000 people" --> "1,000 people"
- Italicize the names of books and films.
    - FIX: "The Godfather" --> "''The Godfather''"
    - OK: "the Bible", "the Quran", "the Talmud" (major religious works)
- Use the `{{'}}` syntax to correct add an apostrophe to an italicized word.
    - FIX: "''Enola Gay'''s crew" --> "''Enola Gay''{{'}}s crew"
- Put appropriate spaces around punctuation.
    - FIX: "off the target,and they" --> "off the target, and they"
- Remove space before commas, semicolons, colons, periods, question marks, and exclamation marks.
    - FIX: "text ." → "text."
    - FIX: "text ," → "text,"
    - FIX: "text ;" → "text;"
- Correct any misspelled words.
- Use a non-breaking space to separate a figure from its unit of measurement.
    - FIX: "5m in length" --> "5&nbsp;m in length"
    - FIX: "5 m in length" --> "5&nbsp;m in length"
- Replace curly/smart quotes and apostrophes with straight ones.
- Replace the number sign (#) with "number" when referring to rankings or numbers.
    - FIX: "reached #1 in the charts" → "reached number one in the charts"
    - Exception: Comic book issue numbers may use #1 format
- Replace hyphen with proper minus sign (−) for negative numbers or subtraction.
    - FIX: "-5 degrees" → "−5 degrees"
    - FIX: "5 - 3" → "5 − 3" (when used as subtraction operator)
- Replace "x" with multiplication sign (×) when indicating multiplication.
    - FIX: "5 x 3" → "5 × 3"
    - Exception: "4x4" vehicle designation uses x
- Replace precomposed ellipsis character with three unspaced periods.
    - FIX: "…" → "..."
- Add comma after year in month-day-year format when followed by more text.
    - FIX: "October 1, 2011 as the deadline" → "October 1, 2011, as the deadline"
- Add comma after state/province when following city name.
    - FIX: "Chattanooga, Tennessee for the night" → "Chattanooga, Tennessee, for the night"
- Remove space between number and percent sign.
    - FIX: "3 %" → "3%"
- Remove space between currency symbol and number.
    - FIX: "$ 123" → "$123"
- Replace archaic ligatures in English words.
    - FIX: "encyclopædia" → "encyclopedia" or "encyclopaedia"
    - OK: "Æthelstan" (proper name)
- Don't capitalize "the" mid-sentence unless part of a proper name.
    - FIX: "throughout The United Kingdom" → "throughout the United Kingdom"
    - OK: "visited The Hague" (proper name)
- Use non-breaking space between year and AD/BC/CE/BCE.
    - FIX: "5 BC" → "5&nbsp;BC"
    - FIX: "AD 565" → "AD&nbsp;565"
- Don't mix "between" or "from" with en-dashes.
    - FIX: "between 450–500 people" → "between 450 and 500 people"
    - FIX: "from 1961–1964" → "from 1961 to 1964"
- Add 's to singular nouns ending in s.
    - FIX: "Cortez' men" → "Cortez's men"
    - OK: "for goodness' sake" (set phrase)
- Remove italics that surround an entire quotation. (Italics inside of a quotation are OK.)

Obey the following guidelines:

- Purely typographical corrections (dashes, italicized apostrophes) should be applied to quoted
  material, but corrections that change the content (contractions, decade format) should not be.
- Use the existing national variety of English (American, British, etc.) if established, or else
  the national variety with strongest ties to the article's topic.

Do not make any corrections not explicitly on this list. No correction should change the meaning of
the article.

Do not make any formatting changes that have no visible effect.

- For instance, do not change "==Section header==" to "== Section header ==" or vice versa.
- Do not change "{{spaced ndash}}" to an en-dash character.

Use your tools to make edits to the article. Don't call `{GetArticleTool.get_name()}` at the
beginning as you are already presented with the initial text of the article.

You are invoked non-interactively. Do not ask questions or pause for user input. If you have a
limit to the number of tools you can call in a single turn, make all corrections in as many turns
as needed. Call the `{SubmitArticleTool.get_name()}` tool when finished with all edits.
"""


ArticleTitle = NewType("ArticleTitle", str)


@dataclass
class NightlyState(kgjson.Base):
    last_edited: Dict[str, datetime.datetime] = dataclasses.field(default_factory=dict)


DO_NOT_EDIT_WITHIN_THIS_NUMBER_OF_DAYS = 30


_mutex = command.Mutex()


def main_nightly(
    *,
    model: str = llm.GPT_5_2,
    category: Annotated[
        Optional[str],
        command.Extra(help="fetch a random article in this category", mutex=_mutex),
    ],
    vital_level_3: Annotated[
        bool, command.Extra(help="fetch a random level 3 vital article", mutex=_mutex)
    ],
    article: Annotated[
        Optional[str], command.Extra(help="copy-edit this article", mutex=_mutex)
    ],
) -> None:
    app_dir = kgenv.get_app_dir("wikipedia")
    app_dir.mkdir(parents=True, exist_ok=True)
    with NightlyState.with_lock(app_dir / "state.json") as state_lock:
        state = state_lock.read()
        if article is None:
            article = _select_random_article(
                state, category=category, vital_level_3=vital_level_3
            )

        LOG.info("selected random article category %r: %r", category, article)
        article = _normalize_title(article)
        wikipage = fetch_wiki_page(article)
        edited_text, response = tidy(wikipage.wikitext, model=model)
        if edited_text == wikipage.wikitext:
            LOG.info("no edits made")
            return

        html_diff = githelper.make_html_diff(
            wikipage.wikitext, edited_text, word_diff=False
        )

        outfile = app_dir / "output" / f"{article}.txt"
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(edited_text)
        LOG.info("wrote article text to %s", outfile)
        state.last_edited[article] = timehelper.now()

        simplemail.send_email(
            f"wikitidy: edits proposed for {article}",
            _make_email(
                conversation_id=response.conversation_id,
                outfile=outfile.as_posix(),
                article=article,
                html_diff=html_diff,
                revision=wikipage.revision,
            ),
            recipients=[simplemail.LOW_PRIORITY_RECIPIENT],
            html=True,
        )


def _select_random_article(
    state: NightlyState, *, category: Optional[str], vital_level_3: bool
) -> str:
    now = timehelper.now()
    while True:
        if vital_level_3:
            url = "https://randomincategory.toolforge.org/?category=A-Class%20level-3%20vital%20articles&category2=B-Class%20level-3%20vital%20articles&category3=C-Class%20level-3%20vital%20articles&category4=FA-Class%20level-3%20vital%20articles&category5=FL-Class%20level-3%20vital%20articles&category6=GA-Class%20level-3%20vital%20articles&category7=List-Class%20level-3%20vital%20articles&category8=Start-Class%20level-3%20vital%20articles&category9=Stub-Class%20level-3%20vital%20articles&server=en.wikipedia.org&cmnamespace=&cmtype=&returntype=subject"
        else:
            url = f"https://en.wikipedia.org/wiki/Special:RandomInCategory/{category}"

        response = kghttp.get(
            url, headers={"User-Agent": USER_AGENT}, allow_redirects=False
        )
        if response.next is None or response.next.url is None:
            raise KgError("expected redirect", url=url)

        article = response.next.url.rsplit("/", maxsplit=1)[1]
        if article not in state.last_edited:
            return article
        else:
            time_elapsed = now - state.last_edited[article]
            if time_elapsed.days < DO_NOT_EDIT_WITHIN_THIS_NUMBER_OF_DAYS:
                LOG.info(
                    "skipping %r, last edited %s (%s day(s) ago)",
                    article,
                    state.last_edited[article],
                    time_elapsed.days,
                )
                time.sleep(5)
            else:
                return article


def _make_email(
    *, conversation_id: int, outfile: str, article: str, revision: int, html_diff: str
) -> str:
    return f"""\
<p><a href="http://llm/transcript/{conversation_id}">View LLM transcript</a></p>

<ol>
  <li><pre><code>ssh homeserver2 cat {outfile} | pbcopy</code></pre></li>
  <li>
    <a href="https://en.wikipedia.org/w/index.php?title={article}&action=edit&oldid={revision}">
      Edit the page.
    </a>
  </li>
</ol>

<h2>Diff</h2>
{html_diff}
"""


def main_test(
    article: str,
    *,
    model: str = llm.CLAUDE_HAIKU_4_5,
    save: Annotated[
        Optional[pathlib.Path],
        command.Extra(help="save the raw wikitext output to this file"),
    ],
    regex: Annotated[bool, command.Extra(help="use regex instead of an LLM")],
    revision: Annotated[
        Optional[int],
        command.Extra(
            help="fetch this revision of the page instead of the latest revision"
        ),
    ],
) -> None:
    # good test article is 'El Surar, Valencia'
    # or 'Mississippi State Senate' at revision 1333772842
    article = _normalize_title(article)
    wikipage = fetch_wiki_page(article, revision=revision)
    if regex:
        edited_text = tidy_regex(wikipage.wikitext)
    else:
        edited_text, _ = tidy(wikipage.wikitext, model=model)

    print_diff(wikipage.wikitext, edited_text)
    if save is not None:
        save.write_text(edited_text)
        LOG.info("wrote %s char(s) to %s", len(edited_text), save)


@dataclass
class WikiPage:
    wikitext: str
    revision: int


def fetch_wiki_page(
    article: ArticleTitle, *, revision: Optional[int] = None
) -> WikiPage:
    base_url = "https://en.wikipedia.org/w/api.php?action=parse&format=json&prop=wikitext|revid"
    if revision is not None:
        url = f"{base_url}&oldid={revision}"
    else:
        url = f"{base_url}&page={article}"

    response = kghttp.get(url, headers={"User-Agent": USER_AGENT})
    data = response.json()
    if "parse" not in data:
        raise KgError("unexpected response from Wikipedia API", data=data)

    if revision is not None:
        actual_title = _normalize_title(data["parse"]["title"])
        if article != actual_title:
            raise KgError(
                "`revision` and `article` mismatch",
                revision=revision,
                expected_title=article,
                actual_title=actual_title,
            )

    return WikiPage(
        wikitext=data["parse"]["wikitext"]["*"], revision=data["parse"]["revid"]
    )


def _normalize_title(title: str) -> ArticleTitle:
    return ArticleTitle(title.replace(" ", "_"))


def print_diff(wikitext: str, edited_text: str) -> None:
    print(githelper.make_ansi_diff(wikitext, edited_text, word_diff=True))


def tidy(
    text: str, *, model: str = llm.CLAUDE_HAIKU_4_5, max_turn_count: int = 10
) -> Tuple[str, llm.ModelResponse]:
    with pdb.connect(transaction_mode=pdb.TransactionMode.AUTOCOMMIT) as db:
        conversation = llm.Conversation.start(
            db, model=model, app_name="wikipedia::copyedit", system_prompt=SYSTEM_PROMPT
        )
        LOG.info("LLM conversation ID: %s", conversation.conversation_id)

        submit_article_tool = SubmitArticleTool()
        editable_article = EditableArticle(text)
        tools: List[llm.BaseTool] = [
            EditArticleTool(editable_article),
            GetArticleTool(editable_article),
            submit_article_tool,
        ]
        hooks = llm.LoggingHooks()
        options = llm.InferenceOptions.normal()
        response = conversation.prompt(
            db, text, hooks=hooks, tools=tools, options=options
        )

        turn_count = 1
        while not submit_article_tool.is_finished and turn_count < max_turn_count:
            LOG.info("reprompting the model")
            conversation.prompt(
                db,
                "Continue applying edits until done, "
                f"then call your `{submit_article_tool.get_name()}` tool.",
                hooks=hooks,
                tools=tools,
                options=options,
            )
            turn_count += 1

        if not submit_article_tool.is_finished:
            LOG.warning(
                "ran out of turns without calling `%s`", submit_article_tool.get_name()
            )

        return editable_article.get(), response


_blocks_to_ignore_regex = lazy_re(
    r"(<ref[^>]*>.*</ref>|\[\[File:[^\]]*\]\]|\{\{.*\}\})"
)
_en_dash_numeric_range_regex = lazy_re(r"([0-9]+)-([0-9]+)")


def tidy_regex(text: str) -> str:
    r: List[str] = []
    for i, block in enumerate(_blocks_to_ignore_regex.get().split(text)):
        # `re.split` produces a list of `[UNMATCHED, MATCHED, UNMATCHED, MATCHED, ..., UNMATCHED]`.
        # So matched blocks have odd indices and unmatched blocks have even indices.
        # In this case, the matched blocks are ones we should ignore.
        if i % 2 == 0:
            block = _en_dash_numeric_range_regex.get().sub(r"\1–\2", block)
            r.append(block)
        else:
            r.append(block)
    return "".join(r)


cmd = command.Group()
cmd.add2("nightly", main_nightly, less_logging=False)
cmd.add2("test", main_test, less_logging=False)
