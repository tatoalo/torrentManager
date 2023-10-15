import atexit

from sync import sync_storage
from torrent_manager import TorrentManager

if __name__ == "__main__":
    t = TorrentManager()
    atexit.register(sync_storage, manager=t)

    for category in t.config._retrieve_categories():
        t.clean_procedure(category=category)
