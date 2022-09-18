import atexit

from src import logging
from torrent_manager import TorrentManager


@atexit.register
def synch_storage():
    logging.info("Synching storage...")
    try:
        t.storage.close()
    except ValueError:
        logging.info("Shelve has been already synched and closed!")
    except Exception:
        logging.info(
            "storage could not be closed, perhaps wasn't even opened to begin with."
        )


if __name__ == "__main__":

    t = TorrentManager()

    categories_retrieved = t.config.categories
    for category in categories_retrieved:
        t.add_to_watchdog(category=category)

    t.check_status()
