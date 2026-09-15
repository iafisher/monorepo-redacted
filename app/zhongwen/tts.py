import asyncio

import edge_tts

from iafisher.prelude import *

VOICE = "zh-CN-XiaoxiaoNeural"


def save_mp3(hanzi: str, path: pathlib.Path) -> None:
    asyncio.run(_save_mp3_async(hanzi, path))


async def _save_mp3_async(hanzi: str, path: pathlib.Path) -> None:
    LOG.info("start: generating audio: %s", hanzi)
    await edge_tts.Communicate(hanzi, VOICE).save(path.as_posix())
    LOG.info("end:   generating audio: %s", hanzi)
