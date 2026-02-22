from iafisher_foundation.prelude import *
from lib import kghttp

# Documentation: https://github.com/HackerNews/API
BASE_URL = "https://hacker-news.firebaseio.com/v0"


def fetch_top_story_ids() -> List[int]:
    return kghttp.get(f"{BASE_URL}/topstories.json").json()


def fetch_item(item_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetches an item (story or comment).

    Key fields:

    - `title`, `url`, `score`, and `descendants` (number of comments) for stories
    - `text` for comments
    - `by` and `kids` for both
    """
    # 2025-11-17: Why `Optional`? Observed that this endpoint may return `null`.
    return kghttp.get(f"{BASE_URL}/item/{item_id}.json").json()
