def create_large_dat_file(filename, num_records, record_size_bytes):
    """
    Creates a large .dat file with a specified number of records and record size.
    Args:
        filename (str): The name of the .dat file to create.
        num_records (int): The total number of records to write.
        record_size_bytes (int): The size of each record in bytes.
    """
    bytes_written = 0
    sensor = 0x53656E736F72203A 
    row = 0x00
    column = 0x00
    data = 0x44617461
    
    with open(filename, 'wb') as f:  # Open in binary write mode
        # Write header (convert hex to bytes)
        header = 0x4144432D5052455353555245204D415053656E736F72203A0000000044617461

        # Calculate byte length needed (this hex needs 29 bytes)
        f.write(header.to_bytes(32, byteorder='big'))
        
        for i in range(num_records):
            # Generate a record (null bytes)
            record = b'\x00' * record_size_bytes  # Changed from b'00'
            f.write(record)
            
            # Write sensor (8 bytes)
            f.write(sensor.to_bytes(8, byteorder='big'))
            bytes_written += len(record) + 8
            
            # Handle row/column logic
            if row < 0x77:
                row = row + 0x01
                f.write(row.to_bytes(1, byteorder='big'))
                f.write(b'\x00')
                f.write(column.to_bytes(1, byteorder='big'))
                f.write(b'\x00')
            else:
                if column < 0x77:
                    row = 0x00
                    column = column + 1
                    f.write(row.to_bytes(1, byteorder='big'))
                    f.write(b'\x00')
                    f.write(column.to_bytes(1, byteorder='big'))
                    f.write(b'\x00')
                else:
                    f.write((0x00557845).to_bytes(4, byteorder='big'))
            f.write(data.to_bytes(4, byteorder='big'))
            # Optional: provide progress feedback
            if (i + 1) % (num_records // 10) == 0 or (i + 1) == num_records:
                print(f"Progress: {((i + 1) / num_records) * 100:.2f}% ({bytes_written / (1024*1024):.2f} MB written)")
    
    print(f"Successfully created '{filename}' with {num_records} records.")

# Example usage:
file_name = "empty_calibration.dat"
number_of_records = 14400  # 14400 records
size_per_record = 3300     # 3300 bytes per record

create_large_dat_file(file_name, number_of_records, size_per_record)
