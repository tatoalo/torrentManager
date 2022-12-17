FROM alpine:edge

ENV PYTHONPATH="/root"
ENV TZ=Europe/Paris

COPY requirements.txt /
COPY --chmod=777 cron.sh /
COPY torrent-manager-cron /var/spool/cron/crontabs/root

COPY src/ /root/src/

RUN apk add --update --no-cache python3 curl tzdata && \
    rm -rf /var/cache/* && \
    mkdir /var/cache/apk && \
    ln -sf python3 /usr/bin/python && \
    python3 -m ensurepip && \
    pip3 install --no-cache --upgrade pip && \
    pip3 install -r requirements.txt

CMD [ "./cron.sh" ]