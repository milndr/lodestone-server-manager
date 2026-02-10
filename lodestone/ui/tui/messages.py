from textual.message import Message

from lodestone.core.server import Server


class ServerCreated(Message):
    def __init__(self, server: Server) -> None:
        super().__init__()
        self.server = server


class ServerDeleted(Message):
    def __init__(self, server: Server) -> None:
        super().__init__()
        self.server = server
