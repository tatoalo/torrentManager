import os
import shelve
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

        self._check_categories_compliance()

    def _create_client(self) -> qbittorrentapi.Client:
        """
        Create qbittorent client and test the connection to the instance
        """
        try:
            qbt_client = qbittorrentapi.Client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            )

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

    def add_to_watchdog(self, *, category: str = "") -> None:
        """
        Watchdog procedure for the specified category, torrents will be added to the storage
        """
        logging.debug("\n---- watchdog ----")

        logging.debug(f"Looking at category {category}...")
        status_of_torrents_to_be_retrieved = "downloading"

        # retrieving `downloading` torrents
        all_torrents_of_specified_category = [
            {"hash": t.info.hash, "name": t.info.name}
            for t in self.client.torrents_info(
                category=category, status_filter=status_of_torrents_to_be_retrieved
            )
        ]

        self._check_limits(torrents_dict=all_torrents_of_specified_category)

        logging.debug(f"{all_torrents_of_specified_category}")
        if all_torrents_of_specified_category:
            self._populate_DB(torrents_list=all_torrents_of_specified_category)

        logging.debug("---- watchdog ----\n")

        if not os.path.exists(STORAGE_PATH):
            logging.debug(f"Missing folder {STORAGE_PATH}, creating it...")
            os.mkdir(STORAGE_PATH)

        s = shelve.open(STORAGE_PATH + STORAGE_FILENAME)

        return s

    def _populate_DB(self, *, torrents_list: list[dict]) -> None:
        """
        Add torrents to the storage
        """
        for torrent in torrents_list:
            torrent_hash = torrent["hash"]
            if not self._is_hash_already_been_loaded(hash=torrent_hash):
                torrent_name = torrent["name"]
                self.storage[torrent_hash] = torrent_name
                logging.debug(f"Storing {torrent_hash} | {torrent_name}")

    def _is_hash_already_been_loaded(self, *, hash: str) -> bool:
        """
        Check if a torrent has already been added to the storage
        """
        try:
            # No need to waste variable space, GC will think about it :)
            self.storage[hash]
            logging.debug(f"hash {hash} was already stored")
            return True
        except KeyError:
            logging.debug(f"hash {hash} **needs** to be stored")
            return False

    def check_status(self) -> None:
        """
        Check the status of all the stored torrents and if a torrent
        has finished downloading, it will be paused
        """
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

        if len(query_result) != len(hashes_stored):
            logging.debug("Query returned different data than expected...")

        for torrent in query_result:
            torrent_hash = torrent.hash
            torrent_category = torrent.category
            torrent_progress = torrent.progress
            torrent_current_status = torrent.state_enum

            # torrent has been completely downloaded
            if not torrent_current_status.is_downloading:
                torrent_name = torrent.name

                logging.debug(
                    f"torrent {torrent_name} ~ {torrent_category} has finished downloading!"
                )

                self._pause_torrent(hash=torrent_hash)

                logging.debug(
                    f"torrent {torrent_name} ~ {torrent_category} has been **PAUSED**!"
                )

                self._remove_from_storage(hash=torrent_hash)

                logging.debug(
                    f"deleted {torrent_hash}, {len(self.storage)} torrents left in storage"
                )

            else:
                logging.debug(
                    f"{torrent_hash} ~ {torrent_category} is in status {torrent_current_status} | {torrent_progress} %"
                )

    def _pause_torrent(self, *, hash: str) -> None:
        """
        Wrapper for pausing torrent via internal API call
        """
        self.client.torrents_pause(torrent_hashes=hash)

    def _remove_from_storage(self, *, hash: str) -> None:
        """
        Removing torrent from storage
        """
        del self.storage[hash]

    def _check_categories_compliance(self) -> None:
        """
        Checking compliance in terms of save path limits for all interested categories
        """
        for category in self.config.categories:
            logging.debug(f"checking compliance for {category}")
            configuration_save_path_wanted = self.config.dir_targets[category]
            configuration_save_path_actual = self.client.torrents_categories()[
                category
            ]["savePath"]

            if configuration_save_path_actual != configuration_save_path_wanted:
                logging.debug(f"save_path destination for {category} is not compliant")
                self._enforce_category_compliance(
                    category=category, save_path_wanted=configuration_save_path_wanted
                )
            else:
                logging.debug(f"save_path for {category} is already compliant")

    def _enforce_category_compliance(
        self, *, category: str, save_path_wanted: str
    ) -> None:
        """
        Wrapper for editing the save path of a specific category
        """
        self.client.torrents_edit_category(name=category, save_path=save_path_wanted)
        logging.debug(f"save path **changed** for {category} to {save_path_wanted}")

    def _check_limits(self, *, torrents_dict: dict) -> None:
        """
        Checking compliance in terms of DL/UP limits for all interested categories
        """
        download_limit = self.config.dl_limit
        upload_limit = self.config.up_limit

        if download_limit and download_limit != -1:
            self._impose_limit(
                limit_operation=Limit.DOWNLOAD_OPERATION,
                torrents_dict=torrents_dict,
                limit=download_limit,
            )
        if upload_limit and upload_limit != -1:
            self._impose_limit(
                limit_operation=Limit.UPLOAD_OPERATION,
                torrents_dict=torrents_dict,
                limit=upload_limit,
            )

    def _impose_limit(
        self, *, limit_operation: Limit, torrents_dict: dict, limit: int
    ) -> None:
        """
        Wrapper for enforcing DL/UP limits for torrents
        """
        hashes = [t.get("hash") for t in torrents_dict]

        if limit_operation == Limit.DOWNLOAD_OPERATION:
            self.client.torrents_set_download_limit(limit=limit, torrent_hashes=hashes)
        elif limit_operation == Limit.UPLOAD_OPERATION:
            self.client.torrents_set_upload_limit(limit=limit, torrent_hashes=hashes)
        logging.debug(f"imposed {limit_operation.value} limit of {limit} for {hashes}")

