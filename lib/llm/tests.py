from iafisher.prelude import *
from lib.testing import *

from .model_info import MODEL_TO_INFO


class Test(Base):
    def test_model_nicknames_unique(self):
        nicknames: Dict[str, str] = {}
        for this_model, info in MODEL_TO_INFO.items():
            for nickname in info.nicknames:
                existing_model = nicknames.get(nickname)
                if existing_model is not None:
                    raise KgError(
                        "nickname is not unique",
                        model1=existing_model,
                        model2=this_model,
                    )
                nicknames[nickname] = this_model
