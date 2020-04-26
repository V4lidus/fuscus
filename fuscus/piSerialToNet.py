#!/usr/bin/env python3

import sys
import socket
import serial
import serial.threaded
import time
import threading
import pty
import os


class SerialToNet(serial.threaded.Protocol):
    """serial->socket"""

    def __init__(self):
        self.socket = None

    def __call__(self):
        return self

    def data_received(self, data):
        if self.socket is not None:
            self.socket.sendall(data)



class PiSerialToNet(threading.Thread):

    def __init__(self, networkPort, serialPort):
        threading.Thread.__init__(self)

        self.networkPort = networkPort
        self.serialPort = serialPort

        #todo: allow these to be passed in
        # connect to serial port
        self.ser = serial.serial_for_url(self.serialPort, do_not_open=True)
        self.ser.baudrate = 9600
        self.ser.bytesize = 8
        self.ser.parity = 'N'
        self.ser.stopbits = 1
        self.ser.rtscts = False
        self.ser.xonxoff = False

        self.running = False


    def run(self):
        try:
            try:
                self.ser.open()
            except serial.SerialException as e:
                sys.stderr.write('Could not open serial port {}: {}\n'.format(self.ser.name, e))
                sys.exit(1)

            ser_to_net = SerialToNet()
            serial_worker = serial.threaded.ReaderThread(self.ser, ser_to_net)
            serial_worker.start()

            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('', self.networkPort))
            srv.listen(1)

            self.running = True;

            while (self.running):
                sys.stderr.write('Waiting for connection on {}...\n'.format(self.networkPort))
                client_socket, addr = srv.accept()
                sys.stderr.write('Connected by {}\n'.format(addr))
                # More quickly detect bad clients who quit without closing the
                # connection: After 1 second of idle, start sending TCP keep-alive
                # packets every 1 second. If 3 consecutive keep-alive packets
                # fail, assume the client is gone and close the connection.
                try:
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except AttributeError:
                    pass # XXX not available on windows
                client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    ser_to_net.socket = client_socket
                    # enter network <-> serial loop

                    while (self.running):
                        try:
                            data = client_socket.recv(1024)
                            if not data:
                                break
                            self.ser.write(data)                 # get a bunch of bytes and send them
                        except socket.error as msg:
                            sys.stderr.write('ERROR: {}\n'.format(msg))
                            # probably got disconnected
                            break

                except KeyboardInterrupt:
                    self.running = False
                    raise
                except socket.error as msg:
                    sys.stderr.write('ERROR: {}\n'.format(msg))
                finally:
                    ser_to_net.socket = None
                    sys.stderr.write('Disconnected\n')
                    client_socket.close()

        except KeyboardInterrupt:
            pass

        sys.stderr.write('\n--- exit ---\n')
        serial_worker.stop()



    def stop(self):
        self.running = False


if __name__ == "__main__":
    # test code

    master,slave = pty.openpty() #open the pseudoterminal
    s_name = os.ttyname(slave) #translate the slave fd to a filename

    thread = PiSerialToNet(25518, s_name)
    thread.start()

    #open a pySerial connection to the slave
    ser = serial.serial_for_url(s_name, 2400, timeout=1)
    ser.baudrate = 9600
    ser.bytesize = 8
    ser.parity = 'N'
    ser.stopbits = 1
    ser.rtscts = False
    ser.xonxoff = False
