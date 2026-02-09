import logging
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, HorizontalGroup, VerticalGroup, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    Digits,
    Footer,
    Header,
    Input,
    Label,
    ListView,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Static,
    Tab,
    Tabs,
)

from lodestone.core import providers
from lodestone.core.manager import ServerManager
from lodestone.core.server import Server, ServerState

SERVERS_PATH = Path.cwd() / "Servers"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("tui.log", encoding="utf-8"),
    ],
    force=True,
)

logger = logging.getLogger(__name__)
logger.info("Logging started")


class ServerCreated(Message):
    def __init__(self, server: Server) -> None:
        super().__init__()
        self.server = server


class ServerWizard(Screen):
    def __init__(self, server_manager: ServerManager) -> None:
        super().__init__()
        self.server_manager = server_manager
        self.server_name = None
        self.software = None
        self.game_version = None

    def compose(self) -> ComposeResult:
        with Container(id="wizard"):
            if not self.server_name:
                yield Static("Choose a name for your server")
                yield Input(placeholder="Survival1")
                yield Label("", id="error-label")
            elif not self.software:
                yield Static("Choose a server software for your server")
                with RadioSet(id="chosen_software"):
                    yield RadioButton("Paper", name="paper")
                    yield RadioButton("Vanilla", name="vanilla")
                yield Button("Next", id="next")
            elif not self.game_version:
                yield Static("Choose a Minecraft version")
                yield Input(placeholder="1.12.2")
                yield Label("", id="error-label2")
            else:
                yield ProgressBar(id="download-progress")
                self.install_server()

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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.server_name:
            input_val = event.value.strip()
            if input_val != "" and input_val not in self.server_manager.names():
                self.server_name = input_val
                logger.info(f"Chosen name : {self.server_name}")
            else:
                self.query_one("#error-label", Label).update(
                    "Please choose a valid unique name"
                )
            self.refresh(recompose=True)
        elif not self.game_version:
            input_val = event.value.strip()
            if self.software is None:
                return
            provider = providers.get_provider(self.software)
            if provider.version_exists(input_val):
                self.game_version = input_val
                logger.info(f"Chosen version: {self.game_version}")
            else:
                self.query_one("#error-label2", Label).update(
                    "Please choose a valid game version"
                )
            self.refresh(recompose=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            selected_button = self.query_one(
                "#chosen_software", RadioSet
            ).pressed_button
            if selected_button is not None:
                self.software = selected_button.name
                logger.info(f"Chosen software : {self.software}")
                self.refresh(recompose=True)


class ServerOverview(Static):
    def __init__(self, server: Server):
        super().__init__()
        self.server = server

    def compose(self):
        with Container(id="overview-grid"):
            with VerticalGroup(id="players-list"):
                yield Label("Players")
                yield ListView(id="player-list-view")

            with VerticalGroup(id="console"):
                yield Label("Console")
                yield RichLog(id="log", wrap=True)
                yield Input(id="input", placeholder="Enter a command")

            with VerticalGroup(id="actions"):
                yield Label("Actions")
                with Container(id="action-buttons"):
                    yield Button("Start", id="start", variant="success", compact=True)
                    yield Button(
                        "Restart", id="restart", variant="warning", compact=True
                    )
                    yield Button("Stop", id="stop", variant="error", compact=True)

            with VerticalGroup(id="stats"):
                yield Label("CPU: --")
                yield Label("RAM: --")

    def on_mount(self) -> None:
        self.log_widget = self.query_one(RichLog)
        self.input = self.query_one(Input)

        for line in self.server.get_logs():
            self.log_widget.write(line)

        self.server.add_log_callback(self._on_log)

    def on_unmount(self) -> None:
        self.server.remove_log_callback(self._on_log)

    def _on_log(self, server: Server, line: str) -> None:
        if self.is_mounted:
            self.app.call_from_thread(self.log_widget.write, line)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        if cmd:
            self.server.send_command(cmd)
        event.input.value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            try:
                self.run_worker(self.server.start, thread=True)
            except RuntimeError as e:
                self.app.notify(f"{e}", severity="error")
        elif event.button.id == "stop":
            self.run_worker(self.server.stop, thread=True)
        elif event.button.id == "restart":
            self.run_worker(self.server.restart, thread=True)


class ServerScreen(Screen):
    def __init__(self, server: Server):
        super().__init__()
        self.server = server

    def compose(self):
        with VerticalGroup():
            with HorizontalGroup(id="tab-bar"):
                yield Button("Home", id="home", flat=True)
                yield Tabs(
                    Tab("Overview", id="overview"),
                    Tab("Players Management", id="players"),
                    Tab("Server Settings", id="serv-settings"),
                    Tab("Add-ons", id="add-ons"),
                    Tab("Configurations", id="configs"),
                    Tab("Worlds", id="worlds"),
                    id="tabs",
                )

            self.switcher = ContentSwitcher(initial="overview")
            with self.switcher:
                with Container(id="overview"):
                    yield ServerOverview(self.server)

                with Container(id="players"):
                    yield Label("Players view")

                with Container(id="serv-settings"):
                    yield Label("Server settings view")

                with Container(id="add-ons"):
                    yield Label("Add-ons view")

                with Container(id="configs"):
                    yield Label("Configurations view")

                with Container(id="worlds"):
                    yield Label("Worlds view")

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        self.switcher.current = event.tab.id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "home":
            self.app.pop_screen()


class HomeScreen(Screen):
    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager

    def compose(self):
        yield ServerListing(self.server_manager)


class DescBlock(VerticalGroup):
    def __init__(self, server: Server):
        super().__init__()
        self.server = server

    def compose(self):
        yield Label(f"[bold]{self.server.name}[/bold]", id="name")
        yield Label(
            f"{self.server.software.capitalize()} {self.server.game_version}",
            id="software",
        )
        yield Label(self.server.state.value, id="state")


class ServerDisplay(HorizontalGroup):
    state: reactive[ServerState] = reactive(ServerState.STOPPED)

    def __init__(self, server: Server, index: int):
        super().__init__()
        self.server = server
        self.index = index

    def compose(self):
        yield Digits(str(self.index))
        self.desc = DescBlock(self.server)
        yield self.desc
        yield Static(id="spacer")

        with VerticalGroup(id="listing-action-buttons"):
            self.start_btn = Button("Start", variant="success", id="start")
            self.stop_btn = Button("Stop", variant="error", id="stop")
            yield self.start_btn
            yield self.stop_btn

        yield Button("Select", id="select")

    def on_mount(self) -> None:
        self.server.add_state_callback(self._on_state_change)
        self._update_buttons(self.server.state)

    def on_unmount(self) -> None:
        self.server.remove_state_callback(self._on_state_change)

    def _on_state_change(self, server: Server, state: ServerState) -> None:
        self.app.call_from_thread(self._set_state, state)

    def _set_state(self, state: ServerState) -> None:
        self.state = state
        self._update_buttons(state)

    def _update_buttons(self, state: ServerState) -> None:
        state_label = self.desc.query_one("#state", Label)

        state_label.remove_class(
            "stopped", "starting", "running", "stopping", "crashed"
        )
        state_label.add_class(state.value.lower())
        state_label.update(state.value)

        self.start_btn.display = state in {
            ServerState.STOPPED,
            ServerState.CRASHED,
            ServerState.STOPPING,
        }
        self.stop_btn.display = state in {ServerState.RUNNING, ServerState.STARTING}

        self.start_btn.disabled = state not in (
            ServerState.STOPPED,
            ServerState.CRASHED,
        )
        self.stop_btn.disabled = state != ServerState.RUNNING

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.run_worker(self.server.start, thread=True)
        elif event.button.id == "stop":
            self.run_worker(self.server.stop, thread=True)
        elif event.button.id == "select":
            self.app.push_screen(ServerScreen(self.server))


class ServerHead(HorizontalGroup):
    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager

    def compose(self):
        yield Button("Create", variant="success", id="create")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            self.app.push_screen(ServerWizard(self.server_manager))


class ServerListing(VerticalScroll):
    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager

    def compose(self) -> ComposeResult:
        yield ServerHead(self.server_manager)

        for index, server in enumerate(self.server_manager, start=1):
            yield ServerDisplay(server, index)

    def on_server_created(self, event: ServerCreated) -> None:
        new_index = len(self.server_manager)
        self.mount(ServerDisplay(event.server, new_index))


class Lodestone(App):
    CSS_PATH = "style.tcss"
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]
    # SCREENS = {"home_screen": HomeScreen}

    def __init__(self):
        super().__init__()
        self.SERVERS_PATH = Path.cwd() / "Servers"
        self.server_manager = ServerManager(self.SERVERS_PATH)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
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

    def on_unmount(self) -> None:
        for s in self.server_manager.values():
            if s.state == ServerState.RUNNING:
                s.stop()
                logging.info("Stopped %s", s.name)

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )
