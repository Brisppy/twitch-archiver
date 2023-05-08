FROM jrottenberg/ffmpeg:5-ubuntu
RUN apt update \
    && apt install python3 python3-pip --no-install-recommends -y \
    && rm /var/lib/apt/lists/*.lz4

RUN pip install twitch-archiver

ENTRYPOINT [ "twitch-archiver" ]
