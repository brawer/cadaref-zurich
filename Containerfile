# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT
#
# Build configuration for a Linux Container to automatically georeference
# scanned historical maps (cadastral mutation plans) of the City of Zürich.

FROM alpine:3.20 AS cadaref-builder
RUN apk add --no-cache cargo gdal-dev git rust
WORKDIR /home/builder
RUN git clone https://github.com/brawer/cadaref.git
RUN cd cadaref && cargo build --release && cargo test --release

FROM alpine:3.20

RUN apk add --no-cache  \
    gdal  \
	poppler-utils  \
	python3 py3-numpy py3-opencv py-pillow  \
	tiff-tools

WORKDIR /home/cadaref

COPY  \
    --from=cadaref-builder  \
    /home/builder/cadaref/target/release/cadaref-match  \
    /usr/local/bin/cadaref-match

COPY src /home/cadaref/src

