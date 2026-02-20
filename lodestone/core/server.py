import json
import logging
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from enum import Enum
from pathlib import Path


class ServerState(Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    CRASHED = "CRASHED"


StateCallback = Callable[[ServerState], None]
LogCallback = Callable[[str], None]
PlayerJoinedCallback = Callable[[str], None]
PlayerLeftCallback = Callable[[str], None]


class Server:
    __slots__ = (
        "name",
        "software",
        "game_version",
        "path",
        "min_ram_alloc",
        "max_ram_alloc",
        "additional_args",
        "properties",
        "online_players",
        "state",
        "process",
        "log_buffer",
        "stop_event",
        "lock",
        "_state_callbacks",
        "_log_callbacks",
        "_stop_requested",
        "_playerjoined_callbacks",
        "_playerleft_callbacks",
        "log_thread",
    )

    def __init__(self, name: str, software: str, game_version: str, path: Path):
        self.name = name
        self.software = software.lower()
        self.game_version = game_version
        self.path = path

        self.min_ram_alloc: int | None = None
        self.max_ram_alloc: int = 2
        self.additional_args: list[str] | None = None

        self.properties: dict[str, bool | int | str | None] = {}
        self.online_players: list[str] = []

        self.state = ServerState.STOPPED
        self.process: subprocess.Popen | None = None
        self.log_buffer = deque(maxlen=10_000)
        self.stop_event = threading.Event()
        self.lock = threading.RLock()

        self._state_callbacks: list[StateCallback] = []
        self._log_callbacks: list[LogCallback] = []
        self._playerjoined_callbacks: list[PlayerJoinedCallback] = []
        self._playerleft_callbacks: list[PlayerLeftCallback] = []

        self._stop_requested = False

    def __str__(self) -> str:
        out = (
            f"Name : {self.name}\n"
            f"Version : {self.game_version}\n"
            f"Software : {self.software}\n"
            f"Path : {self.path}\n"
            f"State : {self.state}\n"
        )
        if self.process and self.state == ServerState.RUNNING:
            out += f"PID : {self.process.pid}\n"
        return out

    def properties_to_dict(self):
        properties_path = self.path / "server.properties"
        out = {}

        try:
            with properties_path.open(encoding="utf-8") as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue

                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()

                    if value.lower() in ("true", "false"):
                        out[key] = value.lower() == "true"
                    elif value.isdigit() or (
                        value.startswith("-") and value[1:].isdigit()
                    ):
                        out[key] = int(value)
                    else:
                        out[key] = value
        except FileNotFoundError as err:
            raise FileNotFoundError("server.properties couldn't be found") from err

        return out

    def dict_to_properties(self):
        properties_path = self.path / "server.properties"
        data = self.properties

        with properties_path.open("w", encoding="utf-8") as file:
            for key, value in data.items():
                if isinstance(value, bool):
                    value_str = "true" if value else "false"
                else:
                    value_str = str(value)

                file.write(f"{key}={value_str}\n")

    def get_opped_players_dict(self):
        opped_json_path = self.path / "ops.json"

        try:
            with opped_json_path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def add_state_callback(self, callback: StateCallback) -> None:
        self._state_callbacks.append(callback)

    def remove_state_callback(self, callback: StateCallback):
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)

    def _set_state(self, new_state: ServerState) -> None:
        with self.lock:
            if self.state == new_state:
                return

            self.state = new_state

        for cb in self._state_callbacks:
            cb(new_state)

    def change_property_dict(self, key: str, value: str | int | bool):
        if key not in self.properties:
            raise KeyError(f"{key} does not exist")

        self.properties[key] = value

    def change_property_str(self, key: str, value_str: str):
        if key not in self.properties:
            raise KeyError(f"{key} does not exist")

        current = self.properties[key]
        value_str = value_str.strip()

        if isinstance(current, bool):
            if value_str.lower() not in ("true", "false"):
                raise ValueError("Expected boolean")
            value = value_str.lower() == "true"
        elif isinstance(current, int):
            if not (
                value_str.isdigit()
                or (value_str.startswith("-") and value_str[1:].isdigit())
            ):
                raise ValueError("Expected integer")
            value = int(value_str)
        elif current is None:
            value = value_str
        else:
            value = value_str

        self.properties[key] = value

    def start(self) -> None:
        with self.lock:
            if self.state == ServerState.RUNNING:
                raise RuntimeError("Server is already running!")

            jar_path = self.path / "server.jar"
            if not jar_path.exists():
                raise FileNotFoundError("Can't find server.jar")

            if self.min_ram_alloc is not None:
                command = [
                    "java",
                    f"-Xms{self.min_ram_alloc}G",
                    f"-Xmx{self.max_ram_alloc}G",
                    "-jar",
                    str(jar_path),
                    "nogui",
                ]
            else:
                command = [
                    "java",
                    f"-Xmx{self.max_ram_alloc}G",
                    "-jar",
                    str(jar_path),
                    "nogui",
                ]

            if self.additional_args is not None:
                command.extend(self.additional_args)

            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=self.path,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as err:
                raise RuntimeError("Invalid arguments") from err

            self.stop_event.clear()
            self._stop_requested = False
            self._set_state(ServerState.STARTING)

            self.log_thread = threading.Thread(
                target=self._read_logs,
                daemon=True,
            )
            self.log_thread.start()

    def send_command(self, cmd: str) -> None:
        if self.state not in (ServerState.RUNNING, ServerState.STOPPING):
            raise RuntimeError("Server is not running!")

        if not self.process or not self.process.stdin:
            raise RuntimeError("No process or STDIN")

        self.process.stdin.write(cmd + "\n")
        self.process.stdin.flush()

    def get_logs(self, limit: int = 500) -> list[str]:
        with self.lock:
            if limit <= 0:
                return list(self.log_buffer)

            logs = list(self.log_buffer)
            return logs[-limit:] if limit < len(logs) else logs

    def add_log_callback(self, callback: LogCallback) -> None:
        self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: LogCallback):
        if callback in self._log_callbacks:
            self._log_callbacks.remove(callback)

    def add_playerjoined_callback(self, callback: LogCallback) -> None:
        self._playerjoined_callbacks.append(callback)

    def remove_playerjoined_callback(self, callback: LogCallback):
        if callback in self._playerjoined_callbacks:
            self._playerjoined_callbacks.remove(callback)

    def add_playerleft_callback(self, callback: LogCallback) -> None:
        self._playerleft_callbacks.append(callback)

    def remove_playerleft_callback(self, callback: LogCallback):
        if callback in self._playerleft_callbacks:
            self._playerleft_callbacks.remove(callback)

    def _read_logs(self) -> None:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("No process or stdout")

        try:
            for raw_line in self.process.stdout:
                if self.stop_event.is_set():
                    break

                line = raw_line.rstrip("\n")
                with self.lock:
                    self.log_buffer.append(line)

                if self.state == ServerState.STARTING and self._is_server_ready(line):
                    logging.info(f"Server {self.name} is ready")
                    self._set_state(ServerState.RUNNING)

                if self._is_crash_line(line):
                    logging.warning(f"Crash detected in logs: {line}")

                self._has_player_joined(line)
                self._has_player_left(line)

                for cb in self._log_callbacks:
                    cb(line)

        except Exception as e:
            logging.error(f"Error reading logs: {e}")
        finally:
            self._handle_process_exit()

    def _has_player_joined(self, line: str) -> None:
        indicator = "] logged in with entity id "
        if indicator not in line:
            return

        if self._is_imitating(line):
            return

        player_name = line.split(" ")[3].split("[")[0]
        legit_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVXYZ_"

        if any(char not in legit_chars for char in player_name):
            return

        self.online_players.append(player_name)

        for cb in self._playerjoined_callbacks:
            cb(player_name)

        logging.info(f"player joined: {player_name}")

    def _is_imitating(self, line: str) -> bool:
        return any(online_player in line for online_player in self.online_players)

    def _has_player_left(self, line: str) -> None:
        indicator = " lost connection: Disconnected"
        if indicator not in line:
            return

        player_name = line.split(" ")[3]
        legit_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVXYZ_"

        if any(char not in legit_chars for char in player_name):
            return

        self.online_players.remove(player_name)

        for cb in self._playerleft_callbacks:
            cb(player_name)

        logging.info(f"player left: {player_name}")

    def _is_server_ready(self, line: str) -> bool:
        ready_indicators = [
            "INFO]: Done (",
            "For help, type",
            "This server is running",
        ]
        return any(indicator in line for indicator in ready_indicators)

    def _is_crash_line(self, line: str) -> bool:
        crash_indicators = [
            "Exception",
            "Error",
            "FATAL",
            "Crash",
            "OutOfMemoryError",
            "Unsupported Java detected",
        ]
        line_lower = line.lower()
        return any(indicator.lower() in line_lower for indicator in crash_indicators)

    def _handle_process_exit(self) -> None:
        if self.process is None:
            return

        return_code = self.process.poll()

        self._close_pipes()

        if self._stop_requested or return_code == 0:
            self._set_state(ServerState.STOPPED)
        else:
            logging.error(f"Server {self.name} crashed with exit code {return_code}")
            self._set_state(ServerState.CRASHED)

        self.process = None
        self.stop_event.set()

    def _close_pipes(self) -> None:
        if self.process:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            if self.process.stdout and not self.process.stdout.closed:
                self.process.stdout.close()

    def restart(self) -> None:
        self.stop(restart=True)

    def stop(self, restart: bool = False) -> None:
        if self.state not in (ServerState.STARTING, ServerState.RUNNING):
            if restart:
                self.start()
            return

        self._set_state(ServerState.STOPPING)
        self._stop_requested = True

        try:
            self.send_command("stop")
        except RuntimeError:
            if self.process:
                self.process.terminate()

        threading.Thread(
            target=self._wait_stop,
            args=(restart,),
            daemon=True,
        ).start()

    def _wait_stop(self, restart: bool) -> None:
        try:
            if self.process:
                self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logging.warning(f"Server {self.name} stop timeout, killing...")
            if self.process:
                self.process.terminate()
                self.process.wait()

        self.stop_event.set()

        if hasattr(self, "log_thread") and self.log_thread.is_alive():
            self.log_thread.join(timeout=1)

        logging.info(f"Server {self.name} stopped")

        if restart:
            self.start()

    def accept_eula(self) -> None:
        (self.path / "eula.txt").write_text("eula=true\n", encoding="utf-8")
