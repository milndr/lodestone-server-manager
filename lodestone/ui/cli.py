import cmd
import logging
import time
from pathlib import Path

from rich import print
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.prompt import Prompt
from rich.table import Table

from lodestone.core import providers
from lodestone.core.manager import ServerManager
from lodestone.core.server import ServerState

HEADERS = {"User-Agent": "lodestone-server-manager/0.0.1"}
SERVERS_PATH = Path.cwd() / "Servers"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
    force=True,
)
logger = logging.getLogger(__name__)
logger.info("logging initialized")


class Repl(cmd.Cmd):
    prompt = "> "

    def rich_progress(self, label: str):
        task_id = None

        progress = Progress(transient=True)

        def cb(done: int, total: int | None) -> None:
            nonlocal task_id

            if task_id is None:
                progress.start()
                task_id = progress.add_task(label, total=total)

            progress.update(task_id, completed=done)

            if total is not None and done >= total:
                progress.stop()

        return cb

    def __init__(self):
        super().__init__()
        logger.info("Started")
        self.server_manager = ServerManager(SERVERS_PATH)

    def do_list(self, _arg: str) -> None:
        """List all servers"""

        state_colors = {
            ServerState.STOPPED: "red",
            ServerState.STARTING: "yellow",
            ServerState.RUNNING: "green",
            ServerState.STOPPING: "yellow",
            ServerState.CRASHED: "dark_red",
        }

        software_colors = {
            "vanilla": "light_yellow3",
            "paper": "sky_blue2",
            "neoforge": "orange3",
            "purpur": "light_slate_blue",
        }

        table = Table(title="Minecraft Servers")
        table.add_column("Name")
        table.add_column("Software")
        table.add_column("Game version")
        table.add_column("State")
        table.add_column("Path")

        for s in self.server_manager.values():
            table.add_row(
                s.name,
                f"[{software_colors[s.software]}]{s.software.capitalize()}",
                s.game_version,
                f"[{state_colors[s.state]}]{s.state.value}",
                str(s.path),
            )

        console = Console()
        console.print(table)

    def do_create(self, arg: str):
        """create <name> <software> <game_version>"""
        try:
            name, software, game_version = arg.split()
        except ValueError:
            logger.warning("couldn't execute command")
            return

        if name in self.server_manager.names():
            return

        download_progress = self.rich_progress(f"{name} server.jar")

        self.server_manager.create_server(
            name, software, game_version, download_progress, SERVERS_PATH
        )

    # TODO: Refactor into multiple functions
    def do_wizard(self, _arg: None = None):
        """Wizard to create server"""
        name = None
        software = None
        game_version = None

        while True:
            print(
                "[dark_slate_gray1]Choose a name for you server.\n[cornflower_blue]Wizard [white]> ",
                end="",
            )
            name = input().strip()
            if name == "":
                print("[yellow]Please choose a valid name")
            elif name in self.server_manager.names():
                print("[yellow]Another server already has that name")
            else:
                break
        while True:
            print(
                "[dark_slate_gray1]Choose a software for you server (vanilla, paper)\n[cornflower_blue]Wizard [white]> ",
                end="",
            )
            software = input().strip()
            if software == "" or software.lower() not in ("vanilla", "paper"):
                print("[yellow]Please choose a valid server software (vanilla, paper)")
            else:
                break
        while True:
            print(
                '[dark_slate_gray1]Choose a Minecraft version for you server, type "list" for available versions for selected software\n[cornflower_blue]Wizard [white]> ',
                end="",
            )
            game_version = input().strip()
            if game_version == "list":
                self.do_list_versions(software)
                continue
            provider = providers.get_provider(software)
            if game_version == "" or not provider.version_exists(game_version):
                print("[yellow]Please choose a valid minecraft version.")
            else:
                break

        on_progress = self.rich_progress(f"{name} server.jar")

        self.server_manager.create_server(
            name, software, game_version, on_progress, SERVERS_PATH
        )

        while True:
            print(
                "[dark_slate_gray1]Do you agree with the EULA ? [green]y[bright_white]/[red]n [white](it is needed to play)\n[cornflower_blue]Wizard [white]> ",
                end="",
            )
            choise = input().strip()
            if choise == "y":
                self.server_manager[name].accept_eula()
                break
            if choise == "n":
                return
            print("[yellow]Please choose a valid choise.")
        while True:
            print(
                "[dark_slate_gray1]Do you want to start your server ? [green]y[bright_white]/[red]n [white]\n[cornflower_blue]Wizard [white]> ",
                end="",
            )
            choise = input().strip()
            if choise == "y":
                self.server_manager[name].start()
                break
            if choise == "n":
                return
            print("[yellow]Please choose a valid choise.")

    def do_start(self, arg: str):
        """start <server>"""
        if arg not in self.server_manager.names():
            print(f"[yellow]No server with name {arg}")
            return
        try:
            self.server_manager[arg].start()
            self.do_list(arg)
        except RuntimeError as e:
            print(f"[yellow]{e}")

    def do_console(self, arg: str):
        # if not self.is_running():
        #     raise RuntimeError("Server is not running!")

        if arg not in self.server_manager.names():
            print(f"[yellow]No server with name {arg}")
            return

        server = self.server_manager[arg]

        try:
            while server.state == ServerState.RUNNING:
                while not server.log_queue.empty():
                    print(server.log_queue.get())
                time.sleep(0.05)

                cmd = input(f"{server.name} (CTRL + D to quit) > ").strip()
                if not cmd:
                    continue

                server.send_command(cmd)

        except EOFError:
            print("Leaving console (server still running)")

        # self.stop_event.clear()
        # threading.Thread(target=self._print_logs, daemon=True).start()
        # logging.info("Started thread for print_logs")

        # try:
        #     while True:
        #         time.sleep(0.05)
        #         if self.is_running():
        #             cmd = input(f"{self.name} (CTRL + D to quit) > ").strip()
        #         else:
        #             return
        #         if cmd and self.is_running():
        #             self.send_command(cmd)
        #         # if cmd in ("stop", "restart"):
        #         #     time.sleep(3)
        #         #     self.state = ServerState.STOPPED
        #         #     self.stop_event.set()
        #         #     logging.info("Stopped threads")
        #         #     return
        #         else:
        #             return
        # except EOFError:
        #     self.stop_event.set()
        #     logging.info("Stopped threads")

    def do_stop(self, arg: str):
        """stop <server>"""
        if arg not in self.server_manager.names():
            print(f"[yellow]No server with name {arg}")
            return
        try:
            self.server_manager[arg].stop()
        except RuntimeError as e:
            print(f"[yellow]{e}")

    def do_delete(self, arg: str):
        if arg not in self.server_manager.names():
            print(f"[yellow]No server with name {arg}")
            return
        while True:
            choise = Prompt.ask(
                f"[red]Are you sure you want to delete server {arg} (y/n) ? (this action cannot be undone)\n> "
            ).strip()
            if choise == "y":
                self.server_manager.delete_server(arg)
                return
            if choise == "n":
                return
            print("[yellow]Please enter a valid answer (y/n).")

    def do_send(self, arg: str):
        """send <server> <command>"""
        name, *cmd = arg.split()
        if name not in self.server_manager.names():
            print(f"[yellow]No server with name {name}")
            return
        try:
            self.server_manager[name].send_command(" ".join(cmd))
        except RuntimeError as e:
            print(f"[yellow]{e}")

    def do_list_properties(self, arg: str):
        if arg not in self.server_manager.names():
            print(f"[yellow]No server with name {arg}")
            return

        table = Table(title=f"{arg} Properties")
        table.add_column("Property")
        table.add_column("Value")

        self.server_manager[arg].properties_to_dict()

        for k, v in self.server_manager[arg].properties.items():
            table.add_row(k, str(v))

        console = Console()
        console.print(table)

    def do_set_property(self, arg: str):
        """create <name> <property> <value>"""
        try:
            name, property, value = arg.split()
        except ValueError:
            logger.warning("couldn't execute command")
            return

        if name not in self.server_manager.names():
            print(f"[yellow]No server with name {name}")
            return

        try:
            self.server_manager[name].update_property(property, value)
            self.server_manager[name].properties_to_dict()
        except ValueError as e:
            print(f"[yellow]{e}")
        except KeyError as e:
            print(f"[yellow]{e}")

    def do_accept_eula(self, arg: str):
        """accept-eula <server>"""
        if arg not in self.server_manager.names():
            print(f"[yellow]No server with name {arg}")
            return
        self.server_manager[arg].accept_eula()
        print("[green]accepted eula")

    def do_list_versions(self, arg: str):
        """list-versions (paper)"""
        try:
            provider = providers.get_provider(arg)
            provider.list_versions()
        except ValueError as e:
            print(f"[yellow]{e}")

    def do_exit(self, _arg: None = None):
        """Exit"""
        for s in self.server_manager.values():
            if s.state == ServerState.RUNNING:
                s.stop()
                logging.info("Stopped %s", s.name)
        return True

    def do_get(self, _arg: str):
        print(self.server_manager["1"].properties_to_dict())
        print()

    def do_refresh(self, _arg: None = None):
        """Refresh servers registry"""
        self.server_manager = ServerManager(SERVERS_PATH)

    do_quit = do_exit
    do_EOF = do_exit
