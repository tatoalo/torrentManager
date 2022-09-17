import logging

CONFIG_PATH = "configuration.toml"
STORAGE_PATH = "data/"
STORAGE_FILENAME = "storage"
OPERATIONAL_PATH = "watchdog"

logging.addLevelName(10, "DEBUG")
logging.basicConfig(level=logging.DEBUG)

logging.getLogger("qbittorrentapi").setLevel(logging.INFO)
logging.getLogger("requests").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)
