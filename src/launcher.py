from torrent_manager import TorrentManager
import atexit
import sys
from src import logging


@atexit.register
def synch_storage():
    logging.info("Synching storage...")
    try:
        t.storage.close()
    except ValueError:
        logging.info("Shelve has been already synched and closed!")


if __name__ == "__main__":

    t = TorrentManager()

