import contextlib
import logging

from textual.app import ComposeResult
from textual.containers import (
    Container,
    Grid,
    HorizontalGroup,
    Right,
    VerticalGroup,
    VerticalScroll,
)
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    Input,
    Label,
    ListView,
    RichLog,
    Static,
    Switch,
    Tab,
    Tabs,
)

from lodestone.core.manager import ServerManager
from lodestone.core.server import Server, ServerState
from lodestone.ui.tui.messages import ServerDeleted

logger = logging.getLogger("lodestone")


class ServerOverview(Static):
    def __init__(self, server: Server):
        super().__init__()
        self.server = server

    def compose(self):
        with Container(id="overview-grid"):
            with VerticalGroup(id="players-list"):
                yield ListView(id="player-list-view")

            with VerticalGroup(id="console"):
                yield RichLog(id="log", wrap=True)
                yield Input(id="input", placeholder="Enter a command")

            with VerticalGroup(id="actions"):
                yield Button("Start", id="start", variant="success", compact=True)
                yield Button("Restart", id="restart", variant="warning", compact=True)
                yield Button("Stop", id="stop", variant="error", compact=True)

            with VerticalGroup(id="stats"):
                yield Label("CPU: --")
                yield Label("RAM: --")

    def on_mount(self) -> None:
        self.log_widget = self.query_one(RichLog)
        self.input = self.query_one(Input)
        console = self.query_one("#console")
        console.border_title = "Console"
        actions = self.query_one("#actions")
        actions.border_title = "Actions"
        players_list = self.query_one("#players-list")
        players_list.border_title = "Players"
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
            with contextlib.suppress(RuntimeError):
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


class DeleteScreen(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Are you sure you want to delete this server?", id="question"),
            Button("Delete", variant="error", id="delete"),
            Button("Cancel", variant="primary", id="cancel"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ServerScreen(Screen):
    CSS_PATH = "../styles/server.tcss"

    def __init__(self, server: Server, server_manager: ServerManager):
        super().__init__()
        self.server = server
        self.server_manager = server_manager

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
                    yield Label("Not implemented yet")

                with Container(id="serv-settings"):
                    yield Label("Not implemented yet")
                    yield Button("Delete Server", id="delete-button", variant="error")

                with Container(id="add-ons"):
                    yield Label("Not implemented yet")

                with Container(id="configs"):
                    yield Button("Apply changes", id="apply-button")
                    with VerticalScroll(), Grid():
                        for property in self.server.properties:
                            with HorizontalGroup(id=property):
                                yield Label(property, id="property-name")
                                value = self.server.properties[property]
                                if isinstance(value, bool):
                                    yield Right(Switch(value=value, id=property))
                                elif isinstance(value, str):
                                    yield Right(
                                        Input(
                                            value=value,
                                            type="text",
                                            id=property,
                                        )
                                    )
                                else:
                                    yield Right(
                                        Input(
                                            value=str(value),
                                            type="integer",
                                            id=property,
                                        )
                                    )
                with Container(id="worlds"):
                    yield Label("Not implemented yet")

    def on_switch_changed(self, event: Switch.Changed):
        if event.switch.id is not None:
            self.server.change_property_dict(key=event.switch.id, value=event.value)
            self.query_one("#apply-button", Button).variant = "success"

    def on_input_changed(self, event: Input.Changed):
        if event.input.id is not None:
            self.server.change_property_dict(key=event.input.id, value=event.value)
            self.query_one("#apply-button", Button).variant = "success"

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        self.switcher.current = event.tab.id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "home":
            self.app.pop_screen()
        if event.button.id == "delete-button":
            if self.server.state in (ServerState.RUNNING, ServerState.STARTING):
                self.app.notify("Stop the server first", severity="information")
            else:

                def check_delete(delete: bool | None) -> None:
                    if delete:
                        self.server_manager.delete_server(self.server.name)
                        self.app.pop_screen()
                        self.post_message(ServerDeleted(self.server))

                self.app.push_screen(DeleteScreen(), check_delete)
        if event.button.id == "apply-button":
            self.server.dict_to_properties()
