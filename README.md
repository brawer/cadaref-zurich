# Cadaref Zürich

## Usage

To run the georeferencing pipeline on a workstation, install a container
runtime such as [Docker](https://www.docker.com/products/docker-desktop/)
or [Podman](https://podman.io/docs/installation). Then, execute the following
commands in a shell.

Instead of `path/to/scans`, pass the file path to a directory on your
workstation. The directory (or any of its sub-directories) should
contain scanned cadastral plans in PDF format.

The pipeline will write its intermediate files and the final output
to `workdir`. If the process is interrupted, for example because
the workstation is turned off, you can restart the pipeline with
the same command; it will just continue to work.

For security reasons, we highly recommend to disable network access
by passing `--network none` to the container runtime.

```sh
mkdir workdir
docker run \
    --network none   \
    --mount type=bind,src=path/to/scans,dst=/home/cadaref/scans,readonly   \
    --mount type=bind,src=./workdir,dst=/home/cadaref/workdir  \
    ghcr.io/brawer/cadaref-zurich:latest
```

## Output

The pipeline creates a set of  sub-directories in `workdir`. The file
names are mutation IDs in the same form as they are used in the cadastral
survey, for example `21989` or `HG3099`. Sometimes, multiple input files
refer to the same mutation; in that case, the pipeline assembles the parts
into a single file for each mutation.

* `text`: Plaintext, extracted by means of Optical Character Recognition (OCR).
After experiementing with various OCR systems (Tesseract, EasyOCR,
and the commercial OCR systems from Apple, Microsoft and Google),
we decided to simply take the text that is embedded into the PDF/A files
because it had the best OCR quality of all tested systems.

* `rendered`: The input converted to tiled, compressed, multi-page
color TIFF images.

* `thresholded`: The rendered files as tiled, compressed, multi-page
black-and-white TIFF images. The threshold between black and white
is chosen depending by means of classic [Ōtsu thresholding](https://en.wikipedia.org/wiki/Otsu%27s_method) with a custom tweaks to handle very dark scans.


## License

Copyright 2024 by Sascha Brawer, released under the [MIT license](LICENSE).
