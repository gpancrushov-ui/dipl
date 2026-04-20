#!/usr/bin/env python3
"""
UDP File Manager - Total Commander Style GUI
Left panel: Local file system
Right panel: Remote server via UDP
Features:
- Dual panel interface
- Drive dropdown lists for both panels
- UDP connection scanner
- File operations (copy, delete, mkdir, rename)
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import socket
import os
import json
import threading
import struct
import time
from pathlib import Path
import hashlib

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

class UDPClient:
    """UDP client for remote file operations"""
    
    def __init__(self, host='127.0.0.1', port=5000, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        
    def connect(self):
        """Establish UDP connection"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        
    def disconnect(self):
        """Close UDP connection"""
        if self.sock:
            self.sock.close()
            self.sock = None
            
    def send_command(self, cmd, data=b''):
        """Send command to server"""
        if not self.sock:
            self.connect()
        
        # Pack: cmd (1 byte) + data_len (4 bytes) + data
        header = struct.pack('>BI', cmd, len(data))
        packet = header + data
        
        self.sock.sendto(packet, (self.host, self.port))
        
    def receive_response(self):
        """Receive response from server"""
        if not self.sock:
            return None, None
            
        try:
            data, _ = self.sock.recvfrom(65535)
            if len(data) < 5:
                return None, None
                
            status = data[0]
            data_len = struct.unpack('>I', data[1:5])[0]
            payload = data[5:5+data_len] if data_len > 0 else b''
            
            return status, payload
        except socket.timeout:
            return None, None
        except Exception as e:
            return None, str(e).encode()
            
    def list_dir(self, path):
        """List directory contents"""
        self.send_command(CMD_LIST_DIR, path.encode('utf-8'))
        status, data = self.receive_response()
        if status == RESPONSE_DATA:
            return data.decode('utf-8').split('\n')
        return None
        
    def get_drives(self):
        """Get available drives"""
        self.send_command(CMD_GET_DRIVES)
        status, data = self.receive_response()
        if status == RESPONSE_DATA:
            return data.decode('utf-8').split('\n')
        return None
        
    def change_dir(self, path):
        """Change directory on server"""
        self.send_command(CMD_CHANGE_DIR, path.encode('utf-8'))
        status, _ = self.receive_response()
        return status == RESPONSE_OK
        
    def download_file(self, remote_path, local_path):
        """Download file from server"""
        self.send_command(CMD_GET_FILE, remote_path.encode('utf-8'))
        status, data = self.receive_response()
        if status == RESPONSE_DATA:
            with open(local_path, 'wb') as f:
                f.write(data)
            return True
        return False
        
    def upload_file(self, local_path, remote_path):
        """Upload file to server"""
        with open(local_path, 'rb') as f:
            data = f.read()
        payload = remote_path.encode('utf-8') + b'\x00' + data
        self.send_command(CMD_PUT_FILE, payload)
        status, _ = self.receive_response()
        return status == RESPONSE_OK
        
    def delete(self, path):
        """Delete file or directory on server"""
        self.send_command(CMD_DELETE, path.encode('utf-8'))
        status, _ = self.receive_response()
        return status == RESPONSE_OK
        
    def mkdir(self, path):
        """Create directory on server"""
        self.send_command(CMD_MKDIR, path.encode('utf-8'))
        status, _ = self.receive_response()
        return status == RESPONSE_OK
        
    def rename(self, old_path, new_path):
        """Rename file or directory on server"""
        payload = f"{old_path}\x00{new_path}".encode('utf-8')
        self.send_command(CMD_RENAME, payload)
        status, _ = self.receive_response()
        return status == RESPONSE_OK


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


class UDPScanner:
    """Scanner for finding UDP servers"""
    
    @staticmethod
    def scan_network(network_prefix='192.168.1', port=5000, timeout=1.0):
        """Scan network for UDP servers"""
        found_servers = []
        
        def scan_ip(ip):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(timeout)
                
                # Send a test packet (GET_DRIVES command)
                header = struct.pack('>BI', CMD_GET_DRIVES, 0)
                sock.sendto(header, (ip, port))
                
                # Wait for response
                try:
                    data, _ = sock.recvfrom(1024)
                    if len(data) >= 1 and data[0] in [RESPONSE_OK, RESPONSE_DATA, RESPONSE_ERROR]:
                        found_servers.append(ip)
                except socket.timeout:
                    pass
                finally:
                    sock.close()
            except:
                pass
                
        # Scan common IPs
        ips_to_scan = [
            '127.0.0.1',
            f'{network_prefix}.1',
            f'{network_prefix}.10',
            f'{network_prefix}.100',
            f'{network_prefix}.254',
        ]
        
        threads = []
        for ip in ips_to_scan:
            t = threading.Thread(target=scan_ip, args=(ip,))
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join()
            
        return found_servers


class FileManagerApp:
    """Main application class"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("UDP File Manager - Total Commander Style")
        self.root.geometry("1200x700")
        
        # State
        self.local_path = os.getcwd()
        self.remote_path = '/'
        self.remote_server = None
        self.remote_client = UDPClient()
        self.active_panel = 'local'  # 'local' or 'remote'
        self.sort_mode = 'name'  # 'name', 'size', 'date', 'type'
        self.sort_reverse = False
        
        # Setup UI
        self.setup_menu()
        self.setup_main_area()
        self.setup_status_bar()
        
        # Load initial directories
        self.refresh_local_panel()
        
    def setup_menu(self):
        """Setup menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Connect to Server...", command=self.connect_server)
        file_menu.add_command(label="Disconnect", command=self.disconnect_server)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Network menu
        net_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Network", menu=net_menu)
        net_menu.add_command(label="Scan for Servers...", command=self.scan_servers)
        net_menu.add_command(label="Manual Connect...", command=self.manual_connect)
        
        # View menu - Sorting
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        sort_submenu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Sort by", menu=sort_submenu)
        sort_submenu.add_radiobutton(label="Name", command=lambda: self.set_sort_mode('name'))
        sort_submenu.add_radiobutton(label="Size", command=lambda: self.set_sort_mode('size'))
        sort_submenu.add_radiobutton(label="Date", command=lambda: self.set_sort_mode('date'))
        sort_submenu.add_radiobutton(label="Type", command=lambda: self.set_sort_mode('type'))
        view_menu.add_separator()
        view_menu.add_command(label="Toggle Sort Order", command=self.toggle_sort_order)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="About", command=self.show_about)
        
    def setup_action_buttons(self):
        """Setup action buttons at the bottom"""
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Copy from remote to local button
        tk.Button(btn_frame, text="⬇ Download Selected", command=self.download_selected, bg='#90EE90').pack(side=tk.LEFT, padx=5)
        
        # Copy from local to remote button
        tk.Button(btn_frame, text="⬆ Upload Selected", command=self.upload_selected, bg='#87CEEB').pack(side=tk.LEFT, padx=5)
        
        # Scan button
        tk.Button(btn_frame, text="🔍 Scan UDP Servers", command=self.scan_servers, bg='#FFD700').pack(side=tk.RIGHT, padx=5)
        
        # Connection status label
        self.connection_label = tk.Label(btn_frame, text="Disconnected", fg='red')
        self.connection_label.pack(side=tk.RIGHT, padx=10)
        
    def download_selected(self):
        """Download selected file from remote to local"""
        selection = self.remote_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "No file selected")
            return
            
        item = selection[0]
        name = self.remote_tree.item(item, 'text')
        ftype = self.remote_tree.item(item, 'values')[1]
        
        if ftype == 'DIR':
            messagebox.showwarning("Warning", "Directory download not supported yet")
            return
            
        src_path = os.path.join(self.remote_path, name)
        dst_path = os.path.join(self.local_path, name)
        
        if self.remote_client.download_file(src_path, dst_path):
            self.refresh_local_panel()
            self.status_bar.config(text=f"Downloaded {name} from remote")
        else:
            messagebox.showerror("Error", "Failed to download file")
            
    def upload_selected(self):
        """Upload selected file from local to remote"""
        selection = self.local_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "No file selected")
            return
            
        item = selection[0]
        name = self.local_tree.item(item, 'text')
        ftype = self.local_tree.item(item, 'values')[1]
        
        if ftype == 'DIR':
            messagebox.showwarning("Warning", "Directory upload not supported yet")
            return
            
        src_path = os.path.join(self.local_path, name)
        dst_path = os.path.join(self.remote_path, name)
        
        if self.remote_client.upload_file(src_path, dst_path):
            self.refresh_remote_panel()
            self.status_bar.config(text=f"Uploaded {name} to remote")
        else:
            messagebox.showerror("Error", "Failed to upload file")

    def set_sort_mode(self, mode):
        """Set sort mode"""
        self.sort_mode = mode
        self.refresh_local_panel()
        if self.remote_client.sock:
            self.refresh_remote_panel()
            
    def toggle_sort_order(self):
        """Toggle sort order"""
        self.sort_reverse = not self.sort_reverse
        self.refresh_local_panel()
        if self.remote_client.sock:
            self.refresh_remote_panel()
            
    def toggle_sort(self, column):
        """Toggle sort for local panel"""
        if self.sort_mode == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_mode = column
            self.sort_reverse = False
        self.refresh_local_panel()
        
    def toggle_sort_remote(self, column):
        """Toggle sort for remote panel"""
        if self.sort_mode == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_mode = column
            self.sort_reverse = False
        if self.remote_client.sock:
            self.refresh_remote_panel()
            
    def sort_entries(self, entries, is_local=True):
        """Sort entries based on current sort mode"""
        def get_sort_key(entry):
            if is_local:
                name = entry
                full_path = os.path.join(self.local_path, name)
                is_dir = os.path.isdir(full_path)
                if self.sort_mode == 'size':
                    return (0 if is_dir else os.path.getsize(full_path), name)
                elif self.sort_mode == 'date':
                    return (0 if is_dir else os.path.getmtime(full_path), name)
                elif self.sort_mode == 'type':
                    ext = os.path.splitext(name)[1].lower()
                    return (0 if is_dir else ext, name)
                else:  # name
                    return (0 if is_dir else 1, name.lower())
            else:
                # Remote entry format: name|type|size
                parts = entry.split('|')
                name = parts[0]
                ftype = parts[1] if len(parts) > 1 else 'file'
                size = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                is_dir = ftype == 'dir'
                
                if self.sort_mode == 'size':
                    return (0 if is_dir else size, name)
                elif self.sort_mode == 'date':
                    # Date not available from server, use name as fallback
                    return (0 if is_dir else 0, name)
                elif self.sort_mode == 'type':
                    ext = os.path.splitext(name)[1].lower()
                    return (0 if is_dir else ext, name)
                else:  # name
                    return (0 if is_dir else 1, name.lower())
        
        return sorted(entries, key=get_sort_key, reverse=self.sort_reverse)
        
    def setup_main_area(self):
        """Setup main area with two panels"""
        # Main container
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Local panel (left)
        local_frame = tk.LabelFrame(main_frame, text="Local Files", padx=5, pady=5)
        local_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Local drive selector inside local panel
        local_drive_frame = tk.Frame(local_frame)
        local_drive_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(local_drive_frame, text="Drive:").pack(side=tk.LEFT, padx=(0, 5))
        self.local_drive_var = tk.StringVar()
        self.local_drive_combo = ttk.Combobox(local_drive_frame, textvariable=self.local_drive_var, width=20)
        self.local_drive_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.local_drive_combo.bind('<<ComboboxSelected>>', self.on_local_drive_change)
        self.local_drive_combo.bind('<Return>', self.on_local_drive_manual)
        tk.Button(local_drive_frame, text="⟳", width=3, command=self.refresh_local_panel).pack(side=tk.LEFT, padx=(5, 0))
        
        # Local file tree
        self.local_tree = ttk.Treeview(local_frame, columns=('Size', 'Type', 'Date'), selectmode='browse')
        self.local_tree.heading('#0', text='Name', command=lambda: self.toggle_sort('name'))
        self.local_tree.heading('Size', text='Size', command=lambda: self.toggle_sort('size'))
        self.local_tree.heading('Type', text='Type', command=lambda: self.toggle_sort('type'))
        self.local_tree.heading('Date', text='Date', command=lambda: self.toggle_sort('date'))
        self.local_tree.column('#0', width=200)
        self.local_tree.column('Size', width=100)
        self.local_tree.column('Type', width=80)
        self.local_tree.column('Date', width=150)
        
        local_scroll = ttk.Scrollbar(local_frame, orient=tk.VERTICAL, command=self.local_tree.yview)
        self.local_tree.configure(yscrollcommand=local_scroll.set)
        
        self.local_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        local_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.local_tree.bind('<Double-1>', self.on_local_double_click)
        self.local_tree.bind('<Return>', self.on_local_enter)
        self.local_tree.bind('<BackSpace>', lambda e: self.go_up_local())
        
        # Remote panel (right)
        remote_frame = tk.LabelFrame(main_frame, text="Remote Files (UDP)", padx=5, pady=5)
        remote_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Remote drive selector inside remote panel
        remote_drive_frame = tk.Frame(remote_frame)
        remote_drive_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(remote_drive_frame, text="Server:").pack(side=tk.LEFT, padx=(0, 5))
        self.remote_drive_var = tk.StringVar()
        self.remote_drive_combo = ttk.Combobox(remote_drive_frame, textvariable=self.remote_drive_var, width=20)
        self.remote_drive_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.remote_drive_combo.bind('<<ComboboxSelected>>', self.on_remote_drive_change)
        self.remote_drive_combo.bind('<Return>', self.on_remote_drive_manual)
        tk.Button(remote_drive_frame, text="⟳", width=3, command=self.refresh_remote_panel).pack(side=tk.LEFT, padx=(5, 0))
        
        # Remote file tree
        self.remote_tree = ttk.Treeview(remote_frame, columns=('Size', 'Type', 'Date'), selectmode='browse')
        self.remote_tree.heading('#0', text='Name', command=lambda: self.toggle_sort_remote('name'))
        self.remote_tree.heading('Size', text='Size', command=lambda: self.toggle_sort_remote('size'))
        self.remote_tree.heading('Type', text='Type', command=lambda: self.toggle_sort_remote('type'))
        self.remote_tree.heading('Date', text='Date', command=lambda: self.toggle_sort_remote('date'))
        self.remote_tree.column('#0', width=200)
        self.remote_tree.column('Size', width=100)
        self.remote_tree.column('Type', width=80)
        self.remote_tree.column('Date', width=150)
        
        remote_scroll = ttk.Scrollbar(remote_frame, orient=tk.VERTICAL, command=self.remote_tree.yview)
        self.remote_tree.configure(yscrollcommand=remote_scroll.set)
        
        self.remote_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        remote_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.remote_tree.bind('<Double-1>', self.on_remote_double_click)
        self.remote_tree.bind('<Return>', self.on_remote_enter)
        self.remote_tree.bind('<BackSpace>', lambda e: self.go_up_remote())
        
        # Bind Tab to switch panels
        self.root.bind('<Tab>', self.switch_panel)
        
        # Bind function keys
        self.root.bind('<F5>', lambda e: self.copy_file())
        self.root.bind('<F7>', lambda e: self.create_directory())
        self.root.bind('<F8>', lambda e: self.delete_file())
        self.root.bind('<F2>', lambda e: self.rename_file())
        self.root.bind('<Control-R>', lambda e: self.refresh_all())
        self.root.bind('<Control-r>', lambda e: self.refresh_all())
        
        # Action buttons frame
        self.setup_action_buttons()
        
    def setup_status_bar(self):
        """Setup status bar"""
        self.status_bar = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def populate_local_drives(self):
        """Populate local drive dropdown"""
        if os.name == 'nt':  # Windows
            import string
            drives = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append(drive)
            self.local_drive_combo['values'] = drives
            if drives:
                self.local_drive_var.set(drives[0])
        else:  # Linux/Mac
            drives = ['/']
            for item in os.listdir('/'):
                full_path = os.path.join('/', item)
                if os.path.isdir(full_path) and not item.startswith('.'):
                    drives.append(full_path)
            self.local_drive_combo['values'] = drives
            self.local_drive_var.set('/')
            
    def populate_remote_drives(self):
        """Populate remote drive dropdown"""
        if self.remote_client.sock:
            try:
                drives = self.remote_client.get_drives()
                if drives:
                    self.remote_drive_combo['values'] = drives
                    if drives:
                        self.remote_drive_var.set(drives[0])
            except:
                pass
                
    def refresh_local_panel(self):
        """Refresh local file panel"""
        for item in self.local_tree.get_children():
            self.local_tree.delete(item)
            
        try:
            entries = os.listdir(self.local_path)
            # Sort entries
            sorted_entries = self.sort_entries(entries, is_local=True)
            
            for entry in sorted_entries:
                full_path = os.path.join(self.local_path, entry)
                is_dir = os.path.isdir(full_path)
                
                if is_dir:
                    size = ''
                    ftype = 'DIR'
                    date_str = ''
                else:
                    try:
                        size = str(os.path.getsize(full_path))
                    except:
                        size = '?'
                    ftype = 'FILE'
                    try:
                        mtime = os.path.getmtime(full_path)
                        date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
                    except:
                        date_str = ''
                    
                self.local_tree.insert('', 'end', text=entry, values=(size, ftype, date_str))
                
            self.status_bar.config(text=f"Local: {self.local_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read directory: {e}")
            
    def refresh_remote_panel(self):
        """Refresh remote file panel"""
        if not self.remote_client.sock:
            return
            
        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)
            
        try:
            entries = self.remote_client.list_dir(self.remote_path)
            if entries:
                # Filter out empty entries
                entries = [e for e in entries if e.strip()]
                # Sort entries
                sorted_entries = self.sort_entries(entries, is_local=False)
                
                for entry in sorted_entries:
                    if '|' in entry:
                        parts = entry.split('|')
                        name = parts[0]
                        ftype = parts[1]
                        size = parts[2] if len(parts) > 2 else ''
                        
                        display_type = 'DIR' if ftype == 'dir' else 'FILE'
                        display_size = size if ftype == 'file' else ''
                        date_str = ''  # Date not available from server
                        
                        self.remote_tree.insert('', 'end', text=name, values=(display_size, display_type, date_str))
                        
            self.status_bar.config(text=f"Remote: {self.remote_path} [{self.remote_server}]")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read remote directory: {e}")
            
    def on_local_double_click(self, event):
        """Handle double click on local file"""
        selection = self.local_tree.selection()
        if not selection:
            return
            
        item = selection[0]
        name = self.local_tree.item(item, 'text')
        ftype = self.local_tree.item(item, 'values')[1]
        
        if ftype == 'DIR':
            self.local_path = os.path.join(self.local_path, name)
            self.refresh_local_panel()
            self.local_drive_var.set(self.local_path)
            
    def on_remote_double_click(self, event):
        """Handle double click on remote file"""
        selection = self.remote_tree.selection()
        if not selection:
            return
            
        item = selection[0]
        name = self.remote_tree.item(item, 'text')
        ftype = self.remote_tree.item(item, 'values')[1]
        
        if ftype == 'DIR':
            if name == '..':
                self.go_up_remote()
            else:
                self.remote_path = os.path.join(self.remote_path, name)
                if self.remote_client.change_dir(self.remote_path):
                    self.refresh_remote_panel()
                    
    def on_local_enter(self, event):
        """Handle Enter key on local panel"""
        self.on_local_double_click(event)
        
    def on_remote_enter(self, event):
        """Handle Enter key on remote panel"""
        self.on_remote_double_click(event)
        
    def go_up_local(self):
        """Go up one directory in local panel"""
        parent = os.path.dirname(self.local_path)
        if parent and parent != self.local_path:
            self.local_path = parent
            self.refresh_local_panel()
            self.local_drive_var.set(self.local_path)
            
    def go_up_remote(self):
        """Go up one directory in remote panel"""
        parent = os.path.dirname(self.remote_path)
        if parent and parent != self.remote_path:
            self.remote_path = parent
            if self.remote_client.change_dir(self.remote_path):
                self.refresh_remote_panel()
                
    def on_local_drive_change(self, event):
        """Handle local drive change"""
        drive = self.local_drive_var.get()
        if drive and os.path.exists(drive):
            self.local_path = drive
            self.refresh_local_panel()
            
    def on_local_drive_manual(self, event):
        """Handle manual path entry for local drive"""
        path = self.local_drive_var.get().strip()
        if path and os.path.exists(path):
            self.local_path = path
            self.refresh_local_panel()
            
    def on_remote_drive_change(self, event):
        """Handle remote drive change"""
        drive = self.remote_drive_var.get()
        if drive and self.remote_client.sock:
            if self.remote_client.change_dir(drive):
                self.remote_path = drive
                self.refresh_remote_panel()
                
    def on_remote_drive_manual(self, event):
        """Handle manual path entry for remote drive"""
        path = self.remote_drive_var.get().strip()
        if path and self.remote_client.sock:
            if self.remote_client.change_dir(path):
                self.remote_path = path
                self.refresh_remote_panel()
                
    def switch_panel(self, event):
        """Switch between local and remote panels"""
        if self.active_panel == 'local':
            self.active_panel = 'remote'
            self.remote_tree.focus_set()
        else:
            self.active_panel = 'local'
            self.local_tree.focus_set()
        return 'break'
        
    def connect_server(self):
        """Connect to remote server"""
        dialog = ServerConnectDialog(self.root)
        if dialog.result:
            host, port = dialog.result
            try:
                self.remote_client.host = host
                self.remote_client.port = port
                self.remote_client.connect()
                
                self.remote_server = f"{host}:{port}"
                self.connection_label.config(text=f"Connected: {host}:{port}", fg='green')
                
                # Get initial directory listing
                self.remote_path = '/'
                self.populate_remote_drives()
                self.refresh_remote_panel()
                
                self.status_bar.config(text=f"Connected to {host}:{port}")
            except Exception as e:
                messagebox.showerror("Connection Error", f"Failed to connect: {e}")
                self.remote_client.disconnect()
                
    def disconnect_server(self):
        """Disconnect from remote server"""
        if self.remote_client.sock:
            self.remote_client.disconnect()
            self.remote_server = None
            self.connection_label.config(text="Disconnected", fg='red')
            self.remote_drive_combo['values'] = []
            self.remote_drive_var.set('')
            
            for item in self.remote_tree.get_children():
                self.remote_tree.delete(item)
                
            self.status_bar.config(text="Disconnected")
            
    def manual_connect(self):
        """Manual connection dialog"""
        self.connect_server()
        
    def scan_servers(self):
        """Scan network for servers"""
        self.status_bar.config(text="Scanning network...")
        self.root.update()
        
        def scan():
            servers = UDPScanner.scan_network()
            self.root.after(0, lambda: self.show_scan_results(servers))
            
        thread = threading.Thread(target=scan)
        thread.start()
        
    def show_scan_results(self, servers):
        """Show scan results"""
        if servers:
            result = '\n'.join(servers)
            messagebox.showinfo("Servers Found", f"Found UDP servers at:\n{result}")
        else:
            messagebox.showinfo("Scan Complete", "No servers found")
            
        self.status_bar.config(text="Ready")
        
    def copy_file(self):
        """Copy file between panels"""
        if self.active_panel == 'local':
            # Copy from local to remote
            selection = self.local_tree.selection()
            if not selection:
                return
                
            item = selection[0]
            name = self.local_tree.item(item, 'text')
            ftype = self.local_tree.item(item, 'values')[1]
            
            if ftype == 'FILE':
                src_path = os.path.join(self.local_path, name)
                dst_path = os.path.join(self.remote_path, name)
                
                if self.remote_client.upload_file(src_path, dst_path):
                    self.refresh_remote_panel()
                    self.status_bar.config(text=f"Copied {name} to remote")
                else:
                    messagebox.showerror("Error", "Failed to upload file")
            else:
                messagebox.showwarning("Warning", "Directory copy not supported yet")
                
        else:
            # Copy from remote to local
            selection = self.remote_tree.selection()
            if not selection:
                return
                
            item = selection[0]
            name = self.remote_tree.item(item, 'text')
            ftype = self.remote_tree.item(item, 'values')[1]
            
            if ftype == 'FILE':
                src_path = os.path.join(self.remote_path, name)
                dst_path = os.path.join(self.local_path, name)
                
                if self.remote_client.download_file(src_path, dst_path):
                    self.refresh_local_panel()
                    self.status_bar.config(text=f"Copied {name} from remote")
                else:
                    messagebox.showerror("Error", "Failed to download file")
            else:
                messagebox.showwarning("Warning", "Directory copy not supported yet")
                
    def create_directory(self):
        """Create new directory"""
        name = simpledialog.askstring("New Directory", "Enter directory name:")
        if not name:
            return
            
        if self.active_panel == 'local':
            path = os.path.join(self.local_path, name)
            try:
                os.makedirs(path, exist_ok=True)
                self.refresh_local_panel()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create directory: {e}")
        else:
            if self.remote_client.sock:
                path = os.path.join(self.remote_path, name)
                if self.remote_client.mkdir(path):
                    self.refresh_remote_panel()
                else:
                    messagebox.showerror("Error", "Failed to create directory on server")
                    
    def delete_file(self):
        """Delete selected file"""
        if self.active_panel == 'local':
            selection = self.local_tree.selection()
            if not selection:
                return
                
            item = selection[0]
            name = self.local_tree.item(item, 'text')
            
            if messagebox.askyesno("Confirm Delete", f"Delete {name}?"):
                path = os.path.join(self.local_path, name)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        os.rmdir(path)
                    self.refresh_local_panel()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete: {e}")
        else:
            if self.remote_client.sock:
                selection = self.remote_tree.selection()
                if not selection:
                    return
                    
                item = selection[0]
                name = self.remote_tree.item(item, 'text')
                
                if messagebox.askyesno("Confirm Delete", f"Delete {name} from server?"):
                    path = os.path.join(self.remote_path, name)
                    if self.remote_client.delete(path):
                        self.refresh_remote_panel()
                    else:
                        messagebox.showerror("Error", "Failed to delete on server")
                        
    def rename_file(self):
        """Rename selected file"""
        if self.active_panel == 'local':
            selection = self.local_tree.selection()
            if not selection:
                return
                
            item = selection[0]
            old_name = self.local_tree.item(item, 'text')
            
            new_name = simpledialog.askstring("Rename", "Enter new name:", initialvalue=old_name)
            if new_name and new_name != old_name:
                old_path = os.path.join(self.local_path, old_name)
                new_path = os.path.join(self.local_path, new_name)
                try:
                    os.rename(old_path, new_path)
                    self.refresh_local_panel()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to rename: {e}")
        else:
            if self.remote_client.sock:
                selection = self.remote_tree.selection()
                if not selection:
                    return
                    
                item = selection[0]
                old_name = self.remote_tree.item(item, 'text')
                
                new_name = simpledialog.askstring("Rename", "Enter new name:", initialvalue=old_name)
                if new_name and new_name != old_name:
                    old_path = os.path.join(self.remote_path, old_name)
                    new_path = os.path.join(self.remote_path, new_name)
                    if self.remote_client.rename(old_path, new_path):
                        self.refresh_remote_panel()
                    else:
                        messagebox.showerror("Error", "Failed to rename on server")
                        
    def refresh_all(self):
        """Refresh both panels"""
        self.refresh_local_panel()
        if self.remote_client.sock:
            self.refresh_remote_panel()
            
    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        shortcuts = """
Keyboard Shortcuts:
------------------
Tab          - Switch between panels
F5           - Copy file
F7           - Create directory
F8           - Delete file
F2           - Rename file
Ctrl+R       - Refresh both panels
Backspace    - Go up one directory
Enter        - Open file/directory
Double-click - Open file/directory
"""
        messagebox.showinfo("Keyboard Shortcuts", shortcuts)
        
    def show_about(self):
        """Show about dialog"""
        about_text = """
UDP File Manager
Total Commander Style

A dual-panel file manager with:
- Local file system access
- Remote file system via UDP
- Network server scanning
- Full file operations

Version 1.0
"""
        messagebox.showinfo("About", about_text)


class ServerConnectDialog(tk.simpledialog.Dialog):
    """Dialog for connecting to server"""
    
    def body(self, master):
        tk.Label(master, text="Host:").grid(row=0, column=0, sticky=tk.W, pady=5)
        tk.Label(master, text="Port:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        self.host_entry = tk.Entry(master, width=30)
        self.host_entry.grid(row=0, column=1, pady=5)
        self.host_entry.insert(0, '127.0.0.1')
        
        self.port_entry = tk.Entry(master, width=30)
        self.port_entry.grid(row=1, column=1, pady=5)
        self.port_entry.insert(0, '5000')
        
        return self.host_entry
        
    def apply(self):
        try:
            host = self.host_entry.get().strip()
            port = int(self.port_entry.get().strip())
            self.result = (host, port)
        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
            self.result = None


def main():
    """Main entry point"""
    import sys
    
    # Check if running as server
    if len(sys.argv) > 1 and sys.argv[1] == '--server':
        host = '0.0.0.0'
        port = 5000
        if len(sys.argv) > 2:
            port = int(sys.argv[2])
            
        print(f"Starting UDP File Server on {host}:{port}")
        print("Press Ctrl+C to stop")
        
        server = UDPServer(host, port)
        try:
            server.start()
        except KeyboardInterrupt:
            print("\nStopping server...")
            server.stop()
        return
        
    # Run GUI client
    root = tk.Tk()
    app = FileManagerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
