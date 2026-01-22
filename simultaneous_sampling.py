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
import signal
import csv
import serial
import re
from PySide6.QtCore import QThread, Signal, Qt, QObject
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

# ------------------------
# CONFIGURATION
# ------------------------
PORT = 'COM4'
BAUD_RATE = 115200
MASTER_CSV = "sync_cnc_tile_log.csv"
CNC_INTERVAL = 0.1 
MOVE_DISTANCE = "-5.0"
FEED_RATE = "100"
CALIBRATION_COMMAND = f"G1 Z{MOVE_DISTANCE} F{FEED_RATE}\n"
RETURN_COMMAND = f"G1 Z5.0 F100\n"

# Global Start Time for Sync
START_PERF = time.perf_counter()

# ------------------------
# CNC Control Thread
# ------------------------
'''class CNCThread(QThread):
    cncDataReady = Signal(float, float, str) # elapsed, rel_z, state

    def run(self):
        try:
            ser = serial.Serial(PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            ser.write(b"$X\n") # Unlock
            ser.write(b"G21\nG91\n") # Metric, Relative
            ser.flush()
            time.sleep(0.5)

            # Get Baseline
            ser.write(b'?')
            raw_start = ser.readline().decode('ascii')
            match_start = re.search(r'MPos:([-?0-9.,]+)', raw_start)
            z_offset = float(match_start.group(1).split(',')[2]) if match_start else 0.0

            print(f"🚀 CNC: Moving Z {MOVE_DISTANCE}mm...")
            ser.write(CALIBRATION_COMMAND.encode())
            
            moving = True
            returned = False

            while moving:
                ser.write(b'?')
                raw_line = ser.readline().decode('ascii').strip()
                if 'MPos:' in raw_line:
                    elapsed = time.perf_counter() - START_PERF
                    match = re.search(r'MPos:([-?0-9.,]+)', raw_line)
                    if match:
                        coords = match.group(1).split(',')
                        rel_z = round(float(coords[2]) - z_offset, 4)
                        state = raw_line.split('|')[0].strip('<')
                        
                        # Emit data to be logged
                        self.cncDataReady.emit(elapsed, rel_z, state)

                        if state == "Idle" and elapsed > 2.0:
                            if not returned:
                                ser.write(RETURN_COMMAND.encode())
                                returned = True
                            else:
                                moving = False
                time.sleep(CNC_INTERVAL)
            ser.close()
        except Exception as e:
            print(f"CNC Error: {e}")'''

class CNCThread(QThread):
    cncDataReady = Signal(float, float, str)

    def run(self):
        try:
            ser = serial.Serial(PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            
            # 1. Unlock and Force Relative Mode
            ser.write(b"$X\n") 
            ser.write(b"G21\n") # Millimeters
            ser.write(b"G91\n") # RELATIVE POSITIONING (Crucial)
            ser.flush()
            time.sleep(0.5)

            # 2. Get Starting Position
            ser.write(b'?')
            raw_start = ser.readline().decode('ascii')
            match_start = re.search(r'MPos:([-?0-9.,]+)', raw_start)
            z_start = float(match_start.group(1).split(',')[2]) if match_start else 0.0

            # 3. Send Move Command
            # We send G91 again just to be safe
            cmd = f"G91 G1 Z{MOVE_DISTANCE} F{FEED_RATE}\n"
            print(f"🚀 CNC Sending: {cmd.strip()}")
            ser.write(cmd.encode())
            ser.flush()
            
            moving = True
            returned = False
            start_time = time.perf_counter()

            while moving:
                ser.write(b'?')
                raw_line = ser.readline().decode('ascii').strip()
                
                if 'MPos:' in raw_line:
                    elapsed = time.perf_counter() - START_PERF
                    match = re.search(r'MPos:([-?0-9.,]+)', raw_line)
                    if match:
                        current_z_raw = float(match.group(1).split(',')[2])
                        rel_z = round(current_z_raw - z_start, 4)
                        state = raw_line.split('|')[0].strip('<')
                        
                        self.cncDataReady.emit(elapsed, rel_z, state)

                        # Check if move finished
                        # We look for "Idle" AND ensure some time has passed 
                        # to avoid catching the idle state BEFORE the move starts
                        if state == "Idle" and (time.perf_counter() - start_time) > 0.5:
                            if not returned:
                                print(f"✅ Reached {rel_z}mm. Returning...")
                                ser.write(b"G91 G1 Z5.0 F100\n")
                                ser.flush()
                                returned = True
                                start_time = time.perf_counter() # Reset timer for return leg
                            else:
                                print("🏁 Sequence complete.")
                                moving = False
                                
                time.sleep(CNC_INTERVAL)
            
            ser.close()
        except Exception as e:
            print(f"CNC Error: {e}")
# ------------------------
# Tile Acquisition Thread
# ------------------------
class DataReceiverThread(QThread):
    dataReady = Signal(object, float, float)

    def __init__(self, pipeName, bufIm, bufMetaData):
        super().__init__()
        self.bRunLoop = True
        self.bufIm = bufIm
        self.pipeName = pipeName
        try:
            self.pipe = win32file.CreateFile(
                r'\\.\pipe\\' + pipeName,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None
            )
        except:
            print("Could not connect to Tile Pipe!")

    def run(self):
        while self.bRunLoop:
            try:
                data = win32file.ReadFile(self.pipe, 2000000)
                header = struct.unpack('<HHHHHHHHHHHHHHHHQHH', data[1][:44])
                # Extracting ms from hardware header
                ms = header[15] 
                im = np.frombuffer(data[1][44:], dtype='uint16')
                
                elapsed = time.perf_counter() - START_PERF
                # Reshape: Stepscan tiles are usually 64x128 or similar
                # Using header width/height
                h, w = header[5], header[4]
                self.dataReady.emit(im.reshape((h, w)), elapsed, float(ms))
            except:
                break

# ------------------------
# Main Application Logic
# ------------------------
class MainApp:
    def __init__(self):
        self.app = QApplication([])
        
        # Initialize CSV (Rewrite mode)
        with open(MASTER_CSV, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Source", "Elapsed_Seconds", "Z_Pos", "Sensor_X", "Sensor_Y", "Value", "Status"])

        # Setup UI
        self.win = pg.GraphicsLayoutWidget()
        self.view = self.win.addViewBox()
        self.view.setAspectLocked(True)
        self.img = pg.ImageItem()
        self.view.addItem(self.img)
        self.textItem = pg.TextItem(anchor=(0, 0), color='w')
        self.view.addItem(self.textItem)
        self.win.show()

        # Shared Buffers
        self.bufIm = np.zeros(10**7, dtype='uint16')

        # Start Threads
        self.tileThread = DataReceiverThread("PipeOutput", self.bufIm, None)
        self.cncThread = CNCThread()

        # Connections
        self.tileThread.dataReady.connect(self.logTileData)
        self.cncThread.cncDataReady.connect(self.logCNCData)

        self.tileThread.start()
        self.cncThread.start()

        # Store last known Z for Tile logging
        self.current_z = 0.0

    def logCNCData(self, elapsed, rel_z, state):
        self.current_z = rel_z # Update Z for the tile to use
        with open(MASTER_CSV, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["CNC", f"{elapsed:.4f}", rel_z, "", "", "", state])

    def logTileData(self, image, elapsed, hw_ms):
        # Update Heatmap
        self.img.setImage(image.T, levels=[0, 14000])
        
        # Find activated sensors
        threshold = 50
        coords = np.argwhere(image > threshold)
        
        if len(coords) > 0:
            with open(MASTER_CSV, 'a', newline='') as f:
                writer = csv.writer(f)
                for y, x in coords:
                    writer.writerow(["TILE", f"{elapsed:.4f}", self.current_z, x, y, image[y, x], ""])
        
        self.textItem.setText(f"Elapsed: {elapsed:.2f}s\nZ: {self.current_z}\nMax: {np.max(image)}")

# ------------------------
# Helper to Start Processes
# ------------------------
def start_stepscan():
    for exe in ["ConsoleLog.exe", "ConsoleOptions.exe", "DAQ.exe"]:
        if not any(proc.info['name'] == exe for proc in psutil.process_iter(['name'])):
            path = rf"C:\Program Files\Stepscan Technologies Inc\Stepscan LIVE\lib\{exe}"
            if os.path.exists(path): os.startfile(path)

if __name__ == "__main__":
    start_stepscan()
    time.sleep(2)
    main = MainApp()
    main.app.exec()