FROM jrottenberg/ffmpeg:5-ubuntu

# install required packages
RUN apt update && apt install python3 python3-pip --no-install-recommends -y

# copy repository files
COPY . /app
WORKDIR /app

# build and install twitch-archiver locally
RUN python3 -m pip install -e . --break-system-packages

ENTRYPOINT [ "twitch-archiver" ]
