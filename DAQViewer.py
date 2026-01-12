
import os
import time
import numpy as np
import struct
import datetime
import matplotlib.pyplot as plt
import pyqtgraph as pg
import win32file
import pywintypes
import psutil
import signal  # for graceful Ctrl+C handling

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor


# ------------------------
# Process helpers
# ------------------------

def is_process_running(exe_name):
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == exe_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def start_external_processes():
    """Start required external processes if not already running."""
    if not is_process_running("ConsoleLog.exe"):
        os.startfile(r"C:\Program Files\Stepscan Technologies Inc\Stepscan LIVE\lib\ConsoleLog.exe")
    if not is_process_running("ConsoleOptions.exe"):
        os.startfile(r"C:\Program Files\Stepscan Technologies Inc\Stepscan LIVE\lib\ConsoleOptions.exe")
    if not is_process_running("DAQ.exe"):
        os.startfile(r"C:\Program Files\Stepscan Technologies Inc\Stepscan LIVE\lib\DAQ.exe")


def stop_external_processes(names=('ConsoleLog.exe', 'ConsoleOptions.exe', 'DAQ.exe'), timeout=5.0):
    """
    Attempt to terminate external processes gracefully, then force kill if needed.
    Safe to call multiple times.
    """
    targets = []
    for proc in psutil.process_iter(['name', 'pid']):
        name = (proc.info.get('name') or '').lower()
        try:
            for n in names:
                if name == n.lower():
                    targets.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not targets:
        return

    for p in targets:
        try:
            print(f"Terminating {p.pid} ({p.name()})...")
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"  terminate skipped: {e}")

    gone, alive = psutil.wait_procs(targets, timeout=timeout)

    for p in alive:
        try:
            print(f"Forcing kill {p.pid} ({p.name()})...")
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"  kill skipped: {e}")


# ------------------------
# Acquisition thread
# ------------------------

class DataReceiverThread(QThread):
    dataReady = Signal(object)

    def __init__(self, pipeName, bufIm, bufMetaData, parent=None):
        super().__init__(parent)
        self.bRunLoop = False
        self.bLoopStopped = True
        self.bDisable = False
        self.bufMD = bufMetaData
        self.bufIm = bufIm
        self.pipeName = pipeName
        self.frameID = 0
        self.pipe = win32file.CreateFile(
            r'\\.\pipe\\' + pipeName,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None,
            win32file.OPEN_EXISTING,
            win32file.FILE_ATTRIBUTE_NORMAL, None
        )

    def readImageFromNamedPipe(self):
        data = win32file.ReadFile(self.pipe, 2000000)
        # Use proper '<' for little-endian
        header = struct.unpack('<HHHHHHHHHHHHHHHHQHH', data[1][:44])
        (_, _, _, frameID, width, height, _, _, year, month,
         _, day, hour, minute, second, ms, _, _, _) = header
        im = np.frombuffer(data[1][44:], dtype='uint16')

        # NOTE: If 'ms' is milliseconds, you likely want ms*1000 in microseconds.
        dt = datetime.datetime(year, month, day, hour, minute, second, ms)
        timestamp = time.mktime(dt.timetuple())
        return [timestamp, frameID, im, height, width]

    def cleanUp(self):
        try:
            self.pipe.close()
        except Exception:
            pass

    def runSetup(self):
        self.bufImSize = np.size(self.bufIm)
        self.fcount = 0

    def runLoop(self):
        try:
            timestamp, frameID, im, height, width = self.readImageFromNamedPipe()
        except pywintypes.error:
            print("Data receiver pipe closed.")
            self.bRunLoop = False
            return
        if frameID == -1:
            return

        # Circular buffers
        self.bufIm[self.fcount * height * width:(self.fcount + 1) * height * width] = im
        self.bufMD[self.fcount * 5:(self.fcount + 1) * 5] = [-1, frameID, height, width, timestamp]
        self.bufMD[self.fcount * 5] = 1  # mark written

        self.fcount += 1
        if (self.fcount + 1) * height * width > self.bufImSize:
            self.fcount = 0

        # Emit image for display
        self.dataReady.emit(im.reshape((height, width)))

    def run(self):
        if self.bDisable:
            return
        self.bRunLoop = True
        self.runSetup()
        while self.bRunLoop:
            self.runLoop()
        self.bLoopStopped = True

    def finish(self):
        """Request stop, wait for loop termination, and cleanup."""
        self.bRunLoop = False
        while not self.bLoopStopped:
            time.sleep(0.01)
        self.cleanUp()


# ------------------------
# Main app setup
# ------------------------

# Start external processes
start_external_processes()
time.sleep(3)

# Buffers
bufImSize = 1000 * 1000 * 1000
bufIm = np.zeros(bufImSize, dtype='uint16')
bufMetaData = np.full(int(bufImSize / 1_000_000 * 5 * 100), -1, dtype=float)

# Thread
dataReceiver = DataReceiverThread("PipeOutput", bufIm, bufMetaData)

# UI
app = QApplication([])
win = pg.GraphicsLayoutWidget()
win.showMaximized()
view = win.addViewBox()
view.setAspectLocked(True)
view.invertY(True)
# view.setBackgroundColor(QColor(220, 220, 220))
view.setBackgroundColor(QColor(0, 0, 0))

img = pg.ImageItem(border='w')
jetmap = (plt.get_cmap('jet')(np.linspace(0, 1, 256)) * 255).astype(np.uint8)
jetmap[jetmap > 255] = 255

# Make data value 0 => black
jetmap[0, :3] = 0     # R,G,B = 0
jetmap[0, 3] = 255    # Alpha = 255 (opaque)

img.setLookupTable(jetmap)
view.addItem(img)
view.enableAutoRange()
textItem = pg.TextItem('')
view.addItem(textItem)

def updateImage(image):
    img.setImage(image.T, levels=[0, 14000])

dataReceiver.dataReady.connect(updateImage, Qt.QueuedConnection)
dataReceiver.start()


# ------------------------
# Graceful shutdown wiring
# ------------------------

def shutdown_all():
    """
    Close the data receiver and stop all external processes.
    Safe to call multiple times.
    """
    print("Shutting down: stopping DataReceiverThread...")
    try:
        dataReceiver.finish()
    except Exception as e:
        print(f"DataReceiverThread finish error: {e}")

    print("Shutting down: stopping external processes...")
    try:
        stop_external_processes()
    except Exception as e:
        print(f"Error stopping external processes: {e}")

    print("Shutdown complete.")

# Hook window close
def _win_close_event(ev):
    try:
        shutdown_all()
    finally:
        ev.accept()

win.closeEvent = _win_close_event

# Ensure cleanup on Qt aboutToQuit
app.aboutToQuit.connect(shutdown_all)

# Handle Ctrl+C
def _sigint_handler(*args):
    print("SIGINT received: quitting application...")
    app.quit()
signal.signal(signal.SIGINT, _sigint_handler)


# ------------------------
# Run
# ------------------------
if __name__ == '__main__':
    import sys
    try:
        app.exec()
    finally:
        # Final guard in case quitting bypassed signals
        shutdown_all()
