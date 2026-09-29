from lib import command

from app.obsidian import (
    create_journal,
    fix_links,
    notes,
    plugins,
    snapshot,
    sweep,
    tidy,
    verify_links,
)


cmd = command.Group(help="Umbrella command for managing Obsidian.")
cmd.add("create-journal", create_journal.cmd)
cmd.add("fix-links", fix_links.cmd)
cmd.add("notes", notes.cmd)
cmd.add("plugins", plugins.cmd)
cmd.add("snapshot", snapshot.cmd)
cmd.add("sweep", sweep.cmd)
cmd.add("tidy", tidy.cmd)
cmd.add("verify-links", verify_links.cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
