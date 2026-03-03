from flask import render_template_string

from app.bookmarks import models, rpc
from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *  # noqa: F401
from lib import dblog, pdb, webserver


app = webserver.make_app("bookmarks", file=__file__)
TEMPLATE = webserver.make_template(title="kg: bookmarks", static_file_name="bookmarks")


T = models.Bookmark.T


# TODO(2026-02): Use `webserver.json_response2`.


@app.route("/")
def main_page():
    return render_template_string(TEMPLATE)


@app.route("/api/load", methods=["GET"])
def api_load():
    with pdb.connect() as db:
        bookmarks = fetch_bookmarks(db)
        return webserver.json_response(rpc.LoadResponse(bookmarks=bookmarks))


def fetch_bookmarks(
    db: pdb.Connection, *, include_archived_bookmark_id: int = -1
) -> List[rpc.Bookmark]:
    # necessary to order by both `time_created` and `bookmark_id` as the former is not guaranteed
    # to be unique (and indeed is often _not_ unique)
    return db.fetch_all(
        pdb.SQL(
            """
            SELECT {star}
            FROM {table}
            WHERE {time_archived} IS NULL
                OR {bookmark_id} = %(bookmark_id)s
            ORDER BY {time_created} DESC, {bookmark_id} DESC
            """
        ).format(
            star=T.star,
            table=T.table,
            time_archived=T.time_archived,
            bookmark_id=T.bookmark_id,
            time_created=T.time_created,
        ),
        dict(bookmark_id=include_archived_bookmark_id),
        t=pdb.t(rpc.Bookmark),
    )


@app.route("/api/update", methods=["POST"])
def api_update():
    req = webserver.request(rpc.UpdateRequest)
    with pdb.connect() as db:
        T = models.Bookmark.T
        db.execute(
            pdb.SQL(
                """
                UPDATE {table}
                SET {title} = %(title)s,
                    {url} = %(url)s,
                    {reading_time} = %(reading_time)s,
                    {appeal} = %(appeal)s,
                    {tags} = %(tags)s
                WHERE {bookmark_id} = %(bookmark_id)s
                """
            ).format(
                table=T.table,
                title=T.title,
                url=T.url,
                reading_time=T.reading_time,
                appeal=T.appeal,
                tags=T.tags,
                bookmark_id=T.bookmark_id,
            ),
            dict(
                bookmark_id=req.bookmark_id,
                title=req.title,
                url=req.url,
                reading_time=req.reading_time,
                appeal=req.appeal,
                tags=req.tags,
            ),
        )
        bookmarks = fetch_bookmarks(db)
        return webserver.json_response(rpc.LoadResponse(bookmarks=bookmarks))


@app.route("/api/archive", methods=["POST"])
def api_archive():
    req = webserver.request(rpc.ArchiveRequest)
    time_archived = timehelper.now()

    with pdb.connect() as db:
        T = models.Bookmark.T
        title = db.fetch_val(
            pdb.SQL(
                """
                UPDATE {table}
                SET {reason_archived} = %(reason_archived)s,
                    {time_archived} = %(time_archived)s
                WHERE {bookmark_id} = %(bookmark_id)s
                RETURNING {title}
                """
            ).format(
                table=T.table,
                reason_archived=T.reason_archived,
                time_archived=T.time_archived,
                bookmark_id=T.bookmark_id,
                title=T.title,
            ),
            dict(
                bookmark_id=req.bookmark_id,
                reason_archived=req.reason,
                time_archived=time_archived,
            ),
        )
        dblog.log(
            "bookmark_archived",
            dict(
                bookmark_id=req.bookmark_id,
                title=title,
                reason_archived=req.reason,
            ),
        )
        bookmarks = fetch_bookmarks(db, include_archived_bookmark_id=req.bookmark_id)
        return webserver.json_response(rpc.LoadResponse(bookmarks=bookmarks))


@app.route("/api/unarchive", methods=["POST"])
def api_unarchive():
    req = webserver.request(rpc.UnarchiveRequest)

    with pdb.connect() as db:
        T = models.Bookmark.T
        title = db.fetch_val(
            pdb.SQL(
                """
                UPDATE {table}
                SET {reason_archived} = '',
                    {time_archived} = NULL
                WHERE {bookmark_id} = %(bookmark_id)s
                RETURNING {title}
                """
            ).format(
                table=T.table,
                reason_archived=T.reason_archived,
                time_archived=T.time_archived,
                bookmark_id=T.bookmark_id,
                title=T.title,
            ),
            dict(bookmark_id=req.bookmark_id),
        )
        dblog.log(
            "bookmark_unarchived",
            dict(bookmark_id=req.bookmark_id, title=title),
        )
        bookmarks = fetch_bookmarks(db)
        return webserver.json_response(rpc.LoadResponse(bookmarks=bookmarks))


cmd = webserver.make_command(app)
