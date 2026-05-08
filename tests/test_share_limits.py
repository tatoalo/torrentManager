import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import torrent_configuration
from src.torrent_manager import TorrentManager
from torrent_configuration import ShareLimitRule, TorrentConfiguration


class FakeState:
    def __init__(self, *, is_downloading: bool):
        self.is_downloading = is_downloading


class FakeTorrent:
    def __init__(
        self,
        *,
        hash: str,
        name: str = "torrent",
        category: str = "",
        tags="",
        trackers=(),
        progress: float = 1.0,
        is_downloading: bool = False,
    ):
        self.hash = hash
        self.name = name
        self.category = category
        self.tags = tags
        self.progress = progress
        self.state_enum = FakeState(is_downloading=is_downloading)
        self._trackers = [{"url": tracker} for tracker in trackers]

    @property
    def trackers(self):
        return self._trackers


class FakeClient:
    def __init__(self, torrents):
        self.torrents = torrents
        self.share_limit_calls = []
        self.stopped_hashes = []
        self.deleted_hashes = []

    def torrents_info(self, torrent_hashes=None, **kwargs):
        if not torrent_hashes:
            return self.torrents

        if isinstance(torrent_hashes, str):
            hashes = set(torrent_hashes.split("|"))
        else:
            hashes = set(torrent_hashes)

        return [torrent for torrent in self.torrents if torrent.hash in hashes]

    def torrents_set_share_limits(self, **kwargs):
        self.share_limit_calls.append(kwargs)

    def torrents_stop(self, *, torrent_hashes):
        self.stopped_hashes.append(torrent_hashes)

    def torrents_delete(self, *, torrent_hashes, delete_files):
        if delete_files:
            self.deleted_hashes.append(torrent_hashes)


class FakeConfig:
    def __init__(self, share_limits):
        self.share_limits = share_limits


def build_manager(*, torrents, share_limits):
    manager = TorrentManager.__new__(TorrentManager)
    manager.client = FakeClient(torrents)
    manager.config = FakeConfig(share_limits)
    manager.storage = {}
    return manager


class ShareLimitRuleTests(unittest.TestCase):
    def test_configuration_loads_share_limit_rules(self):
        configuration = """
[qbt]
host = "localhost"
port = 8080
username = "admin"
password = "password"

[[share_limits]]
name = "private tracker"
tags = ["private"]
trackers = ["tracker.example"]
ratio_limit = 2.0
seeding_time_limit = 10080
inactive_seeding_time_limit = -2
share_limit_action = "RemoveWithContent"
"""

        previous_config_path = torrent_configuration.CONFIG_PATH
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as config_file:
            config_file.write(configuration)
            config_file_path = config_file.name

        try:
            torrent_configuration.CONFIG_PATH = config_file_path
            config = TorrentConfiguration()
        finally:
            torrent_configuration.CONFIG_PATH = previous_config_path
            Path(config_file_path).unlink()

        self.assertEqual(len(config.share_limits), 1)
        rule = config.share_limits[0]
        self.assertEqual(rule.name, "private tracker")
        self.assertEqual(rule.tags, ["private"])
        self.assertEqual(rule.trackers, ["tracker.example"])
        self.assertEqual(rule.ratio_limit, 2.0)
        self.assertEqual(rule.seeding_time_limit, 10080)
        self.assertEqual(rule.inactive_seeding_time_limit, -2)
        self.assertEqual(rule.share_limit_action, "RemoveWithContent")

    def test_apply_share_limits_matches_tags(self):
        rule = ShareLimitRule(
            name="private",
            tags=["private"],
            ratio_limit=2.0,
            seeding_time_limit=60,
            share_limit_action="Stop",
        )
        manager = build_manager(
            torrents=[
                FakeTorrent(hash="match", tags="private, archive"),
                FakeTorrent(hash="miss", tags="public"),
            ],
            share_limits=[rule],
        )

        manager.apply_share_limits()

        self.assertEqual(len(manager.client.share_limit_calls), 1)
        call = manager.client.share_limit_calls[0]
        self.assertEqual(call["torrent_hashes"], ["match"])
        self.assertEqual(call["ratio_limit"], 2.0)
        self.assertEqual(call["seeding_time_limit"], 60)
        self.assertEqual(call["share_limit_action"], "Stop")

    def test_apply_share_limits_matches_trackers(self):
        rule = ShareLimitRule(
            name="tracker",
            trackers=["tracker.example"],
            ratio_limit=1.5,
            share_limit_action="RemoveWithContent",
        )
        manager = build_manager(
            torrents=[
                FakeTorrent(
                    hash="match",
                    trackers=[
                        "** [DHT] **",
                        "https://tracker.example/announce",
                    ],
                ),
                FakeTorrent(hash="miss", trackers=["https://other.example/announce"]),
            ],
            share_limits=[rule],
        )

        manager.apply_share_limits()

        self.assertEqual(len(manager.client.share_limit_calls), 1)
        call = manager.client.share_limit_calls[0]
        self.assertEqual(call["torrent_hashes"], ["match"])
        self.assertEqual(call["share_limit_action"], "RemoveWithContent")

    def test_rule_with_tags_and_trackers_requires_both_groups_to_match(self):
        rule = ShareLimitRule(
            name="private tracker",
            tags=["private"],
            trackers=["tracker.example"],
            seeding_time_limit=120,
            share_limit_action="Stop",
        )
        manager = build_manager(
            torrents=[
                FakeTorrent(
                    hash="match",
                    tags="private",
                    trackers=["https://tracker.example/announce"],
                ),
                FakeTorrent(
                    hash="tag-only",
                    tags="private",
                    trackers=["https://other.example/announce"],
                ),
                FakeTorrent(
                    hash="tracker-only",
                    tags="public",
                    trackers=["https://tracker.example/announce"],
                ),
            ],
            share_limits=[rule],
        )

        manager.apply_share_limits()

        self.assertEqual(len(manager.client.share_limit_calls), 1)
        self.assertEqual(
            manager.client.share_limit_calls[0]["torrent_hashes"],
            ["match"],
        )

    def test_completed_share_managed_torrent_is_not_paused(self):
        rule = ShareLimitRule(
            name="private",
            tags=["private"],
            seeding_time_limit=60,
            share_limit_action="Stop",
        )
        manager = build_manager(
            torrents=[FakeTorrent(hash="managed", tags="private")],
            share_limits=[rule],
        )
        manager.storage = {"managed": "Managed Torrent"}

        manager.check_status()

        self.assertEqual(manager.client.stopped_hashes, [])
        self.assertNotIn("managed", manager.storage)

    def test_completed_unmanaged_torrent_is_still_paused(self):
        rule = ShareLimitRule(
            name="private",
            tags=["private"],
            seeding_time_limit=60,
            share_limit_action="Stop",
        )
        manager = build_manager(
            torrents=[FakeTorrent(hash="unmanaged", tags="public")],
            share_limits=[rule],
        )
        manager.storage = {"unmanaged": "Unmanaged Torrent"}

        manager.check_status()

        self.assertEqual(manager.client.stopped_hashes, ["unmanaged"])
        self.assertNotIn("unmanaged", manager.storage)

    def test_cleaner_skips_share_managed_torrent(self):
        rule = ShareLimitRule(
            name="private",
            tags=["private"],
            seeding_time_limit=60,
            share_limit_action="RemoveWithContent",
        )
        manager = build_manager(
            torrents=[FakeTorrent(hash="managed", tags="private")],
            share_limits=[rule],
        )
        completed_at = int((datetime.now() - timedelta(hours=1)).timestamp())

        manager._remove_torrents(
            torrents_to_clean=[
                {
                    "hash": "managed",
                    "name": "Managed Torrent",
                    "completed_at": completed_at,
                }
            ]
        )

        self.assertEqual(manager.client.deleted_hashes, [])

    def test_cleaner_still_deletes_unmanaged_torrent(self):
        rule = ShareLimitRule(
            name="private",
            tags=["private"],
            seeding_time_limit=60,
            share_limit_action="RemoveWithContent",
        )
        manager = build_manager(
            torrents=[FakeTorrent(hash="unmanaged", tags="public")],
            share_limits=[rule],
        )
        completed_at = int((datetime.now() - timedelta(hours=1)).timestamp())

        manager._remove_torrents(
            torrents_to_clean=[
                {
                    "hash": "unmanaged",
                    "name": "Unmanaged Torrent",
                    "completed_at": completed_at,
                }
            ]
        )

        self.assertEqual(manager.client.deleted_hashes, ["unmanaged"])


if __name__ == "__main__":
    unittest.main()
