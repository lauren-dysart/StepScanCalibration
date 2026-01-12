import os
filename = "pressure_grid.nc"
target_directory= r"c:\Users\htl\Desktop\StepScanTileCalibrationProject"
width = 24
length = 24
divisions=12
travel_z=0.125
press_z1=-0.1
press_z2=-0.025
feed_rate=30

spacing_x = width / (divisions-1)
spacing_y = length / (divisions-1)

os.makedirs(target_directory, exist_ok=True)
filepath=os.path.join (target_directory, filename)

with open(filepath, 'w') as f:
    #write header
    f.write("G20 (inches)\n")
    f.write("G90 (absolute)\n")
    f.write("M5 (Ensure spindle is stopped)\n") #safety measure
    f.write(f"G0 Z{travel_z}\n")

    #generate grid
    for i in range(divisions):
        x=i*spacing_x
        for j in range(divisions):
            y=j*spacing_y

            f.write(f"G0 X{x:.4f} Y{y:.4f}\n") #rapid to point
            f.write(f"G1 Z{press_z1} F{feed_rate}\n")   #motor moves, shouldn't spin
            f.write(f"G4 X0.5\n")
            f.write(f"G1 Z{press_z2} F{feed_rate}\n")   #motor moves, shouldn't spin
            f.write(f"G0 Z{travel_z}\n")
    f.write("G0 X0 Y0\n")
    f.write("M30\n")