from decimal import Decimal

from iafisher.prelude import *
from lib import kghttp, kgjson, secrets


@dataclass
class ApiQuestion(kgjson.Base):
    type: str
    instructions: str
    criteria: Optional[Dict[str, str]] = None


@dataclass
class ApiRequest(kgjson.Base):
    state: str
    model: str
    questions: Dict[str, ApiQuestion]


@dataclass
class ApiAnswer(kgjson.Base):
    type: str
    noul: Optional[float]
    choice: Optional[str]
    probabilities: Optional[Dict[str, float]]
    confidence: Optional[float]
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


@dataclass
class ApiUsage(kgjson.Base):
    input_tokens: int
    output_tokens: int
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


@dataclass
class ApiResponse(kgjson.Base):
    model: str
    answers: Dict[str, ApiAnswer]
    usage: ApiUsage
    raw: Annotated[StrDict, kgjson.StoreMessage()] = dataclasses.field(repr=False)


def decide(state: str, questions: List[Tuple[str, ApiQuestion]]) -> ApiResponse:
    api_key = secrets.get_or_raise("JEV_API_KEY")
    request = ApiRequest(
        state=state, model="jev-latest", questions={k: v for k, v in questions}
    )
    http_response = kghttp.post(
        "https://api.typesafe.ai/v1/systemone",
        json=request.to_dict(),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response = http_response.json()
    return ApiResponse.deserialize(response)


def _decide_one(state: str, question: ApiQuestion) -> ApiAnswer:
    question_key = "my_question"
    api_response = decide(state, [(question_key, question)])
    try:
        return api_response.answers[question_key]
    except KeyError:
        raise KgError(
            "The API response did not contain the expected question key.",
            question_key=question_key,
            question=question,
            api_response=api_response,
        )


def decide_yes_or_no(state: str, instructions: str) -> float:
    question = ApiQuestion(type="noul", instructions=instructions)
    api_answer = _decide_one(state, question)
    if api_answer.noul is None:
        raise KgError(
            "The `noul` field on the answer object is unexpectedly blank or missing"
            " for a `type='noul'` question.",
            question=question,
            api_answer=api_answer,
        )
    return api_answer.noul


def decide_from_choices(
    state: str, instructions: str, choices: List[Tuple[str, str]]
) -> List[Tuple[str, float]]:
    question = ApiQuestion(
        type="choice", instructions=instructions, criteria={k: v for k, v in choices}
    )
    api_answer = _decide_one(state, question)
    if api_answer.probabilities is None:
        raise KgError(
            "The `probabilities` field on the answer object is unexpectedly blank or missing"
            " for a `type='choice'` question.",
            question=question,
            api_answer=api_answer,
        )
    return list(api_answer.probabilities.items())


def decide_likeliest_choice(
    state: str, instructions: str, choices: List[Tuple[str, str]]
) -> Tuple[str, float]:
    probabilities = decide_from_choices(state, instructions, choices)
    return max(probabilities, key=lambda tup: tup[1])


# https://docs.typesafe.ai/models
USD_PER_MILLION_TOKENS = Decimal("0.042")  # Jev 1.13 as of 2026-09-27


def estimate_cost_usd(usage: ApiUsage) -> Decimal:
    return (usage.input_tokens / Decimal(1_000_000)) * USD_PER_MILLION_TOKENS


if __name__ == "__main__":
    state = "We spent the summer vacationing on the Loire."
    instructions1 = (
        "Does the statement mention anything related to the country of France?"
    )
    print(f"{state=}")
    print(f"{instructions1=}")
    print(decide_yes_or_no(state, instructions1))
    instructions2 = (
        "Does the statement mention anything related to the country of Mongolia?"
    )
    print(f"{instructions2=}")
    print(decide_yes_or_no(state, instructions2))
