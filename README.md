# Cadaref Zürich

## Usage

To run the georeferencing pipeline on a workstation, install a container
runtime such as [Docker](https://www.docker.com/products/docker-desktop/)
or [Podman](https://podman.io/docs/installation). Then, execute the following
commands in a shell; `path/to/scans` is the file path of a directory with
scanned cadastral plans in PDF format. The pipeline will read the scans,
process them, and write its output to `workdir`. For security reasons,
we highly recommnd to disable networking by passing `--network none`.

````sh
$ mkdir workdir
$ docker run \
    --network none   \
    --mount type=bind,src=path/to/scans,dst=/home/cadaref/scans,readonly   \
    --mount type=bind,src=./workdir,dst=/home/cadaref/workdir  \
    ghcr.io/brawer/cadaref-zurich:latest
```