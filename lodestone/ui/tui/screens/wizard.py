import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    Static,
)

from lodestone.core import providers
from lodestone.core.manager import ServerManager
from lodestone.ui.tui.messages import ServerCreated

logger = logging.getLogger("lodestone")
SERVERS_PATH = Path.cwd() / "Servers"


class ServerWizard(Screen):
    CSS_PATH = "../styles/wizard.tcss"

    def __init__(self, server_manager: ServerManager) -> None:
        super().__init__()
        self.server_manager = server_manager
        self.server_name = None
        self.software = None
        self.game_version = None

    def compose(self) -> ComposeResult:
        yield Button("Cancel", id="cancel-button", compact=True)
        with ContentSwitcher(id="wizard", initial="name-selection") as self.wizard_step:
            with Container(id="name-selection"):
                yield Static("Choose a name for your server")
                yield Input(placeholder="Survival1")
                yield Label("", id="error-label")
            with Container(id="software-selection"):
                yield Static("Choose a server software for your server")
                with RadioSet(id="chosen_software"):
                    yield RadioButton("Paper", name="paper")
                    yield RadioButton("Vanilla", name="vanilla")
                yield Button("Next", id="next")
            with Container(id="version-selection"):
                yield Static("Choose a Minecraft version")
                yield Input(placeholder="1.12.2")
                yield Label("", id="error-label2")
            with Container(id="download-bar"):
                yield ProgressBar(id="download-progress")

    @work(thread=True)
    def install_server(self) -> None:
        if (
            self.server_name is None
            or self.software is None
            or self.game_version is None
        ):
            logger.error("Missing server creation parameters")
            return

        try:
            created = self.server_manager.create_server(
                self.server_name,
                self.software,
                self.game_version,
                self.make_progress,
                SERVERS_PATH,
            )
            created.accept_eula()
            self.post_message(ServerCreated(created))
        except Exception as e:
            logger.error(f"Error creating server: {e}")
            self.app.notify(f"Error: {e}", severity="error")
        finally:
            self.app.call_from_thread(self.app.pop_screen)

    def make_progress(self, downloaded: int, total: int | None) -> None:
        self.app.call_from_thread(
            self.query_one("#download-progress", ProgressBar).update,
            total=total,
            progress=downloaded,
        )

    def on_mount(self) -> None:
        wizard = self.query_one("#wizard")
        wizard.border_title = "Server Creation"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.server_name:
            input_val = event.value.strip()
            if input_val != "" and input_val not in self.server_manager.names():
                self.server_name = input_val
                self.wizard_step.current = "software-selection"
                logger.info(f"Chosen name : {self.server_name}")
            else:
                logger.info("Not valid name")
                self.query_one("#error-label", Label).update(
                    "Please choose a valid unique name"
                )
        elif not self.game_version:
            input_val = event.value.strip()
            if self.software is None:
                return
            provider = providers.get_provider(self.software)
            if provider.version_exists(input_val):
                self.game_version = input_val
                self.wizard_step.current = "download-bar"
                logger.info(f"Chosen version: {self.game_version}")
                self.install_server()
            else:
                self.query_one("#error-label2", Label).update(
                    "Please choose a valid game version"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            selected_button = self.query_one(
                "#chosen_software", RadioSet
            ).pressed_button
            if selected_button is not None:
                self.software = selected_button.name
                logger.info(f"Chosen software : {self.software}")
                self.wizard_step.current = "version-selection"
        elif event.button.id == "cancel-button":
            self.app.pop_screen()
