import json
import logging
from collections.abc import Callable
from pathlib import Path
from shutil import rmtree

from lodestone.core import providers
from lodestone.core.server import Server


class ServerManager:
    def __init__(self, servers_path: Path):
        self.servers_path = servers_path
        self.servers: dict[str, Server] = {}
        self.load_all_from_path()

    def __getitem__(self, name: str) -> Server:
        return self.servers[name]

    def __iter__(self):
        return iter(self.servers.values())

    def __len__(self):
        return len(self.servers)

    def names(self):
        return self.servers.keys()

    def values(self):
        return self.servers.values()

    def load_all_from_path(self):
        # self.servers.clear()

        if not self.servers_path.exists():
            return

        for directory in self.servers_path.iterdir():
            self.load_from_path(directory)

    def load_from_server_instance(self, server: Server):
        self.servers[server.name] = server

    def load_from_path(self, directory: Path) -> Server | None:
        if not directory.is_dir():
            logging.warning("Couldn't find folder")
            return None

        manifest = directory / "lodestone-manifest.json"
        if not manifest.exists():
            logging.warning("Couldn't find manifest")
            return None

        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))

            server = Server(
                data["name"],
                data["software"],
                data["game_version"],
                directory,
            )
            try:
                server.properties = server.properties_to_dict()
            except FileNotFoundError as e:
                logging.warning(e)

            self.load_from_server_instance(server)
            return server

        except (KeyError, json.JSONDecodeError):
            logging.warning("Coulnd't read the manifest")
            return None

    ProgressCb = Callable[[int, int | None], None]

    def create_server(
        self,
        name: str,
        software: str,
        game_version: str,
        progress: ProgressCb,
        servers_path: Path,
    ) -> Server:
        server_path = servers_path / name
        server_path.mkdir(parents=True, exist_ok=True)

        server = Server(name, software, game_version, server_path)

        self.load_from_server_instance(server)

        manifest = {
            "schema": 1,
            "name": name,
            "software": software,
            "game_version": game_version,
        }

        (server_path / "lodestone-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        try:
            provider = providers.get_provider(software)
            provider.download_jar(game_version, server_path, progress)
        except ValueError as e:
            raise RuntimeError(f"[yellow]{e}") from e
        except InterruptedError:
            rmtree(server_path)

        (server_path / "server.properties").write_text(
            "# Managed by Lodestone-server-manager"
        )

        return server

    def delete_server(self, name: str):
        if name not in self.names():
            raise RuntimeError("No server with that name.")

        try:
            rmtree(self[name].path)
        except Exception as err:
            raise RuntimeError("Couldn't find server's directory") from err

        del self.servers[name]
