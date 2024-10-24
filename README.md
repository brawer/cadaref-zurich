# Cadaref Zürich

## Usage

To run the georeferencing pipeline on a workstation, install a container
runtime such as [Docker](https://www.docker.com/products/docker-desktop/)
or [Podman](https://podman.io/docs/installation). Then, execute the following
commands in a shell. Instead of `path/to/scans`, pass the file path to
a directory on your workstation with scanned cadastral plans in PDF format.
The pipeline will write its output to `workdir`, in particular the
`georeferenced` subdirectory. If the pipeline gets interrupted (for example
because the workstation is turned off), it will pick up its work upon
getting started again. For security reasons, we highly recommnd to disable
network access by passing `--network none`.

````sh
mkdir workdir
docker run \
    --network none   \
    --mount type=bind,src=path/to/scans,dst=/home/cadaref/scans,readonly   \
    --mount type=bind,src=./workdir,dst=/home/cadaref/workdir  \
    ghcr.io/brawer/cadaref-zurich:latest
```


## License

Copyright 2024 by Sascha Brawer, released under the [MIT license](LICENSE).
