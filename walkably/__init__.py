def classFactory(iface):
    from .walkably_plugin import WalkablyPlugin

    return WalkablyPlugin(iface)
