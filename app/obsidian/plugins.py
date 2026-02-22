import json
from typing import Annotated

from iafisher_foundation import colors, tabular
from iafisher_foundation.prelude import *
from lib import command, githelper, obsidian


def main_install(
    path: pathlib.Path,
    *,
    vault: pathlib.Path = obsidian.Vault.main().path(),
    dry_run: bool = False,
) -> None:
    plugins_dir = vault / ".obsidian" / "plugins"

    install_from_path = path.absolute()
    install_to_path = plugins_dir / install_from_path.name

    if install_to_path.exists():
        raise KgError(
            "a plugin is already installed at that path", path=install_to_path
        )

    if not install_from_path.is_dir():
        raise KgError("plugin path should be a directory", path=install_from_path)

    def _file_exists(name: str) -> None:
        if not (install_from_path / name).exists():
            raise KgError(
                f"plugin directory should contain {name}", path=install_from_path
            )

    _file_exists("manifest.json")
    _file_exists("main.js")

    if dry_run:
        print(f"would have installed {install_from_path} at {install_to_path}")
    else:
        print(f"installed {install_from_path} at {install_to_path}")
        os.symlink(install_from_path, install_to_path, target_is_directory=True)


def main_list(
    *,
    vault: pathlib.Path = obsidian.Vault.main().path(),
    local: Annotated[bool, command.Extra(help="only list local plugins")] = False,
) -> None:
    plugins_dir = vault / ".obsidian" / "plugins"
    active_plugins = get_active_plugins(vault)

    table = tabular.Table()
    table.row(["name", "type", "active", "version"], color=colors.cyan)
    for p in plugins_dir.iterdir():
        if p.is_symlink():
            type_ = "local"
        elif p.is_dir():
            type_ = "external"
        else:
            continue

        if local and type_ != "local":
            continue

        details = get_plugin_details(p)
        if details.id in active_plugins:
            active = "yes"
        else:
            active = colors.red("no")

        table.row([colors.yellow(p.name), type_, active, details.version])

    table.sort("name")
    table.flush()


def main_uninstall(
    name: str, *, vault: pathlib.Path = obsidian.Vault.main().path()
) -> None:
    plugin_path = vault / ".obsidian" / "plugins" / name

    if not plugin_path.exists():
        raise KgError("plugin is not installed", path=plugin_path)

    plugin_path.unlink()


def get_active_plugins(vault: pathlib.Path) -> List[str]:
    with open(vault / ".obsidian" / "community-plugins.json") as f:
        return json.load(f)


@dataclass
class PluginDetails:
    id: str
    version: str


def get_plugin_details(plugin: pathlib.Path) -> PluginDetails:
    with open(plugin / "manifest.json") as f:
        manifest = json.load(f)

    version = manifest["version"]

    if githelper.is_in_repo(plugin) and githelper.are_there_uncommitted_changes(
        repo=plugin
    ):
        version += "*"

    return PluginDetails(id=manifest["id"], version=version)


cmd = command.Group(help="Manage Obsidian plugins.")
cmd.add2("install", main_install, help="Install a local plugin.")
cmd.add2("list", main_list, help="List installed plugins.")
cmd.add2("uninstall", main_uninstall, help="Uninstall a local plugin.")
