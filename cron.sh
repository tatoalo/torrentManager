#!/bin/sh

LAUNCHER_SCRIPT="/usr/bin/python src/launcher.py"
CLEANER_SCRIPT="/usr/bin/python src/cleaner.py"

LAUNCHER_COMMAND="${LAUNCHER_SCRIPT}"
CLEANER_COMMAND="${CLEANER_SCRIPT}"

clean_crontab () {
    crontab -l | grep -v $1 | crontab -
}

activate_crontab () {
    crond -f
}

# Checking for HC_UUID_LAUNCHER
if [[ "${HC_UUID_LAUNCHER}" ]]; then
    echo "** Capturing ID for monitoring launcher cron **"
    LAUNCHER_COMMAND="${LAUNCHER_COMMAND} && curl -sS --retry 2 -o /dev/null https://hc-ping.com/${HC_UUID_LAUNCHER}"
fi

# Checking for HC_UUID_CLEANER
if [[ "${HC_UUID_CLEANER}" ]]; then
    echo "** Capturing ID for monitoring cleaner cron **"
    CLEANER_COMMAND="${CLEANER_COMMAND} && curl -sS --retry 2 -o /dev/null https://hc-ping.com/${HC_UUID_CLEANER}"
fi

# Checking for custom LAUNCHER_CRON
if [[ "${LAUNCHER_CRON}" ]]; then
    echo "** Setting custom schedule for launcher **"
    clean_crontab "launcher"
    crontab -l | { cat; echo "${LAUNCHER_CRON} ${LAUNCHER_COMMAND}"; } | crontab -
else
    echo "No custom cron for the launcher has been defined, sticking with default scheduling."
fi

# Checking for custom CLEANER_CRON
if [[ "${CLEANER_CRON}" ]]; then
    echo "** Setting custom schedule for cleaner **"
    clean_crontab "cleaner"
    crontab -l | { cat; echo "${CLEANER_CRON} ${CLEANER_COMMAND}"; } | crontab -
else
    echo "No custom cron for the cleaner has been defined, sticking with default scheduling."
fi

activate_crontab