import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from lodestone.core.manager import ServerManager
from lodestone.core.server import ServerState
from lodestone.ui.tui.messages import ServerCreated, ServerDeleted
from lodestone.ui.tui.screens.home import HomeScreen, ServerListing

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("tui.log", encoding="utf-8"),
    ],
    force=True,
)

logger = logging.getLogger("lodestone")


class Lodestone(App):
    HORIZONTAL_BREAKPOINTS = [
        (0, "-narrow"),
        (60, "-normal"),
        (85, "-wide"),
        (120, "-very-wide"),
    ]
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def __init__(self):
        super().__init__()
        self.SERVERS_PATH = Path.cwd() / "Servers"
        self.server_manager = ServerManager(self.SERVERS_PATH)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        self.home_screen = HomeScreen(self.server_manager)
        self.push_screen(self.home_screen)

    def on_server_created(self, event: ServerCreated) -> None:
        try:
            listing = self.home_screen.query_one(ServerListing)
            listing.on_server_created(event)
        except Exception:
            pass

    def on_server_deleted(self, event: ServerDeleted) -> None:
        try:
            listing = self.home_screen.query_one(ServerListing)
            listing.on_server_deleted(event)
        except Exception:
            pass

    def on_unmount(self) -> None:
        for s in self.server_manager.values():
            if s.state == ServerState.RUNNING:
                s.stop()
                logging.info("Stopped %s", s.name)

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )


if __name__ == "__main__":
    Lodestone().run()
