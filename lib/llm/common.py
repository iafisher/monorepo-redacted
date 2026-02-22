import itertools
import pickle
import time
from typing import Iterator

from iafisher_foundation.prelude import *

from . import universal


@dataclass
class TokenUsage:
    # Supported by: all models
    input_tokens: Optional[int] = None
    # Supported by: all models
    output_tokens: Optional[int] = None
    # Supported by: Gemini, GPT
    reasoning_tokens: Optional[int] = None
    # Supported by: all models
    cache_read_tokens: Optional[int] = None
    # Supported by: Claude
    cache_creation_tokens: Optional[int] = None
    # Supported by: all models (synthetic for Claude)
    total_tokens: Optional[int] = None
    # the raw response the model returned, which may include extra model-specific information
    raw_json: Optional[StrDict] = None


class IteratorWithDelay:
    def __init__(self, it: Iterator[Any]) -> None:
        self._it = it

    def __iter__(self) -> Any:
        return self

    def __next__(self) -> Any:
        time.sleep(0.01)
        return next(self._it)


def load_mock_turn(model: str, messages: List[universal.Message]) -> Any:
    mock_path = pathlib.Path(__file__).absolute().parent / "mocks" / f"{model}.pkl"
    mock_data = pickle.loads(mock_path.read_bytes())
    user_message_count = sum(
        1
        for is_user_message, _ in itertools.groupby(
            messages, lambda msg: msg.role == "user"
        )
        if is_user_message
    )
    # 1 user message means turn 0
    # 2 user messages means turn 1
    # etc.
    return mock_data["turns"][user_message_count - 1]
