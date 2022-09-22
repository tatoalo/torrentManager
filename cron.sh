#!/bin/sh

clean_crontab () {
    crontab -l | grep -v $1 | crontab -
}

activate_crontab () {
    crond -f
}

# Checking for custom LAUNCHER_CRON
if [[ "${LAUNCHER_CRON}" ]]; then
    echo "** Setting custom schedule for launcher **"
    clean_crontab "launcher"
    crontab -l | { cat; echo "${LAUNCHER_CRON} /usr/bin/python src/launcher.py"; } | crontab -
else
    echo "No custom cron for the launcher has been defined, sticking with default scheduling."
fi

# Checking for custom CLEANER_CRON
if [[ "${CLEANER_CRON}" ]]; then
    echo "** Setting custom schedule for cleaner **"
    clean_crontab "cleaner"
    crontab -l | { cat; echo "${CLEANER_CRON} /usr/bin/python src/cleaner.py"; } | crontab -
else
    echo "No custom cron for the cleaner has been defined, sticking with default scheduling."
fi

activate_crontab