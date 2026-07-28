from lib import kgjson
from iafisher.prelude import *


@dataclass
class State(kgjson.Base):
    latest_zulip_message_id: Optional[int]
