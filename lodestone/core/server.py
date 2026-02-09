import logging
import queue
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


StateCallback = Callable[["Server", ServerState], None]
LogCallback = Callable[["Server", str], None]


class Server:
    def __init__(self, name: str, software: str, game_version: str, path: Path):
        self.name = name
        self.software = software.lower()
        self.game_version = game_version
        self.path = path

        self.min_ram_alloc: int | None = None
        self.max_ram_alloc: int = 2
        self.additional_args: list[str] | None = None

        self.properties: dict[str, bool | int | str | None] = {}

        self.state = ServerState.STOPPED
        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.log_buffer = deque(maxlen=10_000)
        self.stop_event = threading.Event()
        self.lock = threading.RLock()

        self._state_callbacks: list[StateCallback] = []
        self._log_callbacks: list[LogCallback] = []

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
            cb(self, new_state)

    def update_property(self, key: str, value_str: str):
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

    def get_logs(self) -> list[str]:
        return list(self.log_buffer)

    def add_log_callback(self, callback: LogCallback) -> None:
        self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: LogCallback):
        if callback in self._log_callbacks:
            self._log_callbacks.remove(callback)

    def _read_logs(self) -> None:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("No process or stdout")

        try:
            for raw_line in self.process.stdout:
                if self.stop_event.is_set():
                    break

                line = raw_line.rstrip("\n")
                self.log_buffer.append(line)

                if self.state == ServerState.STARTING and self._is_server_ready(line):
                    logging.info(f"Server {self.name} is ready")
                    self._set_state(ServerState.RUNNING)

                if self._is_crash_line(line):
                    logging.warning(f"Crash detected in logs: {line}")

                for cb in self._log_callbacks:
                    cb(self, line)

        except Exception as e:
            logging.error(f"Error reading logs: {e}")
        finally:
            self._handle_process_exit()

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
