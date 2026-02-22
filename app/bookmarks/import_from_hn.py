import textwrap
from typing import Annotated

from app.bookmarks import hn
from app.bookmarks import models as bookmark_models
from app.bookmarks.common import insert_bookmarks_filtering_duplicates
from app.bookmarks.redacted import *

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import command, llm, pdb


@dataclass
class Story:
    item_id: int
    title: str
    score: int
    url: str
    comments: List[str]


LLM_SYSTEM_PROMPT = f"""\
You are a digital assistant that chooses stories from Hacker News to include in a morning briefing for a
software engineer.

- Favor stories with deep technical content.
- Do not include current events or mainly non-technical content.
- Positive: The story has lots of in-depth comments.
- Positive: The story is from someone's personal website.
- Consider the story's score, but you can still pick a low-score story if it is otherwise interesting.

Topics I am typically interested in:

{HN_TOPICS}

On average, you should pick 0-3 stories.

You are given some information about the story, and the top-level comments, if any.

List the IDs of the stories of interest on a single line, separated by commas. This MUST be the last
line of your response. If no stories are chosen, write NONE. You do not need to explain your choices.

For example:

User:

> 44608754: Asynchrony is not concurrency https://kristoff.it/blog/asynchrony-is-not-concurrency/ (score: 143)
>   - &quot;Asynchrony&quot; is a very bad word for this and we already have a very well-defined mathematical one: commutativity. Some operations are commutative (order does not matter: addition, multiplication, etc.), while others are non- [...]
>   - I kind of think the author simply pulled the concept of yielding execution out of the definition of concurrency and into this new &quot;asynchrony&quot; term. Then they argued that the term is needed because without it the entire concept of [...]
>   - There&#x27;s a great old book on this if someone wants to check it: Communicating Sequential Processes. From Hoare. Go channels and the concurrent approach was inspired on this.<p>I also wrote a blog post a while back when I did a talk at work, [...]
>
> 44609969: Silence Is a Commons by Ivan Illich (1983) http://www.davidtinapple.com/illich/1983_silence_commons.html (score: 53)
>   - Computers could hardly do anything back then. Mostly backend data processing.<p>Yet this speech could have been written today.<p>Intriguing.
>   - Why is Ivan Illich so underrated ?<p>He predicted and theorized free software 10 years before it happened in Tools for Conviviality, made the most obvious and needed critic of education and hospitals alone against the Zeitgeist, studied step by [...]
>
> 44610925: Ccusage: A CLI tool for analyzing Claude Code usage from local JSONL files https://github.com/ryoppippi/ccusage (score: 9)
>   - Have been using this for awhile, I&#x27;m on the $100&#x2F;mo Max plan and have been running $600-800&#x2F;mo in terms of usage, and I&#x27;m hardly pushing it to the limits (missing lots of billing windows).<p>It makes me wonder what [...]
>   - I really like how easy it is to run using bunx, pnpx, npx, etc.<p>But does anyone have thoughts on the security aspect. Getting people used to just running code like this that has full access to the system is slightly concerning.<p>On the other [...]
>
> 44610468: How to write Rust in the Linux kernel: part 3 https://lwn.net/SubscriberLink/1026694/3413f4b43c862629/ (score: 8)

Assistant:

> 44608754,44610468
"""


def main(
    *,
    model: Annotated[str, llm.cli.model_flag_extra()] = llm.ANY_FAST_MODEL,
    story_limit: Annotated[
        int, command.Extra(help="limit the number of stories to query")
    ] = 20,
    comment_limit: Annotated[
        int, command.Extra(help="limit the number of comments to query per story")
    ] = 10,
) -> None:
    LOG.info("querying Hacker News for stories")
    stories = query_hn(story_limit=story_limit, comment_limit=comment_limit)
    LOG.info("prompting LLM for recommendations from %d HN stories", len(stories))
    with pdb.connect() as db:
        recommended_stories = get_llm_recommendations(db, stories, model=model)
        if len(recommended_stories) == 0:
            LOG.info("no recommended stories")
        else:
            save_bookmarks(db, recommended_stories)


HN_AUTO_RECOMMENDATION_SOURCE = "hn_auto_recommendations"


def save_bookmarks(db: pdb.Connection, stories: List[Story]) -> None:
    time_created = timehelper.now()
    bookmarks = [
        bookmark_models.Bookmark(
            bookmark_id=-1,
            source_id=str(story.item_id),
            title=story.title,
            url=story.url,
            reading_time="",
            appeal="",
            source=HN_AUTO_RECOMMENDATION_SOURCE,
            reason_archived="",
            tags=[],
            time_created=time_created,
            time_archived=None,
        )
        for story in stories
    ]
    insert_bookmarks_filtering_duplicates(
        db,
        bookmarks,
        source_name_for_logging="HN auto recommendations",
        dry_run=False,
    )


def get_llm_recommendations(
    db: pdb.Connection, stories: List[Story], *, model: str
) -> List[Story]:
    message = make_prompt_from_hn_stories(stories)
    response = llm.oneshot(
        db,
        message,
        model=model,
        system_prompt=LLM_SYSTEM_PROMPT,
        app_name="bookmarks::hn_recs",
        options=llm.InferenceOptions.normal(),
    )
    model = response.model
    LOG.info(
        "LLM conversation %d (%s), %d token(s)",
        response.conversation_id,
        model,
        response.token_usage.total_tokens,
    )
    lines = response.output_text.splitlines()
    if len(lines) == 0:
        raise KgError("LLM response was empty", model=model)

    final_line = lines[-1].strip().lower()
    if final_line == "none":
        return []
    else:
        try:
            recommended_story_ids = set(int(s) for s in final_line.split(","))
        except Exception:
            raise KgError(
                "LLM response could not be parsed",
                final_line=final_line,
                model=model,
            )
        return [story for story in stories if story.item_id in recommended_story_ids]


def query_hn(*, story_limit: int, comment_limit: int) -> List[Story]:
    top_story_ids = hn.fetch_top_story_ids()
    stories: List[Story] = []
    for story_id in top_story_ids[:story_limit]:
        story_dict = hn.fetch_item(story_id)
        if story_dict is None or "url" not in story_dict:
            continue

        comment_dicts = [
            hn.fetch_item(comment_id)
            for comment_id in story_dict.get("kids", [])[:comment_limit]
        ]
        stories.append(
            Story(
                item_id=story_dict["id"],
                title=story_dict["title"],
                score=story_dict["score"],
                url=story_dict["url"],
                comments=[
                    comment["text"]
                    for comment in comment_dicts
                    if comment is not None and "text" in comment
                ],
            )
        )

    return stories


def make_prompt_from_hn_stories(stories: List[Story]) -> str:
    builder: List[str] = []
    for story in stories:
        builder.append(
            f"{story.item_id}: {story.title} {story.url} (score: {story.score})"
        )
        for comment in story.comments:
            builder.append(f"  - {textwrap.shorten(comment, width=250)}")
        builder.append("")

    return "\n".join(builder)


cmd = command.Command.from_function(
    main, help="Import bookmarks from the Hacker News front page", less_logging=False
)
