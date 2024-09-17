# Experimental scripts

This directory contains a hodgepodge of experimental one-off scripts
that were useful at some point in the project, but did not make it
to the final production pipeline.

* [extract_coordinates.py](extract_coordinates.py) was an experiment
  to extract geographic coordinates from scanned and OCRed mutation
  files. The extraction worked reasonably well, but ultimately we just
  needed the *deleted* points. For the other, non-deleted points
  today’s land survey database is a more reliable source.

* [extract_deleted_points.py](extract_deleted_points.py) and
  [check_deleted_points.py](check_deleted_points.py) were used to
  extract the records about deleted border points and deleted fixed
  points from scanned and OCRed mutation files. The output was then
  manually reviewed and corrected. Also, we ran the extracted
  coordinates through the [swisstopo REFRAME
  tool](https://www.swisstopo.admin.ch/de/koordinaten-konvertieren-reframe)
  for converting coordinates from the historical to the present-day
  spatial reference system.  The final version of the deleted points
  data file is in [src/deleted_points.csv](../deleted_points.csv).

* [find_datestamps.py](find_datestamps.py) was an experiment to
  heuristically extract date stamps using simple computer vision.
  The extraction seemed to work well, but utimately it did not seem
  worth the effort. The dates are only marginally relevant
  for the project whose main goal was georeferencing. Also, here’s
  quite a number of mutation files with multiple different datestamps,
  so this need manual inspection anyway.

* [find_stamp_ohne_grenzaenderung.py](find_stamp_ohne_grenzaenderung.py)
  was an experiment to identify stamps in mutation files. In the
  experiment, we looked for the stamp [Bestandesänderung ohne
  Grenzänderung](ohne_grenzaenderung.png), which the cadastral office
  used to mark mutations that did not modify any boundaries. However,
  the chosen extraction method, OpenCV template metching, did not
  perform very well on the data.  We quickly abandoned this experiment
  and did not try to identify the various other kinds of stamps that
  appear in the dataset.
  
  


  
  