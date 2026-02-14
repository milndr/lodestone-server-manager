import logging

from textual import on
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Right, VerticalGroup, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Digits, Label
from textual.worker import Worker, WorkerState

from lodestone.core.manager import ServerManager
from lodestone.core.server import Server, ServerState
from lodestone.ui.tui.messages import ServerCreated, ServerDeleted
from lodestone.ui.tui.screens.server import ServerScreen
from lodestone.ui.tui.screens.wizard import ServerWizard

logger = logging.getLogger("lodestone")


class DescBlock(VerticalGroup):
    __slots__ = ("server",)

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
    __slots__ = ("server", "server_manager", "index", "start_btn", "stop_btn", "desc")
    state: reactive[ServerState] = reactive(ServerState.STOPPED)

    def __init__(self, server: Server, server_manager: ServerManager, index: int):
        super().__init__()
        self.server = server
        self.server_manager = server_manager
        self.index = index
        self.start_btn = Button("Start", variant="success", id="start")
        self.stop_btn = Button("Stop", variant="error", id="stop")

    def compose(self):
        yield Digits(str(self.index))
        self.desc = DescBlock(self.server)
        yield self.desc

        with VerticalGroup(id="listing-action-buttons"):
            yield Right(self.start_btn, self.stop_btn)

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
            self.run_worker(self.server.start, thread=True, exit_on_error=False)
        elif event.button.id == "stop":
            self.run_worker(self.server.stop, thread=True)
        elif event.button.id == "select":
            self.app.push_screen(ServerScreen(self.server, self.server_manager))

    @on(Worker.StateChanged)
    def handle_worker_state(self, event: Worker.StateChanged) -> None:
        worker = event.worker

        if worker.state is WorkerState.ERROR:
            error = worker.error
            logging.error(f"Worker error : {error}")
            self.app.notify(f"{error}", severity="error")


class ServerHead(HorizontalGroup):
    __slots__ = ("server_manager",)

    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager

    def compose(self):
        yield Button("Create", variant="success", id="create")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            self.app.push_screen(ServerWizard(self.server_manager))


class ServerListing(VerticalScroll):
    __slots__ = ("server_manager", "displays")

    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager
        self.displays = {}

    def compose(self) -> ComposeResult:
        yield ServerHead(self.server_manager)

        for index, server in enumerate(self.server_manager, start=1):
            display_instance = ServerDisplay(server, self.server_manager, index)
            self.displays[server.name] = display_instance
            yield display_instance

    def on_server_created(self, event: ServerCreated) -> None:
        new_index = len(self.server_manager)
        display_instance = ServerDisplay(event.server, self.server_manager, new_index)
        self.mount(display_instance)
        self.displays[event.server.name] = display_instance

    def on_server_deleted(self, event: ServerDeleted) -> None:
        try:
            display = self.displays.pop(event.server.name)
            display.remove()
        except KeyError:
            logger.warning(f"Could not find display for server {event.server.name}")


class HomeScreen(Screen):
    CSS_PATH = "../styles/home.tcss"
    __slots__ = ("server_manager",)

    def __init__(self, server_manager: ServerManager):
        super().__init__()
        self.server_manager = server_manager

    def compose(self):
        yield ServerListing(self.server_manager)
