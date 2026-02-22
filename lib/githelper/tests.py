from lib.testing import *

from .githelper import BlameLine, _blame


class Test(Base):
    def test_git_blame(self):
        lines = _blame(GIT_BLAME_OUTPUT)
        self.assertEqual(
            BlameLine(
                commit_hash="3561c9449331d8e50ebbc42a6a7eb7f84c2caff4",
                commit_time_epoch_secs=1743864557,
                line="- [ ] CS644: week 6 homework solutions\n",
            ),
            lines[0],
        )
        self.assertEqual(
            BlameLine(
                commit_hash="3561c9449331d8e50ebbc42a6a7eb7f84c2caff4",
                commit_time_epoch_secs=1743864557,
                line="- [ ] CS644: week 7 homework solutions\n",
            ),
            lines[1],
        )
        self.assertEqual(
            BlameLine(
                commit_hash="3561c9449331d8e50ebbc42a6a7eb7f84c2caff4",
                commit_time_epoch_secs=1743864557,
                line="- [ ] CS644: week 8 lecture\n",
            ),
            lines[2],
        )
        self.assertEqual(
            BlameLine(
                commit_hash="3561c9449331d8e50ebbc42a6a7eb7f84c2caff4",
                commit_time_epoch_secs=1743864557,
                line="- [ ] CS644: decide on content for weeks 9 and 10\n",
            ),
            lines[3],
        )
        self.assertEqual(
            BlameLine(
                commit_hash="a85d239c383840daa9b557d76923b2d50ed1788d",
                commit_time_epoch_secs=1743938931,
                line="\n",
            ),
            lines[4],
        )
        self.assertEqual(
            BlameLine(
                commit_hash=None,
                commit_time_epoch_secs=None,
                line="\n",
            ),
            lines[5],
        )
        self.assertEqual(
            BlameLine(
                commit_hash=None,
                commit_time_epoch_secs=None,
                line="## test\n",
            ),
            lines[6],
        )
        self.assertEqual(7, len(lines))


GIT_BLAME_OUTPUT = """\
3561c9449331d8e50ebbc42a6a7eb7f84c2caff4 1 1 4
author vaultsnapshot
author-mail <vaultsnapshot@iafisher.com>
author-time 1743864557
author-tz -0400
committer vaultsnapshot
committer-mail <vaultsnapshot@iafisher.com>
committer-time 1743864557
committer-tz -0400
summary automatic snapshot (1 mod)
previous 7308ed2c3b3dc8611dd2e8500c9e5a4e280180f6 Scratchpad.md
filename Scratchpad.md
\t- [ ] CS644: week 6 homework solutions
3561c9449331d8e50ebbc42a6a7eb7f84c2caff4 2 2
\t- [ ] CS644: week 7 homework solutions
3561c9449331d8e50ebbc42a6a7eb7f84c2caff4 3 3
\t- [ ] CS644: week 8 lecture
3561c9449331d8e50ebbc42a6a7eb7f84c2caff4 4 4
\t- [ ] CS644: decide on content for weeks 9 and 10
a85d239c383840daa9b557d76923b2d50ed1788d 5 5 7
author vaultsnapshot
author-mail <vaultsnapshot@iafisher.com>
author-time 1743938931
author-tz -0400
committer vaultsnapshot
committer-mail <vaultsnapshot@iafisher.com>
committer-time 1743938931
committer-tz -0400
summary automatic snapshot (2 mod)
previous 820bd5efda9fae568d5a96a416af69754c10eb2c Scratchpad.md
filename Scratchpad.md
\t
0000000000000000000000000000000000000000 27 27 2
author Not Committed Yet
author-mail <not.committed.yet>
author-time 1743947439
author-tz -0400
committer Not Committed Yet
committer-mail <not.committed.yet>
committer-time 1743947439
committer-tz -0400
summary Version of Scratchpad.md from Scratchpad.md
previous 73806c16379bf13bb19647f4e2f1400206896fa2 Scratchpad.md
filename Scratchpad.md
\t
0000000000000000000000000000000000000000 28 28
\t## test
"""
