# syntax=docker/dockerfile:1
#
# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT
#
# Build configuration for a Linux Container to automatically georeference
# scanned historical maps (cadastral mutation plans) of the City of Zürich.

FROM alpine:3.20.3 AS cadaref-builder
ARG BUILDKIT_SBOM_SCAN_STAGE=true
RUN apk add --no-cache cargo gdal-dev git rust
WORKDIR /home/builder
RUN git clone --branch v0.1.1 --depth 1 --config advice.detachedHead=false \
    https://github.com/brawer/cadaref.git
RUN cd cadaref && cargo build --release && cargo test --release

FROM alpine:3.20.3

RUN apk add --no-cache  \
        gdal  \
        poppler-utils  \
        python3 py3-numpy py3-opencv py3-pillow  \
        tiff-tools

COPY  \
    --from=cadaref-builder  \
    /home/builder/cadaref/target/release/cadaref-match  \
    /usr/local/bin/cadaref-match

RUN adduser -S cadaref
USER cadaref
WORKDIR /home/cadaref

COPY src /home/cadaref/src
COPY survey_data /home/cadaref/survey_data

CMD ["python", "src/process.py", "--cadaref_tool", "/usr/local/bin/cadaref-match"]
