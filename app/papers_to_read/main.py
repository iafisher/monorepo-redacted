import contextlib
import json
import uuid

from iafisher import timehelper
from iafisher.prelude import *
from lib import command, fzf, kgjson, llm, localdb, pgdb


SYSTEM_PROMPT = """\
You recommend academic papers for a user to read.

Prefer shorter and less dense papers. The user will typically read the papers on the subway.

Previous recommendations the user liked:
%(upvoted_recommendations)s

Previous recommendations the user did not like:
%(downvoted_recommendations)s

Use your tool to submit recommendations. The user will not see any text you generate. Do
not ask any questions or end your turn without submitting recommendations.
"""


@dataclass
class Recommendation(kgjson.Base):
    title: str
    author: str
    description: str

    @override
    def __str__(self) -> str:
        return f'"{self.title}" by {self.author}'


class SubmitRecommendationTool(llm.BaseTool):
    recommendations: List[Recommendation]

    def __init__(self) -> None:
        self.recommendations = []

    @override
    def get_name(self):
        return "submit_recommendation"

    @override
    def get_plain_description(self):
        return "Submit a paper recommendation for the user to view."

    @override
    def get_input_schema(self) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                paper_title=dict(
                    type="string",
                    description="The title of the paper. Do not put the title in quotes.",
                ),
                paper_author=dict(
                    type="string",
                    description="The name of the author or authors of the paper.",
                ),
                brief_description=dict(
                    type="string",
                    description="A one-sentence description of the paper's topic.",
                ),
            ),
            required=["paper_title", "paper_author", "brief_description"],
        )

    @override
    def get_output_schema(cls) -> StrDict:
        return {}

    @override
    def call(self, params: Any) -> None:
        title = params["paper_title"]
        author = params["paper_author"]
        description = params["brief_description"]
        self.recommendations.append(
            Recommendation(title=title, author=author, description=description)
        )


KV_STATE_KEY = "papers_to_read_state"


def main_recommend(topic: str, *, model: str = "sonnet") -> None:
    with localdb.connect() as db:
        state = _fetch_state(db)

    state.previous_recommendations.sort(key=lambda rec: rec.date_created)
    take_the_last_n = 20
    upvoted_recommendations = [
        rec for rec in state.previous_recommendations if rec.vote == 1
    ][:-take_the_last_n]
    downvoted_recommendations = [
        rec for rec in state.previous_recommendations if rec.vote == -1
    ][:-take_the_last_n]

    tool = SubmitRecommendationTool()
    prompt = (
        f"Please give your 5 recommendations. The user-provided topic is {topic!r}."
    )
    with pgdb.connect() as db:
        response = llm.oneshot(
            db,
            prompt,
            model=model,
            system_prompt=SYSTEM_PROMPT
            % dict(
                upvoted_recommendations=_rec_list_to_str(upvoted_recommendations),
                downvoted_recommendations=_rec_list_to_str(downvoted_recommendations),
            ),
            app_name="papers-to-read::recommend",
            options=llm.InferenceOptions.normal(),
            tools=[tool],
        )

    print(f"Conversation ID: {response.conversation_id}")
    for rec in tool.recommendations:
        print()
        print(f"- {rec}")
        print(f"    {rec.description}")

    now = timehelper.now()
    with localdb.connect() as db:
        with updating_state(db) as state:
            dated_recommendations = [
                DatedRecommendation(
                    uuid=str(uuid.uuid4()),
                    recommendation=recommendation,
                    vote=0,
                    vote_comment=None,
                    date_created=now,
                )
                for recommendation in tool.recommendations
            ]
            state.previous_recommendations.extend(dated_recommendations)


@dataclass
class DatedRecommendation(kgjson.Base):
    uuid: str
    recommendation: Recommendation
    vote: int  # 1 = upvote, 0 = no vote, -1 = downvote
    vote_comment: Optional[str]
    date_created: dt.datetime


def _rec_list_to_str(recs: List[DatedRecommendation]) -> str:
    return "".join(
        f"{rec.recommendation} (comment: {rec.vote_comment})\n" for rec in recs
    )


@dataclass
class State(kgjson.Base):
    previous_recommendations: List[DatedRecommendation] = dataclasses.field(
        default_factory=list
    )


@contextlib.contextmanager
def updating_state(db: localdb.Connection):
    state = _fetch_state(db)
    yield state
    localdb.kv_set(db, KV_STATE_KEY, state.serialize())


def _fetch_state(db: localdb.Connection) -> State:
    state_str = localdb.kv_get(db, KV_STATE_KEY)
    return State.deserialize(json.loads(state_str)) if state_str else State()


DEFAULT_N_DAYS_OR_NEWER = 7


def main_downvote(
    *, comment: Optional[str], n_days_or_newer: int = DEFAULT_N_DAYS_OR_NEWER
) -> None:
    _set_vote(-1, comment, n_days_or_newer)


def main_upvote(
    *, comment: Optional[str], n_days_or_newer: int = DEFAULT_N_DAYS_OR_NEWER
) -> None:
    _set_vote(1, comment, n_days_or_newer)


def _set_vote(vote: int, comment: Optional[str], n_days_or_newer: int) -> None:
    with localdb.connect() as db:
        state = _fetch_state(db)

    later_than = timehelper.today() - datetime.timedelta(days=n_days_or_newer)
    eligible = [
        rec
        for rec in state.previous_recommendations
        if rec.vote == 0 and rec.date_created.date() >= later_than
    ]

    if len(eligible) == 0:
        bail(
            f"No eligible recommendations in the past {pluralize(n_days_or_newer, 'day')}."
        )

    selected = fzf.select_map([(str(rec), rec) for rec in eligible])

    with localdb.connect() as db:
        with updating_state(db) as state:
            for rec in state.previous_recommendations:
                if rec.uuid == selected.uuid:
                    rec.vote = vote
                    rec.vote_comment = comment
                    break
            else:
                bail(
                    "Recommendation was not found in the state."
                    " Was it updated in the meantime?"
                )


cmd = command.Group()
cmd.add2("downvote", main_downvote)
cmd.add2("recommend", main_recommend)
cmd.add2("upvote", main_upvote)

if __name__ == "__main__":
    command.dispatch(cmd)
