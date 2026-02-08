import functools
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from lodestone.utils.helpers import download_file

HEADERS = {"user-agent": "lodestone-server-manager/0.0.1"}

ProgressCb = Callable[[int, int | None], None]


@functools.lru_cache(maxsize=1)
def paper_get_versions():
    url = "https://fill.papermc.io/v3/projects/paper"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except requests.exceptions.Timeout as err:
        raise RuntimeError("Request timed out") from err
    response.raise_for_status()
    data = response.json()
    return data["versions"]


def paper_version_exist(game_version: str):
    return any(game_version in versions for versions in paper_get_versions().values())


def paper_list_versions():
    out = "Paper versions :\n"
    versions = paper_get_versions()
    for big_ver in versions:
        out += f"\n{big_ver} : "
        for lil_ver in versions[big_ver]:
            if lil_ver != big_ver:
                out += f"{lil_ver[len(big_ver) :]} "
            out += ".0"
    # out += f"{big_ver} : {", ".join(data["versions"][big_ver])}\n"
    print(out)


def paper_download_latest_jar(
    game_version: str, server_path: Path, progress: ProgressCb | None = None
):
    url = f"https://fill.papermc.io/v3/projects/paper/versions/{game_version}/builds"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
    except requests.exceptions.Timeout as err:
        raise RuntimeError("Request timed out") from err
    r.raise_for_status()

    for build in r.json():
        if build["channel"] == "STABLE":
            download_file(
                build["downloads"]["server:default"]["url"],
                server_path / "server.jar",
                progress,
            )
            break


@functools.lru_cache(maxsize=1)
def vanilla_get_json():
    url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except requests.exceptions.Timeout as err:
        raise RuntimeError("Request timed out") from err
    response.raise_for_status()
    return response.json()


@functools.lru_cache(maxsize=1)
def vanilla_get_versions():
    data = vanilla_get_json()
    out = []
    for version in data["versions"]:
        if version["type"] == "release":
            out.append(version["id"])
    return out


def vanilla_get_versions_sorted():
    versions_list = vanilla_get_versions()
    out = {}
    temp = []
    for version in versions_list:
        temp.append(version)
        if version.count(".") == 1:
            out[version] = temp
            temp = []
    return out


def vanilla_list_versions():
    out = "Vanilla versions :\n"
    versions = vanilla_get_versions_sorted()
    for big_ver in versions:
        out += f"\n{big_ver} : "
        for lil_ver in versions[big_ver]:
            if lil_ver != big_ver:
                out += f"{lil_ver[len(big_ver) :]} "
            out += ".0"
    print(out)
    # out += f"{big_ver} : {", ".join(data["versions"][big_ver])}\n"


def vanilla_download_latest_jar(
    game_version: str, server_path: Path, progress: ProgressCb | None = None
):
    jar_url = None
    for version in vanilla_get_json()["versions"]:
        if version["type"] == "release" and version["id"] == game_version:
            try:
                response = requests.get(version["url"], headers=HEADERS, timeout=10)
            except requests.exceptions.Timeout as err:
                raise RuntimeError("Request timed out") from err
            response.raise_for_status()
            data = response.json()
            jar_url = data["downloads"]["server"]["url"]

    if jar_url:
        download_file(
            jar_url,
            server_path / "server.jar",
            progress,
        )
    else:
        raise RuntimeError("no jar for this version")


def vanilla_version_exist(game_version: str):
    return any(game_version in versions for versions in vanilla_get_versions())


@dataclass(frozen=True)
class SoftwareProvider:
    version_exists: Callable[[str], bool]
    download_jar: Callable[[str, Path, ProgressCb | None], None]
    list_versions: Callable[[], None]
    get_versions: Callable[[], Any]


PROVIDERS: dict[str, SoftwareProvider] = {
    "paper": SoftwareProvider(
        version_exists=paper_version_exist,
        download_jar=paper_download_latest_jar,
        list_versions=paper_list_versions,
        get_versions=paper_get_versions,
    ),
    "vanilla": SoftwareProvider(
        version_exists=vanilla_version_exist,
        download_jar=vanilla_download_latest_jar,
        list_versions=vanilla_list_versions,
        get_versions=vanilla_get_versions,
    ),
}


def get_provider(name: str) -> SoftwareProvider:
    try:
        return PROVIDERS[name.lower()]
    except KeyError as err:
        raise ValueError(f"Unsupported server software: {name}") from err
