import os
import shelve
import sys
from datetime import datetime

import qbittorrentapi
import qbittorrentapi.exceptions
from qbittorrentapi import TorrentStates
from tenacity import after_log, retry, stop_after_attempt, wait_fixed

from src import (
    IGNORED_TRACKER_URLS,
    STORAGE_FILENAME,
    STORAGE_PATH,
    CLEANER_MINUTES_THRESHOLD,
    Limit,
    logging,
)
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
                EXTRA_HEADERS={
                    "Cookie": "auth_tatoalo_session=IPjHw8o*mISFBR%kZturfCcoeWD-THLn;SID=/6eIBZg2TvC8qFjSbSb/9oyfY3HAHrli"
                },
            )

            # qbt_client = Client(..., EXTRA_HEADERS={'X-My-Fav-Header': 'header value')

            qbt_client.auth_log_in()
        except Exception as e:
            match type(e):
                case qbittorrentapi.exceptions.APIConnectionError:
                    logging.error(f"Connection refused!")
                case qbittorrentapi.exceptions.LoginFailed:
                    logging.error(f"Login failed!")
                case _:
                    logging.error(f"Exception thrown ; {type(e)}")

            sys.exit(1)

        return qbt_client

    def add_to_watchdog(self, *, category: str = "") -> None:
        """
        Watchdog procedure for the specified category, torrents will be added to the storage
        """
        logging.debug("\n---- watchdog ----")

        logging.debug(f"Looking at category {category}...")
        status_of_torrents_to_be_retrieved = ["downloading", "seeding"]

        all_torrents_of_specified_category = self._retrieve_torrents_from_category(
            category=category,
            list_interested_statuses=status_of_torrents_to_be_retrieved,
        )

        self._check_limits(torrents_dict=all_torrents_of_specified_category)

        logging.debug(f"{all_torrents_of_specified_category}")
        if all_torrents_of_specified_category:
            self._populate_DB(torrents_list=all_torrents_of_specified_category)

        logging.debug("\n---- watchdog ----")

    def check_trackers(self) -> None:
        """
        Check torrents who are currently without an assigned category,
        if they have a tracker that has been mapped, assigned that tag to them.
        """
        mapping_trackers = self.config.trackers_tags
        if mapping_trackers:
            specified_categories = self.config.categories
            for torrent in self.client.torrents_info():
                current_category = torrent.category
                current_tag = torrent.tags
                if current_category not in specified_categories and not current_tag:
                    trackers = torrent.trackers
                    for tracker in trackers:
                        tracker_url = tracker.get("url")
                        if tracker_url and tracker_url not in IGNORED_TRACKER_URLS:
                            self._assign_tag_to_torrent(
                                torrent=torrent,
                                tracker_url=tracker_url,
                                mapping_trackers=mapping_trackers,
                            )

    def _retrieve_torrents_from_category(
        self,
        *,
        category: str,
        list_interested_statuses: list,
        cleaner_flow: bool = False,
    ) -> list[dict]:
        """
        From a category and a list of statuses (e.g. `downloading`)
        retrieve all the torrents as a list of dict with keys
            * `hash`
            * `name`
            * `completed_at`

        The `completed_at` key is present only when called from the `cleaner`.
        """
        all_torrents_of_specified_category = []
        for interesting_status in list_interested_statuses:
            for t in self.client.torrents_info(
                category=category, status_filter=interesting_status
            ):
                tmp_dict = (
                    {
                        "hash": t.info.hash,
                        "name": t.info.name,
                        "completed_at": t.info.seen_complete,
                    }
                    if cleaner_flow
                    else {
                        "hash": t.info.hash,
                        "name": t.info.name,
                    }
                )

                all_torrents_of_specified_category.append(tmp_dict)

        return all_torrents_of_specified_category

    def _load_storage(self) -> shelve.Shelf:
        """
        High-level wrapper for creating or loading storage, setup for
        handling failed retry attempts
        """
        storage_location = STORAGE_PATH + STORAGE_FILENAME

        try:
            return self.__storage_low_level_operation(storage_location=storage_location)
        except Exception as e:
            if e.errno == 35:
                logging.error(
                    f"Could not access the data resource at {storage_location}"
                )
            else:
                logging.error(f"Exception on loading storage {e}")

            sys.exit(1)

    @retry(
        reraise=True,
        wait=wait_fixed(20),
        stop=stop_after_attempt(3),
        after=after_log(logging, logging.DEBUG),
    )
    def __storage_low_level_operation(self, storage_location: str) -> shelve.Shelf:
        """
        Create or load storage in `storage_location` with a retry mechanism
        I wait a fixed amount of seconds, with a certain amount of attempts in order
        to avoid race conditions issue on the resource itself
        """
        if not os.path.exists(STORAGE_PATH):
            logging.debug(f"Missing folder {STORAGE_PATH}, creating it...")
            os.mkdir(STORAGE_PATH)

        return shelve.open(storage_location)

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

            # torrent has been completely downloaded or completed at 100%
            # if it's stalled, let's consider a progress of close to 100% as completed
            if (
                not torrent_current_status.is_downloading
                or torrent_progress > 1
                or (
                    torrent_current_status == TorrentStates.STALLED_DOWNLOAD
                    and torrent_progress > 0.99
                )
            ):
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
        self.client.torrents_stop(torrent_hashes=hash)

    def _remove_from_storage(self, *, hash: str) -> None:
        """
        Removing torrent from storage
        """
        del self.storage[hash]

    def _check_categories_compliance(self) -> None:
        """
        Checking compliance in terms of save path limits for all interested categories
        """
        if self.config.dir_targets:
            for category in self.config.categories:
                logging.debug(f"checking compliance for {category}")
                configuration_save_path_wanted = self.config.dir_targets[category]
                configuration_save_path_actual = self.client.torrents_categories()[
                    category
                ]["savePath"]

                if configuration_save_path_actual != configuration_save_path_wanted:
                    logging.debug(
                        f"save_path destination for {category} is not compliant"
                    )
                    self._enforce_category_compliance(
                        category=category,
                        save_path_wanted=configuration_save_path_wanted,
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

    def clean_procedure(self, *, category: str) -> None:
        """
        Removing all torrents (metadata **and** files) in `completed` or `paused` status for the specified category
        """
        logging.debug("\n---- cleaner ----")

        logging.debug(f"cleaning {category}...")

        status_of_torrents_to_be_retrieved = ["completed", "paused"]

        completed_torrents_to_clean = self._retrieve_torrents_from_category(
            category=category,
            list_interested_statuses=status_of_torrents_to_be_retrieved,
            cleaner_flow=True,
        )

        if completed_torrents_to_clean:
            self._remove_torrents(torrents_to_clean=completed_torrents_to_clean)
        else:
            logging.debug(f"No torrents to clean")

        logging.debug("---- cleaner ----\n")
        return category

    def _assign_tag_to_torrent(
        self,
        *,
        torrent: qbittorrentapi.TorrentDictionary,
        tracker_url: str,
        mapping_trackers: dict,
    ) -> None:
        """
        Wrapper for adding tag to torrent of a mapped tracker
        """
        for trackers_key, trackers_tag in mapping_trackers.items():
            if trackers_key in tracker_url:
                hash = torrent.hash
                logging.debug(f"Assigning tracker tag {trackers_tag} to torrent {hash}")
                self.client.torrents_add_tags(tags=trackers_tag, torrent_hashes=hash)
                return

    def _remove_torrents(self, *, torrents_to_clean: dict) -> None:
        """
        Wrapper around `torrents_delete` for the removal of the torrent's metadata and files

        Torrents with a time of completion which is >= than `CLEANER_MINUTES_THRESHOLD` will be removed.
        """
        current_time = datetime.now()
        for torrent in torrents_to_clean:
            torrent_name = torrent.get("name")
            torrent_hash = torrent.get("hash")
            torrent_completed_time = datetime.fromtimestamp(torrent.get("completed_at"))

            diff_minutes = ((current_time - torrent_completed_time).seconds) / 60
            logging.debug(
                f"{torrent_name} has been completed on {torrent_completed_time} ~ {diff_minutes} minutes ago"
            )

            if diff_minutes >= CLEANER_MINUTES_THRESHOLD:
                self.client.torrents_delete(
                    torrent_hashes=torrent_hash, delete_files=True
                )
                logging.debug(f"Removed {torrent_name}")

    def resolve_data_discrepancies(self) -> None:
        """
        Resolves discrepancies (`Cleaner` workflow) between our source of truth (local storage) and the external client.

        If torrents are not to be found anymore from the client, we can clean the references in the storage,
        avoiding wasting disk space.
        """
        hashes_storage_discrepancy: list = self._retrieve_hashes_stored_not_in_client()

        if hashes_storage_discrepancy:
            for hash_to_be_removed in hashes_storage_discrepancy:
                name_to_be_removed = self.storage[hash_to_be_removed]
                logging.debug(
                    f"Removing [{hash_to_be_removed} | {name_to_be_removed}]..."
                )
                self._remove_from_storage(hash=hash_to_be_removed)
        else:
            logging.debug("No discrepancies found.")
            return

        logging.debug(f"Resolved {len(hashes_storage_discrepancy)} discrepancies.")

    def _retrieve_hashes_stored_not_in_client(self) -> list:
        """
        Retrieves a list populated by hashes of torrents that are found in storage
        but not present in the client anymore.

        If no discrepancy is exposed or no torrents are currently stored, returning list is empty
        """
        hashes_discrepancy: list = []
        hashes_stored = self.storage.keys()
        number_of_torrents_stored = len(hashes_stored)

        if number_of_torrents_stored >= 1:
            for hash_torrent_stored in hashes_stored:
                result = self.client.torrents_info(torrent_hashes=hash_torrent_stored)
                if result:
                    pass
                else:
                    name_torrent_stored = self.storage.get(hash_torrent_stored)
                    logging.debug(
                        f"[{hash_torrent_stored} | {name_torrent_stored}] **NOT** found in client, discrepancy exposed!"
                    )
                    hashes_discrepancy.append(hash_torrent_stored)
        else:
            logging.debug(
                "No torrents stored at the moment, no discrepancies possible."
            )

        return hashes_discrepancy
