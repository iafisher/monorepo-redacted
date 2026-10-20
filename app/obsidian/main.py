from lib import command

from app.obsidian import create_journal, notes, plugins, snapshot, tidy


cmd = command.Group(help="Umbrella command for managing Obsidian.")
cmd.add("create-journal", create_journal.cmd)
cmd.add("notes", notes.cmd)
cmd.add("plugins", plugins.cmd)
cmd.add("snapshot", snapshot.cmd)
cmd.add("tidy", tidy.cmd)

if __name__ == "__main__":
    command.dispatch(cmd)
