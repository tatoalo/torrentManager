import os
import shelve
import shutil
import sys

import qbittorrentapi
import qbittorrentapi.exceptions

from src import STORAGE_FILENAME, STORAGE_PATH, Limit, logging
from torrent_configuration import TorrentConfiguration


class TorrentManager:
    def __init__(self):
        self.config = TorrentConfiguration()
        self.storage = self._load_storage()
        self.client = self._create_client()

    def _create_client(self):
        qbt_client = qbittorrentapi.Client(
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
        )
        try:
            qbt_client.auth_log_in()
        except Exception as e:
            match type(e):
                case qbittorrentapi.exceptions.APIConnectionError:
                    logging.error(f"Connection refused!")
                case qbittorrentapi.exceptions.LoginFailed:
                    logging.error(f"Login failed!")
                case _:
                    logging.error(f"Exception thrown ; {type(e)}")

            sys.exit()

        return qbt_client

    def add_to_watchdog(self, category: str = ""):
        logging.debug(f"Looking at category {category}...")
        # TODO: tune filter to "downloading"
        all_torrents_of_specified_category = [
            {"hash": t.info.hash, "name": t.info.name}
            for t in self.client.torrents_info(category=category, status_filter="all")
        ]
        logging.debug(f"{all_torrents_of_specified_category}")
        if all_torrents_of_specified_category:
            self._populate_DB(torrents_list=all_torrents_of_specified_category)

    def _load_storage(self):
        if not os.path.exists(STORAGE_PATH):
            logging.debug(f"Missing folder {STORAGE_PATH}, creating it...")
            os.mkdir(STORAGE_PATH)

        s = shelve.open(STORAGE_PATH + STORAGE_FILENAME)

        return s

    def _populate_DB(self, torrents_list: list[dict]):
        for torrent in torrents_list:
            torrent_hash = torrent["hash"]
            if not self._is_hash_already_been_loaded(hash=torrent_hash):
                torrent_name = torrent["name"]
                self.storage[torrent_hash] = torrent_name
                logging.debug(f"Storing {torrent_hash} | {torrent_name}")

    def _is_hash_already_been_loaded(self, hash: str):
        try:
            # No need to waste variable space, GC will think about it :)
            self.storage[hash]
            logging.debug(f"hash {hash} was already stored")
            return True
        except KeyError:
            logging.debug(f"hash {hash} **needs** to be stored")
            return False

    def check_status(self):
        hashes_to_check = ""
        hashes_stored = self.storage.keys()
        number_of_torrents = len(hashes_stored)

        logging.debug(f"Need to check {number_of_torrents} torrents")

        if number_of_torrents > 1:
            for i, h in enumerate(hashes_stored):
                if i != number_of_torrents - 1:
                    hashes_to_check += h + "|"
                else:
                    hashes_to_check += h
        elif number_of_torrents == 1:
            hashes_to_check = list(hashes_stored)[0]
        else:
            logging.debug("No torrents to check...")
            return

        query_result = self.client.torrents_info(torrent_hashes=hashes_to_check)

        if len(query_result) != hashes_stored:
            logging.debug("Query returned different data than expected...")

        for torrent in query_result:
            # torrent has been completely downloaded
            if not torrent.state_enum.is_downloading:
                torrent_name = torrent.name
                torrent_category = torrent.category

                logging.debug(
                    f"torrent {torrent_name} ~ {torrent_category} has finished downloading!"
                )

                self._pause_torrent(hash=torrent.hash)

                logging.debug(
                    f"torrent {torrent_name} ~ {torrent_category} has been **PAUSED**!"
                )
                # TODO: move torrent to final directory, use a temporary one for now for `radarr`
                self._move_torrent(torrent=torrent, category=torrent_category)

    def _pause_torrent(self, hash: str):
        self.client.torrents_pause(torrent_hashes=hash)

    def _move_torrent(self, torrent: qbittorrentapi.TorrentDictionary, category: str):
        breakpoint()
        original_dir = torrent.content_path
        destination_dir = self.config.dir_targets[category]

        logging.debug(f"moving torrent from {original_dir} to {destination_dir}")

        # shutil.move(original_dir, destination_dir)
        self.client.torrents_set_save_path(
            torrent_hashes=torrent.hash, save_path=destination_dir
        )
