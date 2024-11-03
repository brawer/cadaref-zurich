# How to contribute

Welcome! Here’s how to contribute to this project.

## Set up development machine

### macOS

If you work on macOS, install [Homebrew](https://brew.sh/) and run
the following commands on a terminal:

```sh
brew install cargo git
git clone https://github.com/brawer/cadaref.git
cd cadaref
cargo build --release
cargo test --release
cd ..

brew install gdal git libtiff opencv poppler python3
git clone https://github.com/brawer/cadaref-zurich.git
cd cadaref-zurich
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python3 src/process.py --scans=/path/to/scans
```

### Linux

If you work on Debian Linux v12 (Bookworm), set up your machine like this:

```sh
apt-get update
apt-get install -y curl build-essential gcc git libgdal-dev pkg-config
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sudo sh
git clone https://github.com/brawer/cadaref.git
cd cadaref
cargo build --release
cargo test --release
cd ..

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


## Visualize symbol detection

To visualize symbol detection, run the following command. It will
produce a TIFF file `HG3099.symbols.tif` in which the detected
cartographic symbols are highlighted in color.

```sh
venv/bin/python3 src/debug_symbol_detection.py --rendered=workdir/rendered/HG3099.tif
```

To generate input for `debug_symbol_detection.py` without running
the entire pipeline, do the following. This will work for any input,
even if it is very different from the cadastral mutation plans
in the archives of the City of Zürich.

```sh
pdftocairo -tiff -r 300 sample.pdf
venv/bin/python3 src/debug_symbol_detection.py --rendered sample-1.tif
```

## Change the source code

To change the source code of the pipeline, use any editor of your choice.
Re-run the pipeline and check out the results. Note that the pipeline
caches intermediate results, so you may or may not want to delete
`workdir` after each edit depending on your task.

Once you’re happy with your changes, make a GitHub pull request.


## Release a new version

After a series of changes have been merged into the code repository,
it’s time to release a new version of the pipeline. To see all
versions ever released, use the `git tag` command. To tag a new
release, for example `v0.1.2`, do this:

```sh
git tag v0.1.2
git push origin v0.1.2
```

After you’ve pushed a fresh release tag to GitHub, an automated workflow
will build and deploy a fresh container, including a Software Bill of
Materials (SBOM), to the
project’s [Container Registry](https://github.com/brawer/cadaref-zurich/pkgs/container/cadaref-zurich) on GitHub. In addition, the GitHub workflow will
automatically create and publish an [Attestation of provencance](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds) for the build.
