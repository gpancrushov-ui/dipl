#!/usr/bin/env python3
"""
UDP File Manager - Server Component
Provides file system access over UDP protocol
"""

import socket
import os
import struct
import sys

# Protocol constants
CMD_LIST_DIR = 1
CMD_GET_FILE = 2
CMD_PUT_FILE = 3
CMD_DELETE = 4
CMD_MKDIR = 5
CMD_RENAME = 6
CMD_GET_DRIVES = 7
CMD_CHANGE_DIR = 8
RESPONSE_OK = 100
RESPONSE_ERROR = 101
RESPONSE_DATA = 102


class UDPServer:
    """UDP server for file operations"""
    
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.current_dir = os.getcwd()
        
    def start(self):
        """Start the server"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(1.0)
        self.running = True
        
        print(f"UDP File Server started on {self.host}:{self.port}")
        print(f"Serving files from: {self.current_dir}")
        print("Press Ctrl+C to stop")
        
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                self.handle_request(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Server error: {e}")
                
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.sock:
            self.sock.close()
            
    def handle_request(self, data, addr):
        """Handle incoming request"""
        if len(data) < 5:
            return
            
        cmd = data[0]
        data_len = struct.unpack('>I', data[1:5])[0]
        payload = data[5:5+data_len] if data_len > 0 else b''
        
        try:
            if cmd == CMD_LIST_DIR:
                self.handle_list_dir(payload, addr)
            elif cmd == CMD_GET_DRIVES:
                self.handle_get_drives(addr)
            elif cmd == CMD_CHANGE_DIR:
                self.handle_change_dir(payload, addr)
            elif cmd == CMD_GET_FILE:
                self.handle_get_file(payload, addr)
            elif cmd == CMD_PUT_FILE:
                self.handle_put_file(payload, addr)
            elif cmd == CMD_DELETE:
                self.handle_delete(payload, addr)
            elif cmd == CMD_MKDIR:
                self.handle_mkdir(payload, addr)
            elif cmd == CMD_RENAME:
                self.handle_rename(payload, addr)
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def send_response(self, addr, status, data=b''):
        """Send response to client"""
        header = struct.pack('>BI', status, len(data))
        packet = header + data
        self.sock.sendto(packet, addr)
        
    def handle_list_dir(self, payload, addr):
        """Handle list directory request"""
        path = payload.decode('utf-8')
        if path:
            target_dir = path
        else:
            target_dir = self.current_dir
            
        try:
            entries = []
            for item in os.listdir(target_dir):
                full_path = os.path.join(target_dir, item)
                is_dir = os.path.isdir(full_path)
                size = os.path.getsize(full_path) if not is_dir else 0
                entries.append(f"{item}|{'dir' if is_dir else 'file'}|{size}")
                
            self.send_response(addr, RESPONSE_DATA, '\n'.join(entries).encode())
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_get_drives(self, addr):
        """Handle get drives request"""
        try:
            if os.name == 'nt':  # Windows
                import string
                drives = []
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if os.path.exists(drive):
                        drives.append(drive)
                self.send_response(addr, RESPONSE_DATA, '\n'.join(drives).encode())
            else:  # Linux/Mac
                drives = ['/']
                for item in os.listdir('/'):
                    full_path = os.path.join('/', item)
                    if os.path.isdir(full_path) and not item.startswith('.'):
                        drives.append(full_path)
                self.send_response(addr, RESPONSE_DATA, '\n'.join(drives).encode())
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_change_dir(self, payload, addr):
        """Handle change directory request"""
        path = payload.decode('utf-8')
        try:
            if os.path.isdir(path):
                self.current_dir = path
                self.send_response(addr, RESPONSE_OK)
            else:
                self.send_response(addr, RESPONSE_ERROR, b"Directory not found")
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_get_file(self, payload, addr):
        """Handle get file request"""
        path = payload.decode('utf-8')
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.send_response(addr, RESPONSE_DATA, data)
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_put_file(self, payload, addr):
        """Handle put file request"""
        try:
            null_idx = payload.index(b'\x00'[0])
            path = payload[:null_idx].decode('utf-8')
            file_data = payload[null_idx+1:]
            
            with open(path, 'wb') as f:
                f.write(file_data)
            self.send_response(addr, RESPONSE_OK)
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_delete(self, payload, addr):
        """Handle delete request"""
        path = payload.decode('utf-8')
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                os.rmdir(path)
            self.send_response(addr, RESPONSE_OK)
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_mkdir(self, payload, addr):
        """Handle mkdir request"""
        path = payload.decode('utf-8')
        try:
            os.makedirs(path, exist_ok=True)
            self.send_response(addr, RESPONSE_OK)
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())
            
    def handle_rename(self, payload, addr):
        """Handle rename request"""
        parts = payload.decode('utf-8').split('\x00')
        if len(parts) != 2:
            self.send_response(addr, RESPONSE_ERROR, b"Invalid rename format")
            return
            
        old_path, new_path = parts
        try:
            os.rename(old_path, new_path)
            self.send_response(addr, RESPONSE_OK)
        except Exception as e:
            self.send_response(addr, RESPONSE_ERROR, str(e).encode())


def main():
    """Main entry point"""
    host = '0.0.0.0'
    port = 5000
    
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        host = sys.argv[2]
    
    server = UDPServer(host, port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.stop()


if __name__ == '__main__':
    main()
