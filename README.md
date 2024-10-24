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
While developing the cadastral georeferencing pipeline,
we had evaluated various other OCR systems:
([Tesseract](https://tesseract-ocr.github.io/tessdoc/),
[Jaided EasyOCR](https://www.jaided.ai/easyocr_enterprise/),
[Microsoft Document Intelligence](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read),
[Apple Vision API](https://developer.apple.com/documentation/vision),
[Google Document AI](https://cloud.google.com/document-ai),
and [Amazon Textract](https://aws.amazon.com/textract/)).
Perhaps surprisingly, the OCR engine in Kodak Capture Pro
gave the best quality for Zürich’s historical cadastral plans.
Therefore, the current version of the pipeline simply extracts
the embedded plaintext that Kodak Capture Pro stored in the PDF/A input,
with [Poppler](https://poppler.freedesktop.org/) for layout analysis.

2. **Rendering:** In `workdir/rendered`, the pipeline stores a
tiled, zip-compressed, multi-page color TIFF image for every mutation dossier.
Sometimes, a single scanned page contains a mutation plan next to a table
or some text. Initially, we had used image analysis to detect this situation,
but ultimately we settled on looking for certain keywords in the recognized
text.

3. **Thresholding:** In `workdir/thresholded`, the pipeline stores
a thresholded (binarized) version of the rendered image as a tiled,
telefax-compressed, multi-page, black-and-white TIFF image. The threshold
value is automatically chosen by means of the classic [Ōtsu method](https://en.wikipedia.org/wiki/Otsu%27s_method). However, the mutation plan archive
contains some scans where the Ōtsu method did not perform very well;
the pipeline detects this and applies a custom workaround.

4. TODO: Continue description.


## License

Copyright 2024 by Sascha Brawer, released under the [MIT license](LICENSE).
