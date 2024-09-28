import logging
from enum import Enum

CONFIG_PATH = "configuration.toml"
STORAGE_PATH = "data/"

STORAGE_FILENAME = "storage"

IGNORED_TRACKER_URLS = ["** [DHT] **", "** [PeX] **", "** [LSD] **"]

CLEANER_MINUTES_THRESHOLD = 15

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("qbittorrentapi").setLevel(logging.INFO)
logging.getLogger("requests").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)


class Limit(Enum):
    DOWNLOAD_OPERATION = "download"
    UPLOAD_OPERATION = "upload"
