import atexit

from synch import synch_storage
from torrent_manager import TorrentManager

if __name__ == "__main__":

    t = TorrentManager()
    atexit.register(synch_storage, manager=t)

    for category in t.config._retrieve_categories():
        t.clean_procedure(category=category)
