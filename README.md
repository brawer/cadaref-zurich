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
    ghcr.io/brawer/cadaref-zurich:v0.2.0
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

1. **Finding work:** The pipeline starts by listing the contents
of the input directory, looking for PDF files that match the
naming scheme used by the cadastral plan archive of the City of Zürich.
For each mutation, the pipeline checks if there’s a log file from
previous run. If no log file can be found, the mutation is put on
a work queue for processing.

2. **Text extraction:** In `workdir/text`, the pipeline stores the
plaintext for every mutation as found by means of Optical Character
Recognition (OCR). To produce its archival PDF/A files, the document
scanning center of the City of Zürich uses
[Kodak Capture Pro](https://support.alarisworld.com/en-us/capture-pro-software).
While developing this pipeline for georeferencing historical cadastral plans,
we evaluated various alternative OCR systems:
[Tesseract](https://tesseract-ocr.github.io/tessdoc/),
[Jaided EasyOCR](https://www.jaided.ai/easyocr_enterprise/),
[Microsoft Document Intelligence](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read),
[Apple Vision API](https://developer.apple.com/documentation/vision),
[Google Document AI](https://cloud.google.com/document-ai),
and [Amazon Textract](https://aws.amazon.com/textract/).
However, the OCR engine of Kodak Capture Pro
gave the best quality for the input dataset.
Therefore, the current version of the pipeline simply extracts
the embedded plaintext from the PDF/A input. For PDF parsing
and layout analysis, is uses the [Poppler](https://poppler.freedesktop.org/)
library.

3. **Rendering:** The pipeline converts every page in the input PDF
to a tiled, 24-bit color, single-page TIFF image with gzip compression.
For PDF rendering, we use [Poppler](https://poppler.freedesktop.org/)
and [Cairo](https://www.cairographics.org/).

4. **Page splitting:** In `workdir/rendered`, the pipeline stores a
tiled, gzip-compressed, 24-bit color, multi-page TIFF image file
for every mutation dossier. In the output of the previous step,
the pipeline detects glued-together pages and splits them in two halves
along the middle fold. Possibly to save time, the human scanning operators
occasionally happened to merge two separate DIN A4 pages into a single A3
page with landscape orientation. However, sometimes a historical cadastral
plan really was in landscape DIN A3 format, so we cannot blindly split
all A3 pages. Likewise, the scan contractors did not bother to separate
the left and right halves when scanning bound tomes of the early 20th century;
and again, we cannot blindly split everything because sometimes, a single
historical map really does span two pages. Initially, we detected this
situation algorithmically, by means of image analysis.
Ultimately, however, we settled on looking for certain keywords
in the OCRed text. Looking for certain keywords is much simpler and turned
out to be more reliable.

5. **Thresholding:** In `workdir/thresholded`, the pipeline stores
a thresholded (binarized) version of the rendered image as a tiled,
multi-page, black-and-white TIFF image in [Telefax CCITT Group 4 compression](https://en.wikipedia.org/wiki/Group_4_compression). The pipeline chooses a suitable
threshold for each page by means of the classic [Ōtsu method](https://en.wikipedia.org/wiki/Otsu%27s_method). However, the Zürich mutation plan archive
contains a handful of very dark scans where the Ōtsu method did not
perform well. The pipeline detects this, and applies a custom workaround
to handle it. Also at this stage, the pipeline runs some basic image
pre-processing algorithms to clean up scanning artifacts. For example,
a morphological operation is used to remove small dust speckles.

6. **Detecting screenshots:** Some mutation dossiers of the late 1990s
and early 2000s contain printed-out screenshots of a Microsoft Windows
database. At the time, this Windows tool was used to manage the
cadastral register, and Windows screenshots were regularly printed out
and archived.  Because these screenshot print-outs look like maps
(they have long thin lines like a cadastral plan), our pipeline needs
to detect them. We experimented with computer vision, but by far the
easiest and most reliable way to detect screenshots was to look at the
OCRed text. The pipeline does not generate any special files for detected
screenshots, but it notes a list of screenshot pages in the logs.

7. **Detecting map scale:** The pipeline tries to find the map scale,
such as `1:500`, which is often (but not always) printed on the historical
map. If no scale designation can be found on the page, the pipeline falls
back to the other pages in the same mutation dossier because sometimes
the scale was given on the page next to the actual map. If this still
does not lead to any map scales, the pipeline supplies a fallback list
with map scales that commonly appear in the Zürich dataset.

8. **Measuring distance limit:** For every scanned page that hasn’t
been classified as a screenshot, the pipeline measures the maximum
distance between any two points assuming it’s a map.  The inputs to
this computation are the map scale, the width and height of the
rendered image in raster pixels, and the resolution of the rendered
image in dots per inch (dpi). For example, if the detected map scale
is 1:1000, and the image is 2480×3508 pixels at 300 dpi, the scanned
page is 21.0×29.7 centimeters (DIN A4). At scale 1:1000, this
corresponds to 210×297 meters on the ground. Thus, the distance
between any two points depicted on this map can’t be more than
√(210² + 297²) = 363.7 meters.  We’ll need this value in the next step.

9. **Estimating mutation bounds:** In `workdir/bounds`, the pipeline
stores a GeoJSON file with the approximate bounds of the mutation.
The bounds are approximated by looking up the parcel numbers, found by
means of Optical Character Recognition, in the survey data of December
2007.  This will capture any parcels whose numbers are mentioned in
the text documentation for the mutation, and any parcels whose numbers
were printed on the map (provided OCR managed to read the text).
Also, today’s land survey database stores for every parcel by what
mutation it got created. In case our historic mutation has created
parcels that that still happen to exist today, we incorporate their
bounds into our estimation. If the estimated bounds are smaller than
the distance limit (the maximal distance covered by the map) from the
previous step, we grow the bounding box accordingly. — If no bounds
can be found, the pipeline stops processing the mutation with status
`BoundsNotFound`.

10. **Symbol recognition:** In `workdir/symbols`, the pipeline stores
a CSV file that tells which symbols have been recognized on the historical
map images by means of computer vision. The CSV file contains the
following columns: `page` for the document page, `x` and `y` for
the pixel coordinates on that page (which can be fractional because
symbol recognition works on an enhanced-resolution image), and
`symbol` with the detected symbol type. — If there’s not a single page
in the dossier with at least four cartographic symbols, the pipeline
stops processing this mutation with status `NotEnoughSymbols`.

11. **Survey data extraction:** In `workdir/points`, the pipeline
stores a CSV file with the geographic points (survey markers, fixed
points) that are likely to have been drawn on the historical cadastral
map.  The CSV file contains the following columns: `id`, `x`, `y` and
`symbol`.  The latter is the cartographic symbol type likely to be
used on the map, inferred from known properties of the feature
(eg. whether or not a marker has been secured with a metal
bolt). Essentially, this is an excerpt of the cadastral survey data,
limited to the geographical area found earlier in the **Bounds
estimation** stage.  To the extent possible, the pipeline further
restricts this set of points to those that actually existed at the
time the map was drawn. For example, a survery marker that existed
between 1969 and 1992 would included when georeferencing a historical
map from 1984, but not when georeferencing a map from 1930 or 1999. We
allow for some slack (up to a year) in date comparisions, in case the
recorded dates were not fully accurate. The set of points is taken
from two sources: The land survey database as of 2007, and a list of
[deleted points](src/deleted_points.csv) that we recovered (and
manually checked) from scanned and OCRed point deletion logs that
happened to get archived by the City of Zürich.

12. **Georeferencing:** In `workdir/georeferenced`, the pipeline stores
geo-referenced imagery in Cloud-Optimized GeoTIFF format. The georeferencing
is done by calling the [Cadaref tool](https://github.com/brawer/cadaref)
with the rendered image, map scale, symbols and points that were found
by the previous steps. If an image could not be georeferenced, the pipeline
stores it in TIFF format in `workdir/not_georeferenced`.


In `workdir/logs`, the pipeline stores a log file for every
mutation.

In `workdir/tmp`, the pipeline stores temporary files. We do not use `/tmp`
because some of our temporary files can be very large, and we do not
want to exhaust physical memory in case `/tmp` happens to be implemented
by a [tmpfs file system](https://en.wikipedia.org/wiki/Tmpfs) on the
worker machine.

To maximize throughput, the pipeline will concurrently process several
mutation files on a multi-processor machine.


## Contributing

If you’d like to work on this pipeline, please have a look at
the [developer guidelines](docs/CONTRIBUTING.md). Your contributions
would be very welcome.


## License

Copyright 2024 by Sascha Brawer, released under the [MIT license](LICENSE).
