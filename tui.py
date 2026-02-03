from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import HorizontalGroup, VerticalScroll, VerticalGroup, Container
from textual.widgets import (
    Footer,
    Header,
    Button,
    Label,
    Digits,
    Static,
    RichLog,
    ListView,
    Input,
    Tab,
    Tabs,
    ContentSwitcher,
)
from textual.reactive import reactive

from server_manager import ServerManager
from pathlib import Path
from core import ServerState, Server
import logging


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
            self.run_worker(self.server.start, thread=True)
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
        yield Static(self.server.state.value, id="state")


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
        state_label = self.desc.query_one("#state")

        state_label.remove_class(
            "stopped", "starting", "running", "stopping", "crashed"
        )
        state_label.add_class(state.value.lower())
        state_label.update(state.value)

        self.start_btn.display = state in {ServerState.STOPPED, ServerState.CRASHED, ServerState.STOPPING}
        self.stop_btn.display = state in {ServerState.RUNNING, ServerState.STARTING}

        self.start_btn.disabled = state != ServerState.STOPPED and state != ServerState.CRASHED
        self.stop_btn.disabled = state != ServerState.RUNNING

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.run_worker(self.server.start, thread=True)
        elif event.button.id == "stop":
            self.run_worker(self.server.stop, thread=True)
        elif event.button.id == "select":
            self.app.push_screen(ServerScreen(self.server))


class ServerHead(HorizontalGroup):
    def compose(self):
        yield Button("Create", variant="success", id="create")


class ServerListing(VerticalScroll):
    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager

    def compose(self) -> ComposeResult:
        yield ServerHead()

        for index, server in enumerate(self.server_manager, start=1):
            yield ServerDisplay(server, index)


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
        self.push_screen(HomeScreen(self.server_manager))

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


if __name__ == "__main__":
    app = Lodestone()
    app.run()
