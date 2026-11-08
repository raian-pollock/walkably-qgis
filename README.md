# Walkably for QGIS

Add Walkably walking scores to your QGIS project in one click.

Walkably scores how well people can reach daily needs on foot over real streets, for cities in Europe.
This plugin loads the free Walkably GIS sample into QGIS, already coloured by score.

## What it adds

Menu Plugins > Walkably, or the Walkably button on the toolbar:

- **Add Walkably cities (Europe).** One point per city for 528 cities in 31 countries, coloured by the typical walking
  score of the city (0 to 100). Each point carries a link to its city page: use the layer action "Open the Walkably
  city page".
- **Add Walkably sample cells (Hamburg, Barcelona).** The walking score of every street cell in the two sample cities
  (62,211 cells in Hamburg, 11,124 in Barcelona; each cell is six-sided, 55 m sides). The plugin zooms to the city
  that is nearer the middle of your map. Cells exist for these two cities only. The full data is at
  https://walkably.org/data/.
- **About the Walkably data.** The licence and the credit line.

Layers are named "Walkably ...", graduated in five classes on the website's fixed score scale (edges 43, 64, 80, 85),
and carry the credit line in their metadata (Layer Properties > Metadata > Rights).

## Data, credit and licence

The data is the Walkably free GIS sample, shared under the Open Database License (ODbL) 1.0
(https://opendatacommons.org/licenses/odbl/1-0/). Show this credit line with any map or copy you share:

> Contains information from Walkably, https://walkably.org, available under the ODbL. Contains information from
> OpenStreetMap, © OpenStreetMap contributors, https://www.openstreetmap.org/copyright, available under the ODbL.

If you share a changed version of the data, it must also be under the ODbL.

The plugin code is GPL-2.0-or-later (see LICENSE).

## Network and privacy

Nothing is downloaded when QGIS starts. When you click an action, the plugin downloads the files it needs from one
dated folder (`https://data.walkably.org/download/gis-sample/2026-11-07/`), once. It checks them against the
checksums in that folder and keeps them in your QGIS profile folder (`walkably/2026-11-07/`). The sample cell file is
19.5 MB; the cities table is 141 KB. It sends no data about you or your project.

## Install

From the QGIS plugin manager (Plugins > Manage and Install Plugins), search for "Walkably". To install from a zip: zip
the `walkably` folder of this repository (the zip holds that one folder), then Plugins > Manage and Install Plugins >
Install from ZIP.

Works with QGIS 3.22 and later, including QGIS 4 (tested on 3.44 and 4.2).

## For developers

- `walkably/walkably_core.py`: data download, layers and styling. No window code; tested headless.
- `walkably/walkably_plugin.py`: the menu, the toolbar button and the click handlers.
- The dated data folder is one constant, `DATA_FOLDER`, in `walkably_core.py`. A newer folder is a one-line change
  (check that the file names and the credit line in its README are the same).

Questions and bug reports: https://github.com/raian-pollock/walkably-qgis/issues or hello@walkably.org
