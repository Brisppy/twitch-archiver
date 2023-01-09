FROM jrottenberg/ffmpeg:5-ubuntu
WORKDIR /
RUN apt update \
    && apt install python3 python3-pip --no-install-recommends -y \
    && rm /var/lib/apt/lists/*.lz4
COPY . /twitch-archiver
WORKDIR /twitch-archiver
RUN pip install -r /twitch-archiver/requirements.txt
ENTRYPOINT [ "python3", "twitch-archiver.py" ]
