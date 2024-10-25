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


## Run the pipeline

Choose some interesting scans to work on and put them into a directory,
for example:

```sh
$ ls my_scans
AF_Mut_20009_Kat_AF5146_AF5147_j2005.pdf
HG_Mut_3099_Kat_HG7689_j2000.pdf
WD_Mut_20117_Kat_WD8963_WD8964_WD8965_j2007.pdf
```

To run the pipeline, execute the following command:

```sh
$ venv/bin/python3 src/process.py --scans my_scans --workdir workdir
START 20009
START 20117
START HG3099
SUCCESS HG3099
SUCCESS 20117
SUCCESS 20009
```

You’ll find the output of each pipeline step inside `workdir`.