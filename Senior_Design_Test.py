
# # A script to convert the .h5 pressure data files captured by Stepscan Live
# # to numpy format.
# #
# # To save disk space, this script uses .npz format (i.e., numpy "zipped"), which
# # compresses the saved numpy array before saving to disk.
# #
# # For convenience, a `load_npz()` function is also provided to illustrate how to
# # load the converted arrays for further analysis.
# #
# # Usage: python convert_h5_to_npz.py <path_to_h5_file>

#////////////reading from one file
# import numpy as np
# import h5py
# import pathlib
# import sys

# filepath = '/Users/laurendysart/Desktop/Senior_Design/tests_oct23/4c_t1_40.h5'

# def convert_h5_to_npz(filepath):
#     output_filepath = pathlib.Path(filepath).with_suffix('.npz')

#     print(f'\t{filepath} => {output_filepath}')

#     file = h5py.File(filepath, 'r')
#     data = file['I'][:,22:]
#     data = data.reshape((data.shape[0],720,240))
#     np.savez_compressed(output_filepath, arr_0=data)
        

# def load_npz(filepath):
#     npz_file = np.load(filepath)
#     pressure_data = npz_file['arr_0']

#     print(f'{filepath} ({pressure_data.shape})')
#     #print(pressure_data)

#     return pressure_data

# if __name__ == '__main__':
#     #filepath = pathlib.Path(sys.argv[1])
#     convert_h5_to_npz(filepath)

# data = load_npz("/Users/laurendysart/Desktop/Senior_Design/tests_oct23/4c_t1_40.npz")
# #print(data)
# print(f"Shape: {data.shape}")
# print(f"Min: {data.min()}, Max: {data.max()}, Mean: {data.mean():.2f}")

#///////////reading from all files
import numpy as np
import h5py
import pathlib

# Folder containing your .h5 files
input_folder = pathlib.Path('/Users/laurendysart/Desktop/Senior_Design/tests_oct23')


def convert_h5_to_npz(filepath):
    output_filepath = pathlib.Path(filepath).with_suffix('.npz')

    print(f'\t{filepath} => {output_filepath}')

    file = h5py.File(filepath, 'r')
    data = file['I'][:,22:]
    data = data.reshape((data.shape[0],720,240))
    np.savez_compressed(output_filepath, arr_0=data)

    return output_filepath
def load_npz(filepath):
    """Load an .npz file and return the data array."""
    npz_file = np.load(filepath)
    return npz_file['arr_0']

# Main script
if __name__ == '__main__':
    h5_files = list(input_folder.glob('*.h5'))

    print(f'Found {len(h5_files)} .h5 file(s) in {input_folder}\n')

    for h5_file in h5_files:
        # Convert each file
        npz_path = convert_h5_to_npz(h5_file)
        if npz_path is None:
            continue

        # Load the converted data
        data = load_npz(npz_path)

        # Compute and print the max value
        max_val = data.max()
        print(f' {h5_file.name}: max value = {max_val:.3f}\n')

    print("Processing complete.")
