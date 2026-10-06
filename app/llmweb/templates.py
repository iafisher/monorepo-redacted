import subprocess
import tempfile

from iafisher import tabular
from iafisher.prelude import *
from lib import command, llm, pgdb


TABLE = "llmweb_templates"


@dataclass
class Template:
    template_name: str
    system_prompt: str
    default_model: str

    @classmethod
    def fetch_one(cls, db: pgdb.Connection, template_name: str) -> "Template":
        return db.fetch_one(
            f"""
            SELECT
              template_name,
              system_prompt,
              default_model
            FROM
              {TABLE}
            WHERE
              template_name = %(template_name)s
            """,
            dict(template_name=template_name),
            t=pgdb.t(Template),
        )

    @classmethod
    def fetch_all(cls, db: pgdb.Connection) -> List["Template"]:
        return db.fetch_all(
            f"""
            SELECT
              template_name,
              system_prompt,
              default_model
            FROM
              {TABLE}
            """,
            t=pgdb.t(Template),
        )

    @classmethod
    def insert(cls, db: pgdb.Connection, template: "Template") -> None:
        db.execute(
            f"""
            INSERT INTO {TABLE}(template_name, system_prompt, default_model)
            VALUES (%(template_name)s, %(system_prompt)s, %(default_model)s)
            """,
            dict(
                template_name=template.template_name,
                system_prompt=template.system_prompt,
                default_model=template.default_model,
            ),
        )

    @classmethod
    def update_system_prompt(
        cls, db: pgdb.Connection, template_name: str, system_prompt: str
    ) -> None:
        db.execute(
            f"""
            UPDATE {TABLE}
            SET system_prompt = %(system_prompt)s
            WHERE template_name = %(template_name)s
            """,
            dict(system_prompt=system_prompt, template_name=template_name),
        )

    @classmethod
    def update_default_model(
        cls, db: pgdb.Connection, template_name: str, default_model: str
    ) -> None:
        db.execute(
            f"""
            UPDATE {TABLE}
            SET default_model = %(default_model)s
            WHERE template_name = %(template_name)s
            """,
            dict(default_model=default_model, template_name=template_name),
        )


def main_create(template_name: str, *, default_model: str = "") -> None:
    if default_model:
        default_model = llm.canonicalize_model_name(default_model)

    system_prompt = compose_in_editor("")
    template = Template(
        template_name=template_name,
        system_prompt=system_prompt,
        default_model=default_model,
    )
    with pgdb.connect() as db:
        Template.insert(db, template)


def main_edit_model(template_name: str, *, default_model: str) -> None:
    if default_model:
        default_model = llm.canonicalize_model_name(default_model)

    with pgdb.connect() as db:
        Template.update_default_model(db, template_name, default_model)


def main_edit_prompt(template_name: str) -> None:
    with pgdb.connect() as db:
        template = Template.fetch_one(db, template_name)
        new_system_prompt = compose_in_editor(template.system_prompt)
        Template.update_system_prompt(db, template.template_name, new_system_prompt)


def main_list() -> None:
    with pgdb.connect() as db:
        templates = Template.fetch_all(db)
        if len(templates) == 0:
            print("No templates in database.")
        else:
            table = tabular.Table()
            table.header(["template", "prompt", "model"])
            for template in templates:
                prompt_word_count = len(template.system_prompt.split())
                table.row(
                    [
                        template.template_name,
                        pluralize(prompt_word_count, "word"),
                        template.default_model,
                    ]
                )
            table.flush()
            print()
            print(f"{pluralize(len(templates), 'template')} found.")


def main_show(template_name: str) -> None:
    with pgdb.connect() as db:
        template = Template.fetch_one(db, template_name)
        print("Default model: ", template.default_model or "<unset>")
        print()
        print(f"<system>\n{template.system_prompt}\n</system>")


def compose_in_editor(initial: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir) / "tmp.txt"
        if initial:
            path.write_text(initial)

        subprocess.run([os.environ["EDITOR"], path], check=True)

        text = path.read_text()
        if not text:
            bail("Aborted.")
        else:
            return text


cmd = command.Group(help="Manage chat templates.")
cmd.add2("create", main_create, help="Create a new template.")
edit_cmd = command.Group(help="Edit an existing template.")
edit_cmd.add2("model", main_edit_model, help="Edit a template's default model.")
edit_cmd.add2("prompt", main_edit_prompt, help="Edit a template's system prompt.")
cmd.add("edit", edit_cmd)
cmd.add2("list", main_list, help="List existing templates.")
cmd.add2("show", main_show, help="Show an existing template.")
