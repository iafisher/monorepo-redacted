"""
Opinionated helpers for creating web server applications with Flask.

Typical usage:

    app = webserver.make_app("myapp", file=__file__)
    TEMPLATE = webserver.make_template(title="My App", static_file_name="myapp")

    @app.route("/")
    def main_page():
        return render_template_string(TEMPLATE)

    cmd = webserver.make_command(app)

"""

from typing import Annotated, TypeVar

from iafisher_foundation.prelude import *
from lib import command, kgjson, pdb

import flask
from flask.json.provider import DefaultJSONProvider


def make_command(
    app: flask.Flask, *, help: str = "Run the webserver.", default_port: int = 5000
) -> command.Command:
    """
    Make a command to run the webserver.
    """

    def main_run(
        *,
        debug: Annotated[
            bool, command.Extra(help="Run the server in debug mode.")
        ] = False,
        testdb: Annotated[
            bool, command.Extra(help="Run against the test database.")
        ] = False,
        port: int = default_port,
    ) -> None:
        if testdb:
            os.environ["KG_OVERRIDE_DB_NAME"] = pdb.DbName.TEST

        app.run(port=port, debug=debug, load_dotenv=False)

    return command.Command.from_function(main_run, help=help, less_logging=False)


def make_app(name: str, *, file: str) -> flask.Flask:
    """
    Make a Flask app.

    `file` should be passed in as `__file__`.
    """
    d = pathlib.Path(file).parent
    frontend_dir = _find_frontend_dir(d)
    static_folder = frontend_dir / "dist" / name

    app = flask.Flask(
        name, static_folder=static_folder, template_folder=d / "templates"
    )
    app.json = CustomJSONProvider(app)
    return app


def _find_frontend_dir(d: pathlib.Path) -> pathlib.Path:
    while True:
        if (d / "frontend" / "dist").exists():
            return d / "frontend"

        if d == d.parent:
            raise Exception("could not find frontend directory")

        d = d.parent


def json_response(o: kgjson.Base) -> flask.Response:
    return flask.Response(o.serialize(camel_case=True), mimetype="application/json")


@dataclass
class RpcOutput(kgjson.Base):
    output: Any


def json_response2(o: kgjson.Base) -> flask.Response:
    return flask.Response(
        RpcOutput(output=o).serialize(camel_case=True), mimetype="application/json"
    )


@dataclass
class RpcError(kgjson.Base):
    error: str


def json_response_error(error: str, *, status: int = 400) -> flask.Response:
    return flask.Response(
        RpcError(error=error).serialize(camel_case=True),
        status=status,
        mimetype="application/json",
    )


T = TypeVar("T", bound=kgjson.Base)


def request(cls: type[T]) -> T:
    return cls.deserialize(flask.request.get_json(), camel_case=True)


class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):  # type: ignore
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return DefaultJSONProvider.default(obj)


def make_template(*, title: str, static_file_name: str) -> str:
    """
    Make a template string that can be called with `render_template_string`.

    The template includes HTML boilerplate and imports the default JavaScript and CSS.
    """
    return TEMPLATE % dict(title=title, static_file_name=static_file_name)


TEMPLATE = """\
<!DOCTYPE html>

<html lang="en">

<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"/>

    <title>%(title)s</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='%(static_file_name)s.css') }}">
</head>

<body>
</body>

<script src="{{ url_for('static', filename='%(static_file_name)s.js') }}"></script>

</html>
"""
