import serial
import json
import time
# Replace 'COM3' with your serial port (e.g., '/dev/ttyUSB0' on Linux)
ser = serial.Serial('COM9', 115200, timeout=1)

ser.write(b"activate sensor 1\n")
ser.write(b"activate sensor 2\n")




#
# # Replace 'COM3' with your serial port (e.g., '/dev/ttyUSB0' on Linux)
# ser = serial.Serial('COM9', 115200, timeout=1)
#
# # Send a command to the ESP
# ser.write(b'activate sensor 1\n')
# ser.write(b'deactivate sensor 2\n')
#
# while True:
#     line = ser.readline().decode('utf-8').strip()
#     if line:
#         print(line)