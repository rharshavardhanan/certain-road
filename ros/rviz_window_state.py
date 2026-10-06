"""Generate the `QMainWindow State` blob in rviz/demo.rviz: a large camera panel on the left.

RViz keeps dock sizes only in this binary blob, so the layout is built in PyQt5 with the
same dock names RViz uses (each panel's objectName is its display name) and saved:

    /usr/bin/python3 ros/rviz_window_state.py 1840 1000 740 760
    # args: window width, window height, left dock width, camera panel height

Paste the printed hex after `QMainWindow State:` in rviz/demo.rviz. Uses the system
python3, which has PyQt5 as an rqt dependency.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

W, H, LEFT_W, CAM_H = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
app = QApplication(["x", "-platform", "offscreen"])
win = QMainWindow()
win.setCentralWidget(QWidget())
tb = win.addToolBar("Tools")
tb.setObjectName("Tools")
docks = {}
for name, area in [
    ("Camera + detections", Qt.LeftDockWidgetArea),
    ("Displays", Qt.LeftDockWidgetArea),
    ("Views", Qt.RightDockWidgetArea),
]:
    d = QDockWidget(name)
    d.setObjectName(name)
    d.setWidget(QWidget())
    win.addDockWidget(area, d)
    docks[name] = d
win.splitDockWidget(docks["Camera + detections"], docks["Displays"], Qt.Vertical)
docks["Views"].hide()
win.resize(W, H)
win.show()
app.processEvents()
win.resizeDocks([docks["Camera + detections"]], [LEFT_W], Qt.Horizontal)
win.resizeDocks([docks["Camera + detections"], docks["Displays"]], [CAM_H, H - CAM_H], Qt.Vertical)
app.processEvents()
print(bytes(win.saveState().toHex()).decode())
