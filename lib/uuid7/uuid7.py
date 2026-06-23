"""
Adapted from https://github.com/stevesimmons/uuid7

MIT License

Copyright (c) 2021, Stephen Simmons

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import time
import uuid

from iafisher_foundation.prelude import *


def uuid7() -> uuid.UUID:
    ms = time.time_ns() // 1_000_000
    rand_a = int.from_bytes(os.urandom(2))
    rand_b = int.from_bytes(os.urandom(8))
    uuid_bytes = uuidfromvalues(ms, rand_a, rand_b)

    uuid_int = int.from_bytes(uuid_bytes)
    return uuid.UUID(int=uuid_int)


def uuidfromvalues(unix_ts_ms: int, rand_a: int, rand_b: int) -> bytes:
    version = 0x07
    var = 2
    rand_a &= 0xFFF
    rand_b &= 0x3FFFFFFFFFFFFFFF

    final_bytes = unix_ts_ms.to_bytes(6)
    final_bytes += ((version << 12) + rand_a).to_bytes(2)
    final_bytes += ((var << 62) + rand_b).to_bytes(8)

    return final_bytes
