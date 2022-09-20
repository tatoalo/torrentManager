from src import logging
from src.torrent_manager import TorrentManager


def synch_storage(*, manager: TorrentManager) -> None:
    logging.info("Synching storage...")
    try:
        manager.storage.close()
    except ValueError:
        logging.info("Shelve has been already synched and closed!")
    except Exception:
        logging.info(
            "storage could not be closed, perhaps wasn't even opened to begin with."
        )
