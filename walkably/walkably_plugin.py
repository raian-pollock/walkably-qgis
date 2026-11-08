"""Walkably QGIS plugin: the menu, the toolbar button and what happens when the user clicks.

Nothing here runs at QGIS start-up except adding the menu entries. The network is used only inside the click
handlers (through walkably_core.fetch_file).
"""
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox, QProgressDialog, QToolButton
from qgis.core import QgsCoordinateTransform, QgsProject

from . import walkably_core as core

try:  # QGIS 3.30 and later, and all of QGIS 4
    from qgis.core import Qgis
    _INFO, _WARNING, _CRITICAL = Qgis.MessageLevel.Info, Qgis.MessageLevel.Warning, Qgis.MessageLevel.Critical
except AttributeError:  # QGIS 3.22 to 3.28
    from qgis.core import Qgis
    _INFO, _WARNING, _CRITICAL = Qgis.Info, Qgis.Warning, Qgis.Critical


class WalkablyPlugin:
    MENU = "&Walkably"

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar = None

    # ---- QGIS plugin interface -------------------------------------------------------------------------------
    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        window = self.iface.mainWindow()
        entries = (
            ("Add Walkably cities (Europe)", self.add_cities),
            ("Add Walkably sample cells (Hamburg, Barcelona)", self.add_cells),
            ("About the Walkably data (credit and licence)", self.about),
        )
        for text, slot in entries:
            action = QAction(icon, text, window)
            action.triggered.connect(lambda _checked=False, slot=slot: slot())
            self.iface.addPluginToMenu(self.MENU, action)
            self.actions.append(action)
        # One toolbar button that opens a small menu with the two "add" actions.
        self.toolbar = self.iface.addToolBar("Walkably")
        self.toolbar.setObjectName("WalkablyToolbar")
        button = QToolButton()
        button.setIcon(icon)
        button.setToolTip("Walkably: add walking scores to this project")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.addAction(self.actions[0])
        menu.addAction(self.actions[1])
        button.setMenu(menu)
        self.toolbar.addWidget(button)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.MENU, action)
        self.actions = []
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None

    # ---- the actions -----------------------------------------------------------------------------------------
    def add_cities(self):
        canvas_was_empty = not self.iface.mapCanvas().layers()
        try:
            path = self._fetch(core.CITIES_NAME, "Walkably cities table")
            layer = core.build_cities_layer(path)
        except core.WalkablyError as error:
            return self._say("Walkably", str(error), _CRITICAL)
        QgsProject.instance().addMapLayer(layer)
        if canvas_was_empty:
            self._zoom_to(layer)
        self._say("Walkably", "Added %d cities. %s" % (layer.featureCount(), core.CREDIT), _INFO, 20)

    def add_cells(self):
        canvas = self.iface.mapCanvas()
        try:
            path = self._fetch(core.GPKG_NAME, "Walkably sample (19.5 MB, downloaded once)")
            layers = core.build_cell_layers(path)
        except core.WalkablyError as error:
            return self._say("Walkably", str(error), _CRITICAL)
        # The sample has two cities, so "the visible area" means: the one nearer the middle of the map.
        nearer = core.nearer_cell_layer(layers, canvas.center(), canvas.mapSettings().destinationCrs())
        for layer in layers.values():
            QgsProject.instance().addMapLayer(layer)
        self._zoom_to(nearer)
        self._say(
            "Walkably",
            "Added the sample cells and zoomed to %s. Cells exist for Hamburg and Barcelona only; "
            "the full data is at %s. %s" % (nearer.customProperty("walkably/city"), core.DATA_PAGE, core.CREDIT),
            _WARNING,
            30,
        )

    def about(self):
        QMessageBox.information(
            self.iface.mainWindow(),
            "About the Walkably data",
            "Walkably walking scores for European cities.\n\n"
            "Licence: %s\n\nCredit line to show with any map or copy you share:\n%s\n\n"
            "Cells exist for Hamburg and Barcelona only. More at %s"
            % (core.LICENSE_NAME, core.CREDIT, core.DATA_PAGE),
        )

    # ---- helpers ---------------------------------------------------------------------------------------------
    def _fetch(self, name, label):
        progress = QProgressDialog(label, "Cancel", 0, 0, self.iface.mainWindow())
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)  # a file already on disk never shows a window
        try:
            return core.fetch_file(name, progress)
        finally:
            progress.reset()

    def _zoom_to(self, layer):
        canvas = self.iface.mapCanvas()
        transform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(), QgsProject.instance())
        canvas.setExtent(transform.transformBoundingBox(layer.extent()))
        canvas.refresh()

    def _say(self, title, text, level, seconds=0):
        self.iface.messageBar().pushMessage(title, text, level=level, duration=seconds)
