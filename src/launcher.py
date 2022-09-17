from torrent_manager import TorrentManager
from src import logging, OPERATIONAL_PATH
import atexit
import sys


@atexit.register
def synch_storage():
    logging.info("Synching storage...")
    try:
        t.storage.close()
    except ValueError:
        logging.info("Shelve has been already synched and closed!")


if __name__ == "__main__":
    """
    Entrypoint, the only possible operational path is "watchdog" to trigger the population of the storage component
    Avoiding the operational path will trigger the check of the status of torrents already stored
    """
    t = TorrentManager()
    if len(sys.argv) > 1:
        operational_path = sys.argv[1]

        if operational_path == OPERATIONAL_PATH:
            categories_retrieved = t.config.categories
            for category in categories_retrieved:
                t.add_to_watchdog(category=category)
    else:
        t.check_status()
