FROM alpine:3.16

ENV PYTHONPATH="/root"

COPY requirements.txt /
COPY torrent-manager-cron /var/spool/cron/crontabs/root

COPY src/ /root/src/

RUN apk add --update --no-cache python3 && \
    rm -rf /var/cache/* && \
    mkdir /var/cache/apk && \
    ln -sf python3 /usr/bin/python && \
    python3 -m ensurepip && \
    pip3 install --no-cache --upgrade pip && \
    pip3 install -r requirements.txt

CMD ["/usr/sbin/crond", "-f"]