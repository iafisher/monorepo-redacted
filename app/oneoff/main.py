from lib import command
from iafisher_foundation.prelude import *


def main() -> None:
    # main_2025_07_06_rename_obsidian_files()
    todo()


# def main_2025_07_06_rename_obsidian_files() -> None:
#     import subprocess
#     from lib import obsidian

#     vault = obsidian.MAIN_VAULT

#     book_pattern = re.compile(r"^b([0-9]{4})\.([0-9]{2})")
#     film_pattern = re.compile(r"^f([0-9]{4})\.([0-9]{2})")
#     yyyy_mm_dd_pattern = re.compile(r"([0-9]{4})\.([0-9]{2})\.([0-9]{2})")
#     yyyy_mm_pattern = re.compile(r"([0-9]{4})\.([0-9]{2})")

#     def make_new_title(old_title: str) -> str:
#         sep = "-"
#         new_title = (
#             old_title.lower()
#             .replace(" - ", sep)
#             .replace(" + ", sep)
#             .replace("-", sep)
#             .replace("_", sep)
#             .replace(" v. ", f"{sep}v{sep}")
#             .replace(" vs. ", f"{sep}vs{sep}")
#             .replace(".js", "js")
#             .replace(" ", sep)
#             # precomposed and decomposed characters
#             .replace("é", "e")
#             .replace("é", "e")
#             .replace("è", "e")
#             .replace("è", "e")
#             .replace("á", "a")
#             .replace("á", "a")
#             .replace("–", sep)
#             .replace("½", f"{sep}1{sep}2")
#             .replace(",", "")
#             .replace("'", "")
#             .replace('"', "")
#             .replace("!", "")
#             .replace("?", "")
#             .replace("(", "")
#             .replace(")", "")
#             .replace("c++", "cpp")
#             .replace(".com", f"{sep}com")
#             .replace(".local", f"dot{sep}local")
#             .replace(f"{sep}2.0", f"{sep}2{sep}0")
#             .replace("metrics.cityquiz.io", f"metrics{sep}cityquiz{sep}io")
#         )
#         new_title = book_pattern.sub(rf"\1{sep}\2{sep}book", new_title)
#         new_title = film_pattern.sub(rf"\1{sep}\2{sep}film", new_title)
#         new_title = yyyy_mm_dd_pattern.sub(rf"\1{sep}\2{sep}\3", new_title)
#         new_title = yyyy_mm_pattern.sub(rf"\1{sep}\2", new_title)
#         try:
#             new_title.encode("ascii")
#         except:
#             print("ERROR (non ascii):", old_title)

#         if not re.match(r"^[a-zA-Z0-9@-]+$", new_title):
#             print("ERROR (bad char):", new_title)

#         return new_title

#     def prepend_after_properties(md: str, line: str) -> str:
#         # courtesy of chatgpt
#         lines = md.splitlines()
#         if lines and lines[0].strip() == "---":
#             # Look for closing ---
#             for i in range(1, len(lines)):
#                 if lines[i].strip() == "---":
#                     insert_at = i + 1
#                     break
#             else:
#                 # No closing --- found, treat as no frontmatter
#                 insert_at = 0
#         else:
#             insert_at = 0

#         return "\n".join(lines[:insert_at] + [line] + lines[insert_at:])

#     film_book_pat = re.compile(r"[BF][0-9]{4}\.[0-9]{2} ")

#     def do_rename(old_path: pathlib.Path) -> None:
#         old_title = old_path.stem
#         new_title = make_new_title(old_title)

#         if old_title == new_title:
#             return

#         print(f"{old_title} --> {new_title}")
#         new_path = old_path.parent / (new_title + ".md")
#         prel = old_path.relative_to(vault)
#         # horrible hack to deal with macOS case insensitivity causing problems with, e.g., "2024q1"
#         prel = prel.parent.parent / prel.parent.name.replace("q", "Q") / prel.name
#         subprocess.run(
#             [
#                 "git",
#                 "-C",
#                 str(vault),
#                 "mv",
#                 str(prel),
#                 str(new_path.relative_to(vault)),
#             ],
#             check=True,
#         )
#         # old_path.rename(new_path)

#         text = new_path.read_text()
#         try:
#             page_title = obsidian.split_dated_title(old_title)[1]
#         except KgError:
#             page_title = old_title

#         m = film_book_pat.match(page_title)
#         if m:
#             page_title = page_title[m.span()[1] :]

#         page_title = page_title[0].capitalize() + page_title[1:]
#         if page_title == "Journal":
#             page_title = ""

#         if page_title != "":
#             text = prepend_after_properties(text, f"# {page_title}\n")
#             new_path.write_text(text)

#         obsidian.update_all_links(
#             old_title=old_title, new_title=new_title, preserve_text=True, vault=vault
#         )

#     all_paths = list(obsidian.iter_md_files(vault=vault))
#     for path in all_paths:
#         do_rename(path)

#     for path in all_paths:
#         text = path.read_text()
#         if not text.endswith("\n"):
#             path.write_text(text + "\n")

#     for root, dirnames, _ in os.walk(vault):
#         dirnames[:] = [d for d in dirnames if not d.startswith(".")]
#         for dirname in dirnames:
#             new_name = dirname.lower().replace(" ", "-")
#             if new_name == dirname:
#                 continue

#             print(f"{dirname}/ --> {new_name}/")
#             os.rename(os.path.join(root, dirname), os.path.join(root, new_name))


if __name__ == "__main__":
    command.dispatch(command.Command.from_function(main))
