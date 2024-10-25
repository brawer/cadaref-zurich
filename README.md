# Cadaref Zürich

## Usage

To run the georeferencing pipeline on a workstation, install a container
runtime such as [Docker](https://www.docker.com/products/docker-desktop/)
or [Podman](https://podman.io/docs/installation). Then, execute the following
commands in a shell.

As `path/to/scans`, pass the file path to a directory on your
workstation. This directory (or any of its sub-directories) should
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

## Pipeline

The pipeline works in stages. Each stage creates a sub-directory in
`workdir` that contains data (typically an image, text, or a CSV file)
for every cadastral mutation. The file names are the same short
mutation identifiers that also appear in the present-day cadastral
database, for example `21989` or `HG3099`.  Sometimes, the scanning
process has split a mutation file into multiple PDFs, possibly when
the historical documents happened to get archived in separate physical
folders. In this case, the pipeline assembles the various parts together,
so we always have all data for a mutation in a single file.

The pipeline consists of the following stages:

1. **Text extraction:** In `workdir/text`, the pipeline stores the
plaintext for every mutation as found by means of Optical Character
Recognition (OCR). To produce its archival PDF/A files, the document scanning
center of the City of Zürich happened to run [Kodak Capture Pro](https://support.alarisworld.com/en-us/capture-pro-software).
While developing this pipeline for georeferencing historical cadastral plans,
we evaluated various alternative OCR systems:
[Tesseract](https://tesseract-ocr.github.io/tessdoc/),
[Jaided EasyOCR](https://www.jaided.ai/easyocr_enterprise/),
[Microsoft Document Intelligence](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read),
[Apple Vision API](https://developer.apple.com/documentation/vision),
[Google Document AI](https://cloud.google.com/document-ai),
and [Amazon Textract](https://aws.amazon.com/textract/).
However, the OCR engine of Kodak Capture Pro
gave  the best quality for the input dataset.
Therefore, the current version of the pipeline simply extracts
the embedded plaintext from the PDF/A input. For PDF parsing
and layout analysis, is uses the [Poppler](https://poppler.freedesktop.org/)
library.

2. **Rendering:** In `workdir/rendered`, the pipeline stores a
tiled, zip-compressed, multi-page color TIFF image for every mutation dossier.
Sometimes, a single scanned page contains a mutation plan that was glued
next to a table or some text. In its rendering stage, the pipeline detetects
such glued-together pages and vertically splits them in two halves.
Initially, we had used (rather complex) image analysis to detect this
situation. Ultimately, however, we settled on looking for certain keywords
in the OCRed text; this was both simpler and more reliable.

3. **Screenshot detection:** Some mutation dossiers of the late 1990s
and early 2000s contain printed-out screenshots of a Microsoft Windows
database. At the time, this tool was used to manage the cadastral
register. Because these screenshots confuse the symbol recognition,
the pipeline detects them. The easiest and most reliable way to detect
screenshots was to look at the OCRed text.  The pipeline does not
generate special files for detected screenshots, but it notes a list
of screenshot pages in the logs.

4. **Thresholding:** In `workdir/thresholded`, the pipeline stores
a thresholded (binarized) version of the rendered image as a tiled,
multi-page, black-and-white TIFF image in [group 4 compression](https://en.wikipedia.org/wiki/Group_4_compression). The pipeline chooses a suitable
threshold for each page by means of the classic [Ōtsu method](https://en.wikipedia.org/wiki/Otsu%27s_method). However, the mutation plan archive
contains a handful of very dark scans where the Ōtsu method did not
perform well. The pipeline detects this case and applies a custom
workaround to handle it.

5. **Symbol recognition:** In `workdir/symbols`, the pipeline stores
a CSV file that tells which symbols have been recognized on the historical
map images by means of computer vision. The CSV file contains the
following columns: `page` for the document page, `x` and `y` for
the pixel coordinates on that page (which can be fractional because
symbol recognition works on an enhanced-resolution image), and
`symbol` with the detected symbol type.

6. **Survey data extraction:** In `workdir/points`, the pipeline stores...

7. **Georeferencing:** In `workdir/georeferenced`, the pipeline stores...

In `workdir/logs/success`, the poipeline stores a log file for every
mutation whose plans could be successfully georeferenced, wheras the logs
for failed attempts are logged in `workdir/logs/failed`.

In `workdir/tmp`, the pipeline stores temporary files. We do not use `/tmp`
because some of our temporary files can be very large, and we do not
want to exhaust physical memory in case `/tmp` happens to be implemented
by a [tmpfs file system](https://en.wikipedia.org/wiki/Tmpfs) on the
worker machine.

On a multi-core machine, the pipeline will process several mutation files
in parallel.


## Contributing

If you’d like to work on this pipeline, please have a look at
the [developer guidelines](docs/CONTRIBUTING.md). Your contributions
would be very welcome.


## License

Copyright 2024 by Sascha Brawer, released under the [MIT license](LICENSE).
