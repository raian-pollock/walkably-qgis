"""Walkably QGIS plugin: the part that fetches the data and builds the layers.

No window code lives here, so it can run headless (the tests do). The window code is in walkably_plugin.py.

Network: only fetch_file() touches the network, and only when the user clicked an action. Each file of the dated
folder is downloaded once, checked against the folder's SHA256SUMS, and kept in the QGIS profile folder.
"""
import hashlib
import os

from qgis.PyQt.QtCore import QEventLoop, Qt, QUrl
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsAction,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFileDownloader,
    QgsGraduatedSymbolRenderer,
    QgsLayerMetadata,
    QgsPointXY,
    QgsProject,
    QgsRendererRange,
    QgsSymbol,
    QgsVectorLayer,
)

try:  # QGIS 3.30 and later, and all of QGIS 4
    from qgis.core import Qgis
    _OPEN_URL = Qgis.AttributeActionType.OpenUrl
except AttributeError:  # QGIS 3.22 to 3.28
    _OPEN_URL = QgsAction.OpenUrl

# The ONE place that names the dated data folder. A newer folder is a one-line change here.
DATA_FOLDER = "https://data.walkably.org/download/gis-sample/2026-11-07/"

GPKG_NAME = "walkably-sample-hamburg-barcelona.gpkg"
CITIES_NAME = "cities.csv"
SUMS_NAME = "SHA256SUMS"

# The credit line from the folder's README.md. Licence terms: it must be shown with any map or copy that is shared.
CREDIT = (
    "Contains information from Walkably, https://walkably.org, available under the ODbL. "
    "Contains information from OpenStreetMap, © OpenStreetMap contributors, "
    "https://www.openstreetmap.org/copyright, available under the ODbL."
)
LICENSE_NAME = "Open Database License (ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/"
DATA_PAGE = "https://walkably.org/data/"

# Five classes on the website's fixed Europe-wide score scale (edges 43, 64, 80, 85) and its colours.
# The website map splits the top into two narrow bands (85 to 88, 88 and over); here they are one class.
CLASSES = [
    (0, 43, "#fefad5", "Under 43"),
    (43, 64, "#c2e2ab", "43 to 64"),
    (64, 80, "#83caac", "64 to 80"),
    (80, 85, "#2da8b0", "80 to 85"),
    (85, 100, "#446292", "85 and over"),
]

CELL_LAYERS = (
    # (table in the GeoPackage, layer name in QGIS, city name)
    ("hamburg_cells", "Walkably Hamburg cells (sample)", "Hamburg"),
    ("barcelona_cells", "Walkably Barcelona cells (sample)", "Barcelona"),
)
CITIES_LAYER_NAME = "Walkably cities (Europe)"


class WalkablyError(Exception):
    """Something the user can read: a download failed, a file was damaged, a layer would not load."""


def cache_dir():
    """Where the downloaded files are kept: one folder per dated data folder, inside the QGIS profile."""
    date = DATA_FOLDER.rstrip("/").rsplit("/", 1)[-1]
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "walkably", date)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(url, dest, progress=None):
    """Download one URL to one file with QGIS's own network stack (proxy and certificate settings apply).

    progress: optional QProgressDialog-like object (setMaximum, setValue, wasCanceled).
    """
    result = {}
    loop = QEventLoop()
    downloader = QgsFileDownloader(QUrl(url), dest, delayStart=True)

    def on_progress(received, total):
        if progress is not None:
            progress.setMaximum(max(total, 0))
            progress.setValue(received)
            if progress.wasCanceled():
                downloader.cancelDownload()

    downloader.downloadCompleted.connect(lambda _url: result.setdefault("ok", True))
    downloader.downloadError.connect(lambda errors: result.setdefault("error", "; ".join(errors)))
    downloader.downloadCanceled.connect(lambda: result.setdefault("error", "cancelled"))
    downloader.downloadProgress.connect(on_progress)
    downloader.downloadExited.connect(loop.quit)
    downloader.startDownload()
    loop.exec()
    if not result.get("ok"):
        raise WalkablyError("Could not download %s (%s)" % (url, result.get("error", "unknown error")))


def fetch_file(name, progress=None):
    """Return the local path of one file of the data folder, downloading it first if it is not here yet.

    The file is checked against the folder's SHA256SUMS. A damaged download is deleted, never used.
    """
    folder = cache_dir()
    os.makedirs(folder, exist_ok=True)
    sums_path = os.path.join(folder, SUMS_NAME)
    if not os.path.exists(sums_path):
        _download(DATA_FOLDER + SUMS_NAME, sums_path)
    sums = {}
    with open(sums_path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1].lstrip("*")] = parts[0].lower()
    if name not in sums:
        raise WalkablyError("%s is not listed in %s%s" % (name, DATA_FOLDER, SUMS_NAME))
    path = os.path.join(folder, name)
    if os.path.exists(path) and _sha256(path) == sums[name]:
        return path
    _download(DATA_FOLDER + name, path, progress)
    if _sha256(path) != sums[name]:
        os.remove(path)
        raise WalkablyError("%s was damaged on the way (checksum differs). Please try again." % name)
    return path


def _metadata(title, abstract):
    md = QgsLayerMetadata()
    md.setTitle(title)
    md.setAbstract(abstract)
    md.setRights([CREDIT])
    md.setLicenses([LICENSE_NAME])
    return md


def _finish(layer, title, abstract):
    """Credit line, licence and a readable name on a layer."""
    layer.setMetadata(_metadata(title, abstract))
    layer.setAbstract(abstract)
    server = layer.serverProperties() if hasattr(layer, "serverProperties") else layer
    if hasattr(server, "setAttribution"):
        server.setAttribution(CREDIT)  # shows as the layer's attribution in QGIS and in QGIS Server
        server.setAttributionUrl("https://walkably.org")


def _graduate(layer, field, points=False):
    ranges = []
    for lower, upper, colour, label in CLASSES:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(colour))
        sl = symbol.symbolLayer(0)
        if points:  # a dark ring so the pale dots show
            sl.setStrokeColor(QColor("#211f26"))
            sl.setStrokeWidth(0.3)
            symbol.setSize(3.2)
        else:  # cells: no outline, 60,000 hairlines turn the map to mush
            sl.setStrokeStyle(Qt.PenStyle.NoPen)
        ranges.append(QgsRendererRange(lower, upper, symbol, label))
    layer.setRenderer(QgsGraduatedSymbolRenderer(field, ranges))


def build_cities_layer(csv_path):
    """The cities table as a point layer (WGS 84), graduated by score_typical_0_100, with a link to the city page."""
    uri = QUrl.fromLocalFile(csv_path).toString() + "?delimiter=,&xField=centre_lon&yField=centre_lat&crs=EPSG:4326&detectTypes=yes"
    layer = QgsVectorLayer(uri, CITIES_LAYER_NAME, "delimitedtext")
    if not layer.isValid():
        raise WalkablyError("QGIS could not read the cities table (%s)." % csv_path)
    _graduate(layer, "score_typical_0_100", points=True)
    layer.setDisplayExpression('"city"')
    layer.actions().addAction(
        QgsAction(_OPEN_URL, "Open the Walkably city page", '[% "city_page_url" %]')
    )
    _finish(
        layer,
        "Walkably cities (Europe)",
        "One point per Walkably city page, coloured by the typical walking score of the city (0 to 100). "
        "Field city_page_url holds the link to the city page.",
    )
    return layer


def build_cell_layers(gpkg_path):
    """The two sample cell layers, graduated by score. Returns {table: layer}."""
    layers = {}
    for table, name, city in CELL_LAYERS:
        layer = QgsVectorLayer("%s|layername=%s" % (gpkg_path, table), name, "ogr")
        if not layer.isValid():
            raise WalkablyError("QGIS could not read the layer %s in %s." % (table, gpkg_path))
        _graduate(layer, "score")
        layer.setCustomProperty("walkably/city", city)
        _finish(
            layer,
            name,
            "Walking score of %s as six-sided cells of 55 m sides (0 to 100). Sample layer: cells exist for "
            "Hamburg and Barcelona only." % city,
        )
        layers[table] = layer
    return layers


def nearer_cell_layer(layers, centre, centre_crs):
    """The cell layer whose centre is nearest the given map centre (the honest 'visible area' for a two-city sample)."""
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    here = QgsCoordinateTransform(centre_crs, wgs84, QgsProject.instance()).transform(QgsPointXY(centre))
    measure = QgsDistanceArea()
    measure.setSourceCrs(wgs84, QgsProject.instance().transformContext())
    measure.setEllipsoid("WGS84")
    return min(
        layers.values(),
        key=lambda layer: measure.measureLine(here, QgsPointXY(layer.extent().center())),
    )
