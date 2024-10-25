# How to contribute

Welcome! Here’s how to contribute to this project.

## Set up development machine

### macOS

If you work on macOS, install [Homebrew](https://brew.sh/) and run
the following commands on a terminal:

```sh
brew install gdal git libtiff opencv poppler python3
git clone https://github.com/brawer/cadaref-zurich.git
git clone git@github.com:brawer/cadaref-zurich.git
cd cadaref-zurich
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### Linux

If you work on Debian Linux, set up your machine like this:

```sh
apt-get update
apt-get install -y gdal-bin git libtiff-dev libopencv-dev libpoppler-dev python3 python3-venv
git clone https://github.com/brawer/cadaref-zurich.git
cd cadaref-zurich
python3 -m venv venv
venv/bin/pip install -r	requirements.txt
```

Other Linux distributions may use different package names;
please refer to your system’s documentation to find their names.
For Alpine Linux, see our [Containerfile](../Containerfile).