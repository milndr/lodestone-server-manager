import contextlib
import logging

from textual import work
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
    ListItem,
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
    __slots__ = ("server", "log_widget", "input")

    def __init__(self, server: Server):
        super().__init__()
        self.server = server
        self.player_items: dict[str, ListItem] = {}

    def compose(self):
        with Container(id="overview-grid"):
            with VerticalGroup(id="players-list"):
                yield ListView(id="player-list-view")

            with VerticalGroup(id="console"):
                yield RichLog(id="log", wrap=True)
                yield Input(id="command-input", placeholder="Enter a command")

            with VerticalGroup(id="actions"):
                yield Button("Start", id="start", variant="success", compact=True)
                yield Button("Restart", id="restart", variant="warning", compact=True)
                yield Button("Stop", id="stop", variant="error", compact=True)

            with VerticalGroup(id="stats"):
                yield Label("CPU: --")
                yield Label("RAM: --")

    def on_mount(self) -> None:
        self.log_widget = self.query_one(RichLog)
        self.online_player_list = self.query_one("#player-list-view", ListView)
        self.input = self.query_one(Input)
        console = self.query_one("#console")
        console.border_title = "Console"
        actions = self.query_one("#actions")
        actions.border_title = "Actions"
        players_list = self.query_one("#players-list")
        players_list.border_title = "Players"
        for line in self.server.get_logs(limit=500):
            self.log_widget.write(line)

        for online_player in self.server.online_players:
            self._add_player(online_player)

        self.server.add_log_callback(self._on_log)
        self.server.add_playerjoined_callback(self._on_playerjoin)
        self.server.add_playerleft_callback(self._on_playerleft)

    def on_unmount(self) -> None:
        self.server.remove_log_callback(self._on_log)
        self.server.remove_playerjoined_callback(self._on_playerjoin)
        self.server.remove_playerleft_callback(self._on_playerleft)

    def _on_log(self, server: Server, line: str) -> None:
        if self.is_mounted:
            self.app.call_from_thread(self.log_widget.write, line)

    def _add_player(self, player_name: str) -> None:
        item = ListItem(Label(player_name))
        self.player_items[player_name] = item
        self.online_player_list.append(item)

    def _on_playerjoin(self, server: Server, player_name: str) -> None:
        if self.is_mounted:
            self.app.call_from_thread(self._add_player, player_name)

    def _remove_player(self, player_name: str) -> None:
        item = self.player_items.pop(player_name, None)
        if item:
            index = self.online_player_list.children.index(item)
            self.online_player_list.pop(index)

    def _on_playerleft(self, server: Server, player_name: str) -> None:
        if self.is_mounted:
            self.app.call_from_thread(self._remove_player, player_name)

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
    __slots__ = ("server", "server_manager", "switcher")

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
                    with VerticalScroll():
                        yield Grid(id="properties-grid")
                with Container(id="worlds"):
                    yield Label("Not implemented yet")

    def on_mount(self) -> None:
        self.load_properties()

    @work(exclusive=True)
    async def load_properties(self) -> None:
        grid = self.query_one("#properties-grid", Grid)
        await grid.query("*").remove()

        widgets = []
        for property, value in self.server.properties.items():
            if isinstance(value, bool):
                control = Right(Switch(value=value, id=property))
            elif isinstance(value, str):
                control = Right(Input(value=value, type="text", id=property))
            else:
                control = Right(Input(value=str(value), type="integer", id=property))

            hg = HorizontalGroup(
                Label(property, id="property-name"), control, id=property
            )
            widgets.append(hg)

        await grid.mount_all(widgets)

    def on_switch_changed(self, event: Switch.Changed):
        if event.switch.id is not None:
            self.server.change_property_dict(key=event.switch.id, value=event.value)
            self.query_one("#apply-button", Button).variant = "success"

    def on_input_changed(self, event: Input.Changed):
        if event.input.id is not None and event.input.id != "command-input":
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
