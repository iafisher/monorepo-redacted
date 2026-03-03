from collections import defaultdict

from app.habits import models
from app.habits.common import create_habit_entry, fetch_habit_entries, fetch_habits
from lib import dblog, pdb, webserver
from iafisher_foundation.prelude import *

from flask import jsonify, render_template_string, request


app = webserver.make_app("habits", file=__file__)


TEMPLATE = webserver.make_template(title="kg: habits", static_file_name="habits")


@app.route("/")
def main_page():
    return render_template_string(TEMPLATE)


@app.route("/api/load", methods=["GET"])
def api_load():
    with pdb.connect() as db:
        habits = fetch_habits(db)
        habit_entries = fetch_habit_entries(db, last_filter=datetime.timedelta(days=14))

    categories_dict: defaultdict[str, List[models.Habit]] = defaultdict(list)
    for habit in sorted(habits, key=lambda habit: (-habit.points, habit.name)):
        categories_dict[habit.category or "Uncategorized"].append(habit)

    categories = [
        dict(name=key, habits=value)
        for key, value in sorted(categories_dict.items(), key=lambda kv: kv[0])
    ]
    return jsonify({"categories": categories, "entries": habit_entries})


@app.route("/api/create", methods=["POST"])
def api_create():
    data = request.get_json()
    with pdb.connect() as db:
        create_habit_entry(
            db, datetime.date.fromisoformat(data["date"]), data["habit"], data["points"]
        )
        dblog.log("habit_created", dict(date=data["date"], habit=data["habit"]))

    return jsonify({"ok": True})


@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json()
    with pdb.connect() as db:
        table = models.HabitEntry.T.table
        db.execute(
            pdb.SQL(
                """
                    DELETE FROM ONLY {table}
                    WHERE ctid IN (
                        SELECT ctid FROM {table} WHERE habit = %(habit)s AND date = %(date)s
                        ORDER BY time_created DESC LIMIT 1
                    )
                """
            ).format(table=table),
            dict(habit=data["habit"], date=data["date"]),
        )
        dblog.log("habit_deleted", dict(date=data["date"], habit=data["habit"]))

    return jsonify({"ok": True})


cmd = webserver.make_command(app)
