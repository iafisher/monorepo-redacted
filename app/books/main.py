import dataclasses
import re
from typing import Annotated

from app.books import models
from iafisher_foundation import tabular, timehelper
from iafisher_foundation.prelude import *
from lib import command, dblog, humanunits, obsidian, pdb


def main_list(
    *, year_filter: Annotated[Optional[int], command.Extra(name="-year")]
) -> None:
    book_models: List[models.Book] = []
    with pdb.connect() as db:
        T = models.Book.T
        if year_filter is not None:
            book_models = db.fetch_all(
                pdb.SQL("SELECT {} FROM {} WHERE EXTRACT(YEAR FROM {}) = %s").format(
                    T.star, T.table, T.date_started
                ),
                (year_filter,),
                t=pdb.t(models.Book),
            )
        else:
            book_models = db.fetch_all(
                pdb.SQL("SELECT {} FROM {}").format(T.star, T.table),
                t=pdb.t(models.Book),
            )

    table = tabular.Table()
    for book_model in book_models:
        if year_filter is not None:
            fmt = "%b %-d"
            date_started = book_model.date_started.strftime(fmt)
            date_finished = (
                book_model.date_finished.strftime(fmt)
                if book_model.date_finished is not None
                else None
            )
        else:
            date_started = book_model.date_started.isoformat()
            date_finished = (
                book_model.date_finished.isoformat()
                if book_model.date_finished is not None
                else None
            )

        table.row(
            [
                book_model.title,
                book_model.author,
                date_started,
                date_finished or "",
                book_model.pages or "",
            ]
        )

    table.flush()


def main_sync(
    *,
    quiet: Annotated[bool, command.Extra(help="print less output")],
    write: Annotated[
        bool, command.Extra(help="write to database instead of doing a dry run")
    ],
) -> None:
    book_models, warnings = parse_books_from_obsidian_vault()
    for warning in warnings:
        print(f"warning: {warning}")

    if write:
        with pdb.connect() as db:
            table = models.Book.T.table
            db.execute(pdb.SQL("DELETE FROM {}").format(table))
            db.execute_many(
                pdb.SQL("INSERT INTO {}({}) VALUES({})").format(
                    table, models.Book.T.star, models.Book.T.placeholders
                ),
                [dataclasses.asdict(model) for model in book_models],
            )
            dblog.log("books_synced", dict(count=len(book_models)))
    else:
        if not quiet:
            for book_model in book_models:
                print(book_model)

            print()

        print(
            f"Would have written {pluralize(len(book_models), 'row')}. "
            + "Re-run with -write to write to database."
        )

    if len(warnings) > 0:
        sys.exit(1)


def parse_books_from_obsidian_vault() -> Tuple[List[models.Book], List[str]]:
    book_models: List[models.Book] = []
    warnings: List[str] = []
    for note_path, year in get_obsidian_note_paths():
        loop_book_models, loop_warnings = parse_books_from_obsidian_note(
            note_path, note_year=year
        )
        book_models.extend(loop_book_models)
        warnings.extend(loop_warnings)
    return book_models, warnings


entry_pattern = lazy_re(
    r"""
    ^
    # numbered list items
    [0-9]+\.
    \s*
    # some entries have a '+' or '-' rating, e.g., '+++' for a very good book
    (?:[➕➖\+-]*)?
    \s*
    # title is italicized
    \*
    (?:
      # title may be a link...
      \[\[[^|]+\|(?P<title1>[^\]]+)\]\]
      |
      # or a bare title
      (?P<title2>[^\*]+)
    )
    \*
    \s+
    by
    \s+
    (?P<author>[^(]+)
    # a '(ed.)' parenthetical
    (?P<is_editor>
        \s+
        # 'ed.' or 'eds.' OK
        \(eds?\.\)
    )?
    \s+
    \((?P<start_month>[A-Za-z]+)
    \s+
    (?P<start_day>[0-9]+)
    # `end` is optional, 'Jun 2' means started and finished on same day
    (?P<end>
      # if start and end month are the same, then end month is omitted
      –(?P<end_day1>[0-9]+)
      |
      \s*–\s*(?P<end_month>[A-Za-z]+)\s+(?P<end_day2>[0-9]+)
      |
      # if book is in progress, end date is omitted
      –
    )?
    # number of pages is optional
    (?:
        ,
        \s+
        (?P<pages>[0-9]+)
        \s+
        pp\.
    )?
    # allow arbitrary content at end of parentheses
    .*
    \)
    """,
    re.VERBOSE,
)


def parse_books_from_obsidian_note(
    note_path: pathlib.Path, *, note_year: int
) -> Tuple[List[models.Book], List[str]]:
    book_models: List[models.Book] = []
    warnings: List[str] = []
    last_successful_lineno = None
    last_line_was_blank = True
    for lineno, line in enumerate(note_path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            last_line_was_blank = True
            continue

        if line.startswith(("## Abandoned", "## Skimmed")):
            break

        book_model_opt = parse_one_line(line, note_year=note_year)
        if book_model_opt is not None:
            last_successful_lineno = lineno
            book_models.append(book_model_opt)
        else:
            if (
                not last_line_was_blank
                or (
                    last_successful_lineno is not None
                    and last_successful_lineno != lineno - 1
                )
            ) and "❮" not in line:
                warnings.append(f"could not parse line {lineno}: {line!r}")

        last_line_was_blank = False
    return book_models, warnings


def parse_one_line(line: str, *, note_year: int) -> Optional[models.Book]:
    m = entry_pattern.get().match(line)
    if not m:
        return None

    title = m.group("title1") or m.group("title2")
    author = m.group("author")
    if m.group("is_editor") is not None:
        author += " (ed.)"

    start_month = m.group("start_month")
    start_day = int(m.group("start_day"))
    date_started = datetime.date(
        year=note_year, month=humanunits.month_to_int(start_month), day=start_day
    )
    end = m.group("end")
    if end == "–":
        date_finished = None
    elif end is None:
        date_finished = date_started
    else:
        end_month = m.group("end_month") or start_month
        end_day = int(m.group("end_day1") or m.group("end_day2"))
        date_finished = datetime.date(
            year=note_year, month=humanunits.month_to_int(end_month), day=end_day
        )
        if date_finished < date_started:
            if date_started.month >= 11 and date_finished.month <= 3:
                # e.g., Dec 29–Jan 2
                # Assume that 'Jan 2' refers to the next year.
                date_finished = date_finished.replace(year=date_finished.year + 1)
            else:
                raise KgError(
                    "book entry has a finished date that is earlier than the date started",
                    line=line,
                    date_started=date_started,
                    date_finished=date_finished,
                )
    pages = int(m.group("pages")) if m.group("pages") else None

    return models.Book(
        title=title,
        author=author,
        date_started=date_started,
        date_finished=date_finished,
        pages=pages,
    )


earliest_year = 2014


def get_obsidian_note_paths() -> Generator[Tuple[pathlib.Path, int], None, None]:
    this_year = timehelper.now().year
    year = earliest_year
    vault = obsidian.Vault.main()
    while year <= this_year:
        yield vault.find_note(f"{year}-books")[0], year
        year += 1


cmd = command.Group(help="Manage books database.")
cmd.add2("list", main_list, help="List books.")
cmd.add2("sync", main_sync, help="Sync with Obsidian log.", less_logging=False)

if __name__ == "__main__":
    command.dispatch(cmd)
