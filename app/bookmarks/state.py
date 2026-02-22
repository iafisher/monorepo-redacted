from lib import kgjson
from iafisher_foundation.prelude import *


@dataclass
class State(kgjson.Base):
    latest_zulip_message_id: Optional[int]
