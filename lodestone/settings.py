from platformdirs import user_data_path

SERVERS_PATH = (
    user_data_path(
        appname="lodestone", appauthor=False, roaming=True, ensure_exists=True
    )
    / "servers"
)
