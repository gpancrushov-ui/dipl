#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDP File Manager - Клиент в стиле Total Commander
Полноценный GUI с двухпанельным интерфейсом, поддержкой UDP и локальной ФС.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import socket
import os
import sys
import threading
import json
import time
import platform
import subprocess
from pathlib import Path
from datetime import datetime

# Константы
BUFFER_SIZE = 65535
TIMEOUT = 5.0
DEFAULT_PORT = 5000

class UDPClient:
    """Класс для работы с UDP сервером"""
    def __init__(self, host='127.0.0.1', port=5000):
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False
        
    def connect(self):
        """Инициализация сокета"""
        try:
            if self.sock:
                self.sock.close()
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(TIMEOUT)
            self.connected = True
            return True
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            self.connected = False
            return False
            
    def send_request(self, command, data=None):
        """Отправка команды серверу"""
        if not self.connected:
            if not self.connect():
                return None
                
        request = {'command': command}
        if data:
            request['data'] = data
            
        try:
            msg = json.dumps(request).encode('utf-8')
            self.sock.sendto(msg, (self.host, self.port))
            
            # Получение ответа
            data, _ = self.sock.recvfrom(BUFFER_SIZE)
            response = json.loads(data.decode('utf-8'))
            
            if response.get('status') == 'error':
                raise Exception(response.get('message', 'Неизвестная ошибка'))
                
            return response.get('result')
        except socket.timeout:
            raise Exception("Превышено время ожидания ответа от сервера")
        except Exception as e:
            self.connected = False
            raise Exception(f"Ошибка связи: {str(e)}")
            
    def list_dir(self, path):
        """Получение списка файлов"""
        return self.send_request('LIST_DIR', {'path': path})
        
    def get_drives(self):
        """Получение списка дисков сервера"""
        return self.send_request('GET_DRIVES')
        
    def download_file(self, remote_path, local_path):
        """Скачивание файла с сервера"""
        return self.send_request('DOWNLOAD_FILE', {
            'remote_path': remote_path,
            'local_path': local_path
        })

    def scan_network(self, port=5000, timeout=1.0):
        """Поиск активных серверов в локальной сети"""
        found_servers = []
        # Получаем локальный IP для определения подсети
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"
            
        base_ip = '.'.join(local_ip.split('.')[:3])
        
        def check_host(ip):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(timeout)
                req = json.dumps({'command': 'PING'}).encode('utf-8')
                sock.sendto(req, (ip, port))
                data, _ = sock.recvfrom(1024)
                if data:
                    found_servers.append(ip)
                sock.close()
            except:
                pass
                
        threads = []
        for i in range(1, 255):
            ip = f"{base_ip}.{i}"
            t = threading.Thread(target=check_host, args=(ip,))
            t.start()
            threads.append(t)
            # Ограничение количества одновременных потоков
            if len(threads) % 50 == 0:
                for t in threads: t.join()
                threads = []
                
        for t in threads: t.join()
        return found_servers


class FileManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UDP File Manager (Total Commander Style)")
        self.root.geometry("1200x800")
        
        # Состояние
        self.local_path = os.getcwd()
        self.remote_path = "/"
        self.server_address = "127.0.0.1"
        self.server_port = DEFAULT_PORT
        self.udp_client = UDPClient()
        self.is_connected = False
        self.active_panel = 'local' # 'local' или 'remote'
        self.sort_key = 'name'
        self.sort_reverse = False
        
        # Настройка стилей
        self.setup_styles()
        
        # Создание интерфейса
        self.create_menu()
        self.create_toolbar()
        self.create_connection_bar()
        self.create_main_area()
        self.create_status_bar()
        
        # Обновление панелей
        self.refresh_local()
        
    def setup_styles(self):
        """Настройка цветов и шрифтов"""
        self.colors = {
            'bg': '#f0f0f0',
            'panel_bg': '#ffffff',
            'select_bg': '#3399ff',
            'select_fg': '#ffffff',
            'dir_color': '#000080',
            'exe_color': '#008000',
            'text_font': ('Consolas', 10) if platform.system() == 'Windows' else ('DejaVu Sans Mono', 10),
            'header_font': ('Arial', 9, 'bold')
        }
        self.root.configure(bg=self.colors['bg'])
        
    def create_menu(self):
        """Создание меню"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Выход", command=self.root.quit)
        
        net_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Сеть", menu=net_menu)
        net_menu.add_command(label="Поиск серверов", command=self.scan_network_gui)
        net_menu.add_command(label="Переподключиться", command=self.connect_to_server)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)
        
    def create_toolbar(self):
        """Панель инструментов с кнопками"""
        toolbar = tk.Frame(self.root, bg=self.colors['bg'], pady=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        btn_style = {'width': 10, 'padx': 5}
        
        tk.Button(toolbar, text="F5 Копировать", command=self.copy_files, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Скачать", command=self.download_selected, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="F7 Папка", command=self.create_directory, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="F8 Удалить", command=self.delete_files, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="F2 Переим.", command=self.rename_file, **btn_style).pack(side=tk.LEFT, padx=2)
        
        tk.Label(toolbar, text=" | ", bg=self.colors['bg']).pack(side=tk.LEFT, padx=5)
        
        tk.Button(toolbar, text="Обновить (Ctrl+R)", command=self.refresh_all, **btn_style).pack(side=tk.LEFT, padx=2)
        
    def create_connection_bar(self):
        """Панель подключения к серверу"""
        conn_frame = tk.Frame(self.root, bg='#e0e0e0', pady=5, padx=10)
        conn_frame.pack(side=tk.TOP, fill=tk.X)
        
        tk.Label(conn_frame, text="Сервер:", bg='#e0e0e0').pack(side=tk.LEFT)
        
        self.ip_entry = tk.Entry(conn_frame, width=15)
        self.ip_entry.insert(0, self.server_address)
        self.ip_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(conn_frame, text=":", bg='#e0e0e0').pack(side=tk.LEFT)
        
        self.port_entry = tk.Entry(conn_frame, width=6)
        self.port_entry.insert(0, str(self.server_port))
        self.port_entry.pack(side=tk.LEFT, padx=5)
        
        self.conn_btn = tk.Button(conn_frame, text="Подключиться", command=self.toggle_connection, bg='#dddddd')
        self.conn_btn.pack(side=tk.LEFT, padx=10)
        
        self.status_label = tk.Label(conn_frame, text="Отключено", fg='red', bg='#e0e0e0')
        self.status_label.pack(side=tk.LEFT, padx=10)
        
    def create_main_area(self):
        """Основная область с двумя панелями"""
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.colors['bg'])
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- ЛЕВАЯ ПАНЕЛЬ (ЛОКАЛЬНАЯ) ---
        left_frame = tk.Frame(main_paned, bg=self.colors['panel_bg'])
        main_paned.add(left_frame, width=550)
        
        # Заголовок и диск
        l_top = tk.Frame(left_frame, bg=self.colors['panel_bg'])
        l_top.pack(fill=tk.X, padx=2, pady=2)
        tk.Label(l_top, text="Локальный компьютер", font=self.colors['header_font'], bg=self.colors['panel_bg']).pack(side=tk.LEFT)
        
        self.local_drive_var = tk.StringVar()
        self.local_drive_combo = ttk.Combobox(l_top, textvariable=self.local_drive_var, width=10, state='editable')
        self.local_drive_combo.pack(side=tk.RIGHT)
        self.local_drive_combo.bind('<<ComboboxSelected>>', self.on_local_drive_change)
        self.local_drive_combo.bind('<Return>', self.on_local_drive_enter)
        self.update_local_drives()
        
        # Путь
        self.local_path_label = tk.Label(left_frame, text=self.local_path, anchor='w', bg='#ffffcc', relief=tk.SUNKEN)
        self.local_path_label.pack(fill=tk.X, padx=2, pady=2)
        
        # Таблица файлов
        self.local_tree = self.create_file_table(left_frame, self.on_local_double_click)
        self.local_tree.bind('<FocusIn>', lambda e: self.set_active_panel('local'))
        self.local_tree.bind('<Return>', self.on_local_enter_key)
        
        # --- ПРАВАЯ ПАНЕЛЬ (УДАЛЕННАЯ) ---
        right_frame = tk.Frame(main_paned, bg=self.colors['panel_bg'])
        main_paned.add(right_frame, width=550)
        
        # Заголовок и диск
        r_top = tk.Frame(right_frame, bg=self.colors['panel_bg'])
        r_top.pack(fill=tk.X, padx=2, pady=2)
        tk.Label(r_top, text="Удаленный сервер", font=self.colors['header_font'], bg=self.colors['panel_bg']).pack(side=tk.LEFT)
        
        self.remote_drive_var = tk.StringVar()
        self.remote_drive_combo = ttk.Combobox(r_top, textvariable=self.remote_drive_var, width=10, state='editable')
        self.remote_drive_combo.pack(side=tk.RIGHT)
        self.remote_drive_combo.bind('<<ComboboxSelected>>', self.on_remote_drive_change)
        self.remote_drive_combo.bind('<Return>', self.on_remote_drive_enter)
        
        # Путь
        self.remote_path_label = tk.Label(right_frame, text="Не подключено", anchor='w', bg='#ffffcc', relief=tk.SUNKEN)
        self.remote_path_label.pack(fill=tk.X, padx=2, pady=2)
        
        # Таблица файлов
        self.remote_tree = self.create_file_table(right_frame, self.on_remote_double_click)
        self.remote_tree.bind('<FocusIn>', lambda e: self.set_active_panel('remote'))
        self.remote_tree.bind('<Return>', self.on_remote_enter_key)
        
        # Привязка клавиш навигации
        self.root.bind('<Tab>', self.switch_panel)
        self.root.bind('<Control-R>', lambda e: self.refresh_all())
        self.root.bind('<Control-r>', lambda e: self.refresh_all())
        self.root.bind('<F5>', lambda e: self.copy_files())
        self.root.bind('<F7>', lambda e: self.create_directory())
        self.root.bind('<F8>', lambda e: self.delete_files())
        self.root.bind('<BackSpace>', self.go_up_dir)
        
    def create_file_table(self, parent, double_click_cmd):
        """Создание таблицы файлов (Treeview)"""
        cols = ('size', 'date', 'type')
        tree = ttk.Treeview(parent, columns=cols, show='headings', selectmode='extended')
        
        tree.heading('name', text='Имя', command=lambda: self.sort_files(tree, 'name'))
        tree.heading('size', text='Размер', command=lambda: self.sort_files(tree, 'size'))
        tree.heading('date', text='Дата', command=lambda: self.sort_files(tree, 'date'))
        tree.heading('type', text='Тип', command=lambda: self.sort_files(tree, 'type'))
        
        tree.column('name', width=250)
        tree.column('size', width=80, anchor='e')
        tree.column('date', width=120, anchor='center')
        tree.column('type', width=80, anchor='center')
        
        # Скроллбары
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        tree.bind('<Double-1>', double_click_cmd)
        return tree
        
    def create_status_bar(self):
        """Строка состояния"""
        self.status_bar = tk.Label(self.root, text="Готово", anchor='w', relief=tk.SUNKEN, bd=1)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    # --- ЛОГИКА РАБОТЫ С ФАЙЛАМИ ---
    
    def update_local_drives(self):
        """Обновление списка локальных дисков"""
        drives = []
        system = platform.system()
        if system == 'Windows':
            import string
            from ctypes import windll
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(f"{letter}:\\")
                bitmask >>= 1
        else:
            # Для Linux/Unix добавляем корень и основные точки монтирования
            drives = ['/', '/home', '/mnt', '/media']
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) > 1 and parts[1].startswith('/'):
                            mount = parts[1]
                            if mount not in drives and not mount.startswith('/proc') and not mount.startswith('/sys'):
                                drives.append(mount)
            except:
                pass
        
        current = self.local_drive_var.get()
        self.local_drive_combo['values'] = drives
        if not current and drives:
            self.local_drive_var.set(drives[0])
            
    def update_remote_drives(self):
        """Запрос списка дисков у сервера"""
        if not self.is_connected:
            return
        try:
            drives = self.udp_client.get_drives()
            if drives:
                self.remote_drive_combo['values'] = drives
        except Exception as e:
            print(f"Ошибка получения дисков: {e}")

    def refresh_local(self):
        """Обновление локальной панели"""
        self.local_tree.delete(*self.local_tree.get_children())
        self.local_path_label.config(text=self.local_path)
        
        # Добавляем ".." если не в корне
        if self.local_path != os.path.dirname(self.local_path) and self.local_path != '/':
             # Простая проверка на корень для разных ОС
            is_root = False
            if platform.system() == 'Windows':
                is_root = len(self.local_path) <= 3 # C:\
            else:
                is_root = self.local_path == '/'
            
            if not is_root:
                self.local_tree.insert('', 'end', values=('..', '', 'Папка', 'DIR'), tags=('dir',))

        try:
            items = []
            with os.scandir(self.local_path) as it:
                for entry in it:
                    try:
                        size = entry.stat().st_size if entry.is_file() else ''
                        mtime = datetime.fromtimestamp(entry.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                        f_type = 'Папка' if entry.is_dir() else os.path.splitext(entry.name)[1].upper().replace('.', '') or 'FILE'
                        
                        # Форматирование размера
                        if size and size != '':
                            if size > 1024*1024:
                                size_str = f"{size/(1024*1024):.1f} MB"
                            elif size > 1024:
                                size_str = f"{size/1024:.1f} KB"
                            else:
                                size_str = f"{size} B"
                        else:
                            size_str = ''
                            
                        items.append((entry.name, size_str, mtime, f_type, entry.is_dir()))
                    except PermissionError:
                        continue
            
            # Сортировка
            items.sort(key=lambda x: (not x[4], x[0])) # Папки первыми
            
            for name, size, date, ftype, is_dir in items:
                tag = 'dir' if is_dir else 'file'
                self.local_tree.insert('', 'end', values=(name, size, date, ftype), tags=(tag,))
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать директорию: {e}")
            
    def refresh_remote(self):
        """Обновление удаленной панели"""
        self.remote_tree.delete(*self.remote_tree.get_children())
        if not self.is_connected:
            self.remote_path_label.config(text="Не подключено")
            return
            
        self.remote_path_label.config(text=self.remote_path)
        
        try:
            data = self.udp_client.list_dir(self.remote_path)
            if not data:
                return
                
            items = []
            for item in data:
                name = item['name']
                if name == '..':
                    continue
                size = item.get('size', '')
                if size and size != '':
                     if isinstance(size, int):
                        if size > 1024*1024:
                            size_str = f"{size/(1024*1024):.1f} MB"
                        elif size > 1024:
                            size_str = f"{size/1024:.1f} KB"
                        else:
                            size_str = f"{size} B"
                     else:
                         size_str = str(size)
                else:
                    size_str = ''
                    
                date = item.get('date', '')
                ftype = 'Папка' if item.get('is_dir') else 'FILE'
                is_dir = item.get('is_dir', False)
                items.append((name, size_str, date, ftype, is_dir))
            
            items.sort(key=lambda x: (not x[4], x[0]))
            
            for name, size, date, ftype, is_dir in items:
                tag = 'dir' if is_dir else 'file'
                self.remote_tree.insert('', 'end', values=(name, size, date, ftype), tags=(tag,))
                
        except Exception as e:
            self.status_bar.config(text=f"Ошибка сервера: {e}", fg='red')

    # --- ОБРАБОТЧИКИ СОБЫТИЙ ---
    
    def on_local_double_click(self, event):
        selection = self.local_tree.selection()
        if not selection: return
        item = self.local_tree.item(selection[0])
        name = item['values'][0]
        
        if name == '..':
            self.local_path = os.path.dirname(self.local_path)
            self.refresh_local()
        elif item['tags'][0] == 'dir':
            self.local_path = os.path.join(self.local_path, name)
            self.refresh_local()
        else:
            # Открытие файла
            self.open_local_file(name)
            
    def open_local_file(self, filename):
        """Открытие файла стандартной программой"""
        filepath = os.path.join(self.local_path, filename)
        try:
            if platform.system() == 'Windows':
                os.startfile(filepath)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', filepath])
            else:
                subprocess.run(['xdg-open', filepath])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
            
    def on_remote_double_click(self, event):
        if not self.is_connected: return
        selection = self.remote_tree.selection()
        if not selection: return
        item = self.remote_tree.item(selection[0])
        name = item['values'][0]
        
        if name == '..':
            self.remote_path = os.path.dirname(self.remote_path)
            if self.remote_path == '': self.remote_path = '/'
            self.refresh_remote()
        elif item['tags'][0] == 'dir':
            if self.remote_path.endswith('/'):
                self.remote_path += name
            else:
                self.remote_path += '/' + name
            self.refresh_remote()
        else:
            # Предложение скачать файл
            if messagebox.askyesno("Скачивание", f"Скачать файл {name}?"):
                self.download_single_file(name)

    def on_local_enter_key(self, event):
        self.on_local_double_click(None)
        
    def on_remote_enter_key(self, event):
        self.on_remote_double_click(None)

    def set_active_panel(self, panel):
        self.active_panel = panel
        color = '#ffffcc' if panel == 'local' else '#ccffcc'
        self.local_path_label.config(bg=color if panel == 'local' else '#ffffcc')
        self.remote_path_label.config(bg=color if panel == 'remote' else '#ffffcc')
        
    def switch_panel(self, event):
        if self.active_panel == 'local':
            self.remote_tree.focus_set()
            self.set_active_panel('remote')
        else:
            self.local_tree.focus_set()
            self.set_active_panel('local')
        return 'break'
        
    def on_local_drive_change(self, event):
        drive = self.local_drive_var.get()
        if os.path.exists(drive):
            self.local_path = drive
            self.refresh_local()
            
    def on_local_drive_enter(self, event):
        path = self.local_drive_var.get()
        if os.path.exists(path):
            self.local_path = path
            self.refresh_local()
        else:
            messagebox.showerror("Ошибка", "Путь не существует")
            
    def on_remote_drive_change(self, event):
        if not self.is_connected: return
        drive = self.remote_drive_var.get()
        self.remote_path = drive
        self.refresh_remote()
        
    def on_remote_drive_enter(self, event):
        if not self.is_connected: return
        path = self.remote_drive_var.get()
        self.remote_path = path
        self.refresh_remote()

    # --- СЕТЕВЫЕ ОПЕРАЦИИ ---
    
    def toggle_connection(self):
        if self.is_connected:
            self.is_connected = False
            self.udp_client.connected = False
            self.conn_btn.config(text="Подключиться", bg='#dddddd')
            self.status_label.config(text="Отключено", fg='red')
            self.remote_path_label.config(text="Не подключено")
            self.remote_tree.delete(*self.remote_tree.get_children())
            self.status_bar.config(text="Отключено от сервера")
        else:
            self.connect_to_server()
            
    def connect_to_server(self):
        ip = self.ip_entry.get()
        try:
            port = int(self.port_entry.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный номер порта")
            return
            
        self.server_address = ip
        self.server_port = port
        self.udp_client.host = ip
        self.udp_client.port = port
        
        self.status_label.config(text="Подключение...", fg='orange')
        self.root.update()
        
        if self.udp_client.connect():
            # Проверка связи
            try:
                self.udp_client.list_dir('/') # Тестовый запрос
                self.is_connected = True
                self.conn_btn.config(text="Отключиться", bg='#ffcccc')
                self.status_label.config(text=f"Подключено: {ip}:{port}", fg='green')
                self.remote_path = "/"
                self.update_remote_drives()
                self.refresh_remote()
                self.status_bar.config(text=f"Подключено к {ip}:{port}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Сервер не ответил корректно: {e}")
                self.is_connected = False
                self.status_label.config(text="Ошибка", fg='red')
        else:
            messagebox.showerror("Ошибка", "Не удалось подключиться к серверу")
            self.status_label.config(text="Ошибка", fg='red')
            
    def scan_network_gui(self):
        self.status_bar.config(text="Сканирование сети...")
        self.root.update()
        
        def scan():
            servers = self.udp_client.scan_network(self.server_port)
            self.root.after(0, lambda: self.show_scan_result(servers))
            
        threading.Thread(target=scan, daemon=True).start()
        
    def show_scan_result(self, servers):
        if not servers:
            messagebox.showinfo("Поиск", "Серверы не найдены")
        else:
            win = tk.Toplevel(self.root)
            win.title("Найденные серверы")
            win.geometry("300x200")
            lb = tk.Listbox(win)
            lb.pack(fill=tk.BOTH, expand=True)
            for s in servers:
                lb.insert(tk.END, s)
            lb.bind('<Double-1>', lambda e: self.select_scanned_server(lb.get(lb.curselection()), win))
            
    def select_scanned_server(self, ip, win):
        self.ip_entry.delete(0, tk.END)
        self.ip_entry.insert(0, ip)
        win.destroy()
        self.connect_to_server()

    # --- ФУНКЦИОНАЛЬНЫЕ КНОПКИ ---
    
    def download_selected(self):
        """Скачивание выбранных файлов с сервера в локальную папку"""
        if not self.is_connected:
            messagebox.showwarning("Внимание", "Нет подключения к серверу")
            return
            
        selection = self.remote_tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите файлы для скачивания")
            return
            
        for item_id in selection:
            item = self.remote_tree.item(item_id)
            name = item['values'][0]
            is_dir = item['tags'][0] == 'dir'
            
            if is_dir:
                # Рекурсивное скачивание папок требует сложной логики, пока только предупреждение
                messagebox.showinfo("Инфо", f"Скачивание папок ({name}) пока не поддерживается, только файлы.")
                continue
                
            self.download_single_file(name)
            
    def download_single_file(self, filename):
        """Скачивание одного файла"""
        remote_full = os.path.join(self.remote_path, filename).replace('\\', '/')
        local_full = os.path.join(self.local_path, filename)
        
        self.status_bar.config(text=f"Скачивание {filename}...")
        self.root.update()
        
        try:
            res = self.udp_client.send_request('GET_FILE_CONTENT', {'path': remote_full})
            
            if res and 'content' in res:
                import base64
                data = base64.b64decode(res['content'])
                with open(local_full, 'wb') as f:
                    f.write(data)
                messagebox.showinfo("Успех", f"Файл {filename} скачан!")
                self.refresh_local()
            else:
                messagebox.showwarning("Внимание", "Сервер не передал содержимое файла (возможно, файл слишком большой для UDP пакета).")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скачать файл: {e}")
        finally:
            self.status_bar.config(text="Готово")

    def copy_files(self):
        """Копирование между панелями"""
        if self.active_panel == 'local':
            # Копирование ЛОКАЛЬНЫЙ -> УДАЛЕННЫЙ
            if not self.is_connected:
                messagebox.showwarning("Внимание", "Нет подключения к серверу")
                return
            selection = self.local_tree.selection()
            if not selection: return
            
            messagebox.showinfo("Инфо", "Загрузка файлов на сервер пока не реализована в демо-режиме.")
            
        else:
            # Копирование УДАЛЕННЫЙ -> ЛОКАЛЬНЫЙ (то же что Скачать)
            self.download_selected()

    def create_directory(self):
        """Создание директории"""
        name = simpledialog.askstring("Новая папка", "Имя папки:")
        if not name: return
        
        if self.active_panel == 'local':
            try:
                os.makedirs(os.path.join(self.local_path, name))
                self.refresh_local()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        else:
            if not self.is_connected: return
            try:
                self.udp_client.send_request('MKDIR', {'path': os.path.join(self.remote_path, name)})
                self.refresh_remote()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
                
    def delete_files(self):
        """Удаление файлов"""
        if messagebox.askyesno("Подтверждение", "Удалить выбранные файлы?"):
            if self.active_panel == 'local':
                selection = self.local_tree.selection()
                for item_id in selection:
                    name = self.local_tree.item(item_id)['values'][0]
                    path = os.path.join(self.local_path, name)
                    try:
                        if os.path.isdir(path):
                            os.rmdir(path)
                        else:
                            os.remove(path)
                    except Exception as e:
                        messagebox.showerror("Ошибка", str(e))
                self.refresh_local()
            else:
                if not self.is_connected: return
                selection = self.remote_tree.selection()
                for item_id in selection:
                    name = self.remote_tree.item(item_id)['values'][0]
                    path = os.path.join(self.remote_path, name)
                    try:
                        self.udp_client.send_request('DELETE', {'path': path})
                    except Exception as e:
                        messagebox.showerror("Ошибка", str(e))
                self.refresh_remote()

    def rename_file(self):
        """Переименование"""
        if self.active_panel == 'local':
            selection = self.local_tree.selection()
            if not selection: return
            old_name = self.local_tree.item(selection[0])['values'][0]
            new_name = simpledialog.askstring("Переименовать", "Новое имя:", initialvalue=old_name)
            if new_name and new_name != old_name:
                os.rename(os.path.join(self.local_path, old_name), os.path.join(self.local_path, new_name))
                self.refresh_local()
        else:
            if not self.is_connected: return
            selection = self.remote_tree.selection()
            if not selection: return
            old_name = self.remote_tree.item(selection[0])['values'][0]
            new_name = simpledialog.askstring("Переименовать", "Новое имя:", initialvalue=old_name)
            if new_name and new_name != old_name:
                self.udp_client.send_request('RENAME', {
                    'old_path': os.path.join(self.remote_path, old_name),
                    'new_path': os.path.join(self.remote_path, new_name)
                })
                self.refresh_remote()

    def sort_files(self, tree, key):
        """Сортировка колонок"""
        items = [(tree.set(child, key), child) for child in tree.get_children('')]
        
        # Определение типа сортировки
        if key == 'size':
            def convert(val):
                try:
                    if 'MB' in val: return float(val.replace(' MB', '')) * 1024 * 1024
                    if 'KB' in val: return float(val.replace(' KB', '')) * 1024
                    if 'B' in val: return float(val.replace(' B', ''))
                    return 0
                except: return 0
            items.sort(key=lambda x: convert(x[0]), reverse=self.sort_reverse)
        elif key == 'date':
             items.sort(key=lambda x: x[0], reverse=self.sort_reverse)
        else:
            items.sort(key=lambda x: x[0], reverse=self.sort_reverse)
            
        for index, (val, child) in enumerate(items):
            tree.move(child, '', index)
        
        self.sort_reverse = not self.sort_reverse
        self.sort_key = key

    def go_up_dir(self, event):
        """Переход вверх на одну директорию"""
        if self.active_panel == 'local':
            if self.local_path != os.path.dirname(self.local_path):
                self.local_path = os.path.dirname(self.local_path)
                self.refresh_local()
        else:
            if self.is_connected and self.remote_path != '/':
                self.remote_path = os.path.dirname(self.remote_path)
                if self.remote_path == '': self.remote_path = '/'
                self.refresh_remote()

    def refresh_all(self):
        self.refresh_local()
        if self.is_connected:
            self.refresh_remote()
        self.status_bar.config(text="Обновлено")
        
    def show_about(self):
        messagebox.showinfo("О программе", "UDP File Manager v2.0\nСтиль Total Commander\nРаботает через UDP протокол")


def main():
    root = tk.Tk()
    app = FileManagerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
