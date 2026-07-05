import os
import sys
from dataclasses import dataclass, field
from typing import Any

import tomlkit

from src import CONFIG_PATH, logging

SUPPORTED_SHARE_LIMIT_ACTIONS = {
    "Stop",
    "Remove",
    "RemoveWithContent",
    "EnableSuperSeeding",
}


@dataclass(frozen=True)
class ShareLimitRule:
    name: str
    tags: list[str] = field(default_factory=list)
    trackers: list[str] = field(default_factory=list)
    ratio_limit: int | float | None = None
    seeding_time_limit: int | None = None
    inactive_seeding_time_limit: int | None = None
    share_limit_action: str | None = None


class TorrentConfiguration:
    def __init__(self):
        self.host = None
        self.port = None
        self.username = None
        self.password = None

        self.dl_limit = None
        self.up_limit = None

        self.categories = []
        self.dir_targets = {}

        self.trackers_tags = {}
        self.share_limits: list[ShareLimitRule] = []

        self._load_configuration()

    def _load_configuration(self) -> None:
        """
        Loading toml configuration

        e.g.
        [qbt]
        host = "host"
        port = 6942
        username = "username"
        password = "password"

        [qbt_config]
        dl_limit = -1
        up_limit = -1

        [qbt_categories]
        categories = ["cat", "cat2"]

        [targets]
        dir_targets = { "cat" = "path", "cat2" = "path" }

        [trackers]
        trackers_tags = { "tracker_endpoint" = "tag" }

        [[share_limits]]
        name = "private tracker"
        tags = ["private"]
        trackers = ["tracker_endpoint"]
        ratio_limit = 2.0
        seeding_time_limit = 10080
        inactive_seeding_time_limit = -2
        share_limit_action = "RemoveWithContent"
        """

        if not os.path.exists(CONFIG_PATH):
            logging.error(f"Configuration file not found in path `{CONFIG_PATH}`")
            sys.exit(1)

        data = None
        with open(CONFIG_PATH, "rb") as f:
            data = tomlkit.load(f)

        for section, inner_section in data.items():
            match section:
                case "qbt":
                    self.host = inner_section.get("host")
                    try:
                        port = inner_section.get("port")
                        if port:
                            self.port = int(port)
                    except Exception as e:
                        match type(e):
                            case ValueError.__class__:
                                logging.error(
                                    f"Wrong port defined, is it a valid number? {inner_section.get('port')}"
                                )
                            case TypeError.__class__:
                                logging.error(f"Wrong port type defined with {e}")
                            case _:
                                logging.error(f"Exception thrown ; {type(e)}")

                        sys.exit(1)
                    self.username = inner_section.get("username")
                    self.password = inner_section.get("password")
                case "qbt_config":
                    self.dl_limit = inner_section.get("dl_limit")
                    self.up_limit = inner_section.get("up_limit")
                case "qbt_categories":
                    self.categories = inner_section.get("categories")
                case "targets":
                    self.dir_targets = inner_section.get("dir_targets")
                case "trackers":
                    self.trackers_tags = inner_section.get("trackers_tags")
                case "share_limits":
                    self.share_limits = self._load_share_limit_rules(inner_section)
                case _:
                    logging.info(
                        f"Found section {section} in configuration file, skipping this since it wasn't expected..."
                    )

    def _retrieve_categories(self) -> list:
        """
        Retrieve list of categories
        """
        return self.categories

    def _load_share_limit_rules(self, raw_rules: Any) -> list[ShareLimitRule]:
        if isinstance(raw_rules, dict):
            logging.error(
                "Share limit rules must use TOML array tables, e.g. [[share_limits]]"
            )
            sys.exit(1)

        rules = []
        for index, raw_rule in enumerate(raw_rules, start=1):
            rules.append(self._build_share_limit_rule(raw_rule=raw_rule, index=index))

        return rules

    def _build_share_limit_rule(self, *, raw_rule: Any, index: int) -> ShareLimitRule:
        name = str(raw_rule.get("name") or f"share_limits[{index}]")
        tags = self._coerce_string_list(
            value=raw_rule.get("tags"),
            field_name="tags",
            rule_name=name,
        )
        trackers = self._coerce_string_list(
            value=raw_rule.get("trackers"),
            field_name="trackers",
            rule_name=name,
        )

        if not tags and not trackers:
            self._fail_share_limit_rule(
                rule_name=name,
                message="at least one tag or tracker selector is required",
            )

        ratio_limit = raw_rule.get("ratio_limit")
        seeding_time_limit = raw_rule.get("seeding_time_limit")
        inactive_seeding_time_limit = raw_rule.get("inactive_seeding_time_limit")
        share_limit_action = raw_rule.get("share_limit_action")

        if (
            ratio_limit is None
            and seeding_time_limit is None
            and inactive_seeding_time_limit is None
            and share_limit_action is None
        ):
            self._fail_share_limit_rule(
                rule_name=name,
                message="at least one share limit value is required",
            )

        self._validate_ratio_limit(value=ratio_limit, rule_name=name)
        self._validate_time_limit(
            value=seeding_time_limit,
            field_name="seeding_time_limit",
            rule_name=name,
        )
        self._validate_time_limit(
            value=inactive_seeding_time_limit,
            field_name="inactive_seeding_time_limit",
            rule_name=name,
        )
        self._validate_share_limit_action(
            value=share_limit_action,
            rule_name=name,
        )

        return ShareLimitRule(
            name=name,
            tags=tags,
            trackers=trackers,
            ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit,
            inactive_seeding_time_limit=inactive_seeding_time_limit,
            share_limit_action=share_limit_action,
        )

    def _coerce_string_list(
        self, *, value: Any, field_name: str, rule_name: str
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            values = [value]
        else:
            try:
                values = list(value)
            except TypeError:
                self._fail_share_limit_rule(
                    rule_name=rule_name,
                    message=f"{field_name} must be a string or list of strings",
                )

        clean_values = []
        for item in values:
            if not isinstance(item, str):
                self._fail_share_limit_rule(
                    rule_name=rule_name,
                    message=f"{field_name} must contain only strings",
                )
            item = item.strip()
            if item:
                clean_values.append(item)

        return clean_values

    def _validate_ratio_limit(self, *, value: Any, rule_name: str) -> None:
        if value is None:
            return

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._fail_share_limit_rule(
                rule_name=rule_name,
                message="ratio_limit must be a number",
            )

        if value < 0 and value not in {-1, -2}:
            self._fail_share_limit_rule(
                rule_name=rule_name,
                message="ratio_limit must be -2, -1, or greater than or equal to 0",
            )

    def _validate_time_limit(
        self, *, value: Any, field_name: str, rule_name: str
    ) -> None:
        if value is None:
            return

        if isinstance(value, bool) or not isinstance(value, int):
            self._fail_share_limit_rule(
                rule_name=rule_name,
                message=f"{field_name} must be an integer number of minutes",
            )

        if value < 0 and value not in {-1, -2}:
            self._fail_share_limit_rule(
                rule_name=rule_name,
                message=f"{field_name} must be -2, -1, or greater than or equal to 0",
            )

    def _validate_share_limit_action(self, *, value: Any, rule_name: str) -> None:
        if value is None:
            return

        if value not in SUPPORTED_SHARE_LIMIT_ACTIONS:
            actions = ", ".join(sorted(SUPPORTED_SHARE_LIMIT_ACTIONS))
            self._fail_share_limit_rule(
                rule_name=rule_name,
                message=f"share_limit_action must be one of: {actions}",
            )

    def _fail_share_limit_rule(self, *, rule_name: str, message: str) -> None:
        logging.error(f"Invalid share limit rule `{rule_name}`: {message}")
        sys.exit(1)
