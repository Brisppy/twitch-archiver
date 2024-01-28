FROM jrottenberg/ffmpeg:5-ubuntu
RUN apt update \
    && apt install curl python3.9 python3.9-distutils --no-install-recommends -y \
    && rm /var/lib/apt/lists/*.lz4
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py \
    && python3.9 get-pip.py \
    && rm get-pip.py \
    && apt remove curl -y

RUN pip3.9 install twitch-archiver

ENTRYPOINT [ "twitch-archiver" ]
