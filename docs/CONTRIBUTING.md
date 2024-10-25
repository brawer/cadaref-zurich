# How to contribute

Welcome! Here’s how to contribute to this project.

## Set up development machine

### macOS

If you work on macOS, install [Homebrew](https://brew.sh/) and run
the following commands on a terminal:

```sh
brew install gdal git libtiff opencv poppler python3
git clone https://github.com/brawer/cadaref-zurich.git
cd cadaref-zurich
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python3 src/process.py --scans=/path/to/scans
```

### Linux

If you work on Debian Linux, set up your machine like this:

```sh
apt-get update
apt-get install -y gdal-bin git libopencv-dev libtiff-tools poppler-utils python3 python3-venv
git clone https://github.com/brawer/cadaref-zurich.git
cd cadaref-zurich
python3 -m venv venv
venv/bin/pip install -r	requirements.txt
venv/bin/python3 src/process.py --scans=/path/to/scans
```

For Alpine Linux, see our [Containerfile](../Containerfile).
Other Linux distributions may use slightly different package names;
please refer to your system’s documentation.
