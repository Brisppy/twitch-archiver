FROM jrottenberg/ffmpeg:5-ubuntu
WORKDIR /
RUN apt update \
    && apt install python3 python3-pip git --no-install-recommends -y \
    && git clone https://github.com/Brisppy/twitch-archiver.git \
    && rm /var/lib/apt/lists/*.lz4 \
    && pip install -r /twitch-archiver/requirements.txt
WORKDIR /twitch-archiver
ENTRYPOINT [ "python3", "twitch-archiver.py" ]