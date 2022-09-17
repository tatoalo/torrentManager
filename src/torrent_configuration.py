from src import logging
import os
import sys

import tomlkit

from src import CONFIG_PATH


class TorrentConfiguration:
    def __init__(self):
        self.host = None
        self.port = None
        self.username = None
        self.password = None

        self.dl_limit = None
        self.up_limit = None

        self.categories = []
        self.dir_targets = {}

        self._load_configuration()

    def _load_configuration(self):
        """
        Loading toml configuration

        e.g.
        [qbt]
        host = "host"
        port = 6942
        username = "username"
        password = "password"

        [qbt_config]
        dl_limit = -1
        up_limit = -1

        [qbt_categories]
        categories = ["cat", "cat2"]

        [targets]
        dir_targets = { "cat" = "/home/lol", "cat2" = "/home/asd" }
        """

        if not os.path.exists(CONFIG_PATH):
            logging.error(f"Configuration file not found in path `{CONFIG_PATH}`")
            sys.exit()

        data = None
        with open(CONFIG_PATH, "rb") as f:
            data = tomlkit.load(f)

        for section, inner_section in data.items():
            match section:
                case "qbt":
                    self.host = inner_section.get("host")
                    try:
                        self.port = int(inner_section.get("port"))
                    except ValueError:
                        logging.error(
                            f"Wrong port defined, is it a valid number? {inner_section.get('port')}"
                        )
                        sys.exit()
                    self.username = inner_section.get("username")
                    self.password = inner_section.get("password")
                case "qbt_config":
                    self.dl_limit = inner_section.get("dl_limit")
                    self.up_limit = inner_section.get("up_limit")
                case "qbt_categories":
                    self.categories = inner_section.get("categories")
                case "targets":
                    self.dir_targets = inner_section.get("dir_targets")
                case _:
                    logging.info(
                        f"Found section {section} in configuration file, skipping this since it wasn't expected..."
                    )
