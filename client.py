#!/usr/bin/env python3
"""
UDP File Manager Client
Клиентская часть с интерфейсом в стиле Total Commander
Двухпанельный файловый менеджер для работы через UDP
"""

import socket
import json
import base64
import curses
import sys
from pathlib import Path
from datetime import datetime


class UDPFileClient:
    def __init__(self, server_host='127.0.0.1', server_port=5000):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(5.0)
        
        # Левая панель (локальная)
        self.left_path = Path.cwd()
        self.left_items = []
        self.left_selected = 0
        
        # Правая панель (удаленная)
        self.right_path = Path('/')
        self.right_items = []
        self.right_selected = 0
        
        # Активная панель (0 - левая, 1 - правая)
        self.active_panel = 0
        
        # Статус бар
        self.status_message = ""
        
    def send_request(self, request):
        """Отправка запроса на сервер"""
        data = json.dumps(request).encode('utf-8')
        self.socket.sendto(data, (self.server_host, self.server_port))
        
    def receive_response(self):
        """Получение ответа от сервера"""
        chunks = []
        while True:
            try:
                data, _ = self.socket.recvfrom(4096)
                response = json.loads(data.decode('utf-8'))
                
                if 'chunk_index' in response:
                    chunks.append(response['data'])
                    if response.get('is_last', False):
                        full_data = ''.join(chunks)
                        return json.loads(full_data.encode('latin-1').decode('utf-8'))
                else:
                    return response
            except socket.timeout:
                return {'status': 'error', 'message': 'Таймаут соединения'}
            except json.JSONDecodeError:
                continue
    
    def list_remote_dir(self, path=None):
        """Запрос списка файлов с сервера"""
        if path is None:
            path = str(self.right_path)
        
        self.send_request({'command': 'list_dir', 'path': path})
        response = self.receive_response()
        
        if response.get('status') == 'ok':
            self.right_path = Path(response['path'])
            self.right_items = response['items']
            if self.right_selected >= len(self.right_items):
                self.right_selected = max(0, len(self.right_items) - 1)
            return True
        else:
            self.status_message = f"Ошибка: {response.get('message', 'Неизвестная ошибка')}"
            return False
    
    def list_local_dir(self, path=None):
        """Получение списка локальных файлов"""
        if path is None:
            path = self.left_path
        
        try:
            path = Path(path).resolve()
            items = []
            
            if path.parent != path:
                items.append({
                    'name': '..',
                    'type': 'dir',
                    'size': 0,
                    'modified': ''
                })
            
            for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                try:
                    stat = item.stat()
                    items.append({
                        'name': item.name,
                        'type': 'dir' if item.is_dir() else 'file',
                        'size': stat.st_size if item.is_file() else 0,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                    })
                except PermissionError:
                    items.append({
                        'name': item.name,
                        'type': 'error',
                        'size': 0,
                        'modified': ''
                    })
            
            self.left_path = path
            self.left_items = items
            if self.left_selected >= len(self.left_items):
                self.left_selected = max(0, len(self.left_items) - 1)
            return True
        except Exception as e:
            self.status_message = f"Ошибка: {str(e)}"
            return False
    
    def get_remote_file(self, remote_path, local_path):
        """Скачивание файла с сервера"""
        self.send_request({'command': 'get_file', 'path': str(remote_path)})
        
        file_data = b''
        received_metadata = False
        
        while True:
            response = self.receive_response()
            
            if response.get('status') == 'error':
                self.status_message = f"Ошибка: {response.get('message', '')}"
                return False
            
            if response.get('type') == 'file_data' and not received_metadata:
                received_metadata = True
                continue
            elif response.get('type') == 'chunk':
                file_data += base64.b64decode(response['data'])
            elif response.get('type') == 'end':
                break
        
        try:
            with open(local_path, 'wb') as f:
                f.write(file_data)
            self.status_message = f"Файл загружен: {local_path}"
            self.list_local_dir()
            return True
        except Exception as e:
            self.status_message = f"Ошибка записи: {str(e)}"
            return False
    
    def put_remote_file(self, local_path, remote_path):
        """Загрузка файла на сервер"""
        try:
            with open(local_path, 'rb') as f:
                data = f.read()
            
            chunk_size = 1000
            total_chunks = (len(data) + chunk_size - 1) // chunk_size
            
            for i in range(total_chunks):
                chunk = data[i*chunk_size:(i+1)*chunk_size]
                is_last = i == total_chunks - 1
                
                request = {
                    'command': 'put_file',
                    'path': str(remote_path),
                    'data': base64.b64encode(chunk).decode('ascii'),
                    'last': is_last
                }
                
                self.send_request(request)
                response = self.receive_response()
                
                if response.get('status') != 'ok':
                    self.status_message = f"Ошибка загрузки: {response.get('message', '')}"
                    return False
            
            self.status_message = "Файл загружен на сервер"
            self.list_remote_dir()
            return True
        except Exception as e:
            self.status_message = f"Ошибка чтения: {str(e)}"
            return False
    
    def delete_remote(self, path):
        """Удаление файла/директории на сервере"""
        self.send_request({'command': 'delete', 'path': str(path)})
        response = self.receive_response()
        
        if response.get('status') == 'ok':
            self.status_message = "Удалено успешно"
            self.list_remote_dir()
            return True
        else:
            self.status_message = f"Ошибка: {response.get('message', '')}"
            return False
    
    def delete_local(self, path):
        """Удаление локального файла/директории"""
        try:
            path = Path(path)
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
            self.status_message = "Удалено успешно"
            self.list_local_dir()
            return True
        except Exception as e:
            self.status_message = f"Ошибка: {str(e)}"
            return False
    
    def mkdir_remote(self, name):
        """Создание директории на сервере"""
        path = self.right_path / name
        self.send_request({'command': 'mkdir', 'path': str(path)})
        response = self.receive_response()
        
        if response.get('status') == 'ok':
            self.status_message = "Директория создана"
            self.list_remote_dir()
            return True
        else:
            self.status_message = f"Ошибка: {response.get('message', '')}"
            return False
    
    def mkdir_local(self, name):
        """Создание локальной директории"""
        try:
            path = self.left_path / name
            path.mkdir(parents=True, exist_ok=True)
            self.status_message = "Директория создана"
            self.list_local_dir()
            return True
        except Exception as e:
            self.status_message = f"Ошибка: {str(e)}"
            return False
    
    def draw_panel(self, stdscr, items, selected, path, is_active, start_y, start_x, width, height):
        """Рисование панели файлов"""
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)   # Активная панель
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Директории
        curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Файлы
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)   # Заголовки
        curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)    # Ошибки
        
        # Рамка панели
        border_attr = curses.color_pair(4) if is_active else curses.A_DIM
        
        # Заголовок с путем
        title = f" {path} "
        stdscr.attron(border_attr)
        try:
            stdscr.addstr(start_y, start_x, "─" * (width - 2))
            stdscr.addstr(start_y + 1, start_x, f"│{title:^{width-2}}│")
            stdscr.addstr(start_y + 2, start_x, "─" * (width - 2))
        except curses.error:
            pass
        stdscr.attroff(border_attr)
        
        # Список файлов
        content_start = start_y + 3
        visible_height = height - 6
        
        # Прокрутка
        scroll_offset = 0
        if selected >= visible_height:
            scroll_offset = selected - visible_height + 1
        
        for i in range(visible_height):
            idx = i + scroll_offset
            y = content_start + i
            
            if idx < len(items):
                item = items[idx]
                name = item['name']
                item_type = item['type']
                size = item['size']
                
                # Форматирование строки
                if item_type == 'dir':
                    display_name = f"[{name}]"
                    attr = curses.color_pair(2) | curses.A_BOLD
                elif item_type == 'error':
                    display_name = f"[{name}] (нет доступа)"
                    attr = curses.color_pair(5)
                else:
                    display_name = name
                    attr = curses.color_pair(3)
                
                # Выделение выбранного элемента
                if idx == selected and is_active:
                    attr |= curses.color_pair(1) | curses.A_REVERSE
                
                # Обрезка по ширине
                max_name_len = width - 12
                if len(display_name) > max_name_len:
                    display_name = display_name[:max_name_len-3] + "..."
                
                # Размер файла
                if size > 0:
                    size_str = self.format_size(size)
                else:
                    size_str = ""
                
                line = f"{display_name:<{max_name_len}} {size_str:>10}"
                
                try:
                    stdscr.addstr(y, start_x + 1, line.ljust(width - 2)[:width-2], attr)
                except curses.error:
                    pass
            else:
                try:
                    stdscr.addstr(y, start_x + 1, " " * (width - 2))
                except curses.error:
                    pass
    
    def format_size(self, size):
        """Форматирование размера файла"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def draw_status_bar(self, stdscr, height, width):
        """Рисование статусной строки"""
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)
        
        left_info = f"L: {self.left_path}"
        right_info = f"R: {self.right_path}"
        status = f" {self.status_message}" if self.status_message else ""
        
        try:
            stdscr.attron(curses.color_pair(6))
            stdscr.addstr(height - 2, 0, f"{left_info}  │  {right_info}{status}".ljust(width)[:width])
            stdscr.attroff(curses.color_pair(6))
        except curses.error:
            pass
    
    def draw_help_bar(self, stdscr, height, width):
        """Рисование строки помощи"""
        help_text = " F1-Help F3-View F4-Edit F5-Copy F6-Move F7-Mkdir F8-Del F9-Menu F10-Quit Tab-SwitchPanel "
        try:
            stdscr.addstr(height - 1, 0, help_text.center(width)[:width], curses.A_REVERSE)
        except curses.error:
            pass
    
    def run(self, stdscr):
        """Основной цикл приложения"""
        curses.curs_set(0)
        stdscr.clear()
        
        # Инициализация цветов
        curses.start_color()
        curses.use_default_colors()
        
        # Первоначальная загрузка
        self.list_local_dir()
        self.list_remote_dir()
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Разделение экрана на две панели
            panel_width = width // 2
            
            # Рисование панелей
            self.draw_panel(stdscr, self.left_items, self.left_selected, 
                          self.left_path, self.active_panel == 0,
                          0, 0, panel_width, height - 3)
            
            self.draw_panel(stdscr, self.right_items, self.right_selected,
                          self.right_path, self.active_panel == 1,
                          0, panel_width, width - panel_width, height - 3)
            
            # Разделитель между панелями
            for y in range(height - 3):
                try:
                    stdscr.addch(y, panel_width - 1, '│', curses.color_pair(4))
                except curses.error:
                    pass
            
            # Статус бар и помощь
            self.draw_status_bar(stdscr, height, width)
            self.draw_help_bar(stdscr, height, width)
            
            stdscr.refresh()
            
            # Обработка ввода
            key = stdscr.getch()
            
            if key == ord('q') or key == 27:  # Q или Escape
                break
            elif key == 9:  # Tab
                self.active_panel = 1 - self.active_panel
                self.status_message = ""
            elif key == curses.KEY_UP or key == ord('k'):
                if self.active_panel == 0:
                    self.left_selected = max(0, self.left_selected - 1)
                else:
                    self.right_selected = max(0, self.right_selected - 1)
            elif key == curses.KEY_DOWN or key == ord('j'):
                if self.active_panel == 0:
                    self.left_selected = min(len(self.left_items) - 1, self.left_selected + 1)
                else:
                    self.right_selected = min(len(self.right_items) - 1, self.right_selected + 1)
            elif key == curses.KEY_LEFT or key == ord('h'):
                # Переход в родительскую директорию
                if self.active_panel == 0:
                    if self.left_path != self.left_path.parent:
                        self.list_local_dir(self.left_path.parent)
                else:
                    if self.right_items and self.right_items[0]['name'] == '..':
                        self.right_selected = 0
                        self.enter_directory()
            elif key == curses.KEY_RIGHT or key == ord('l') or key == 10:  # Enter
                self.enter_directory()
            elif key == curses.KEY_F5 or key == ord('c'):  # Копировать
                self.copy_file()
            elif key == curses.KEY_F6 or key == ord('m'):  # Переместить
                self.move_file()
            elif key == curses.KEY_F7 or key == ord('n'):  # Создать директорию
                self.create_directory()
            elif key == curses.KEY_F8 or key == ord('d'):  # Удалить
                self.delete_item()
            elif key == curses.KEY_F9:  # Меню (смена сервера)
                self.change_server()
            elif key == curses.KEY_HOME:
                if self.active_panel == 0:
                    self.left_selected = 0
                else:
                    self.right_selected = 0
            elif key == curses.KEY_END:
                if self.active_panel == 0:
                    self.left_selected = len(self.left_items) - 1
                else:
                    self.right_selected = len(self.right_items) - 1
    
    def enter_directory(self):
        """Вход в директорию"""
        if self.active_panel == 0:
            items = self.left_items
            selected = self.left_selected
        else:
            items = self.right_items
            selected = self.right_selected
        
        if selected >= len(items):
            return
        
        item = items[selected]
        
        if item['name'] == '..':
            # Переход вверх
            if self.active_panel == 0:
                self.list_local_dir(self.left_path.parent)
            else:
                parent = self.right_path.parent
                self.list_remote_dir(str(parent))
        elif item['type'] == 'dir':
            # Вход в директорию
            if self.active_panel == 0:
                self.list_local_dir(self.left_path / item['name'])
            else:
                self.list_remote_dir(str(self.right_path / item['name']))
    
    def copy_file(self):
        """Копирование файла между панелями"""
        if self.active_panel == 0:
            # Копирование с локального на удаленный
            if self.left_selected >= len(self.left_items):
                return
            item = self.left_items[self.left_selected]
            if item['type'] != 'file':
                self.status_message = "Можно копировать только файлы"
                return
            
            local_path = self.left_path / item['name']
            remote_path = self.right_path / item['name']
            self.put_remote_file(local_path, remote_path)
        else:
            # Копирование с удаленного на локальный
            if self.right_selected >= len(self.right_items):
                return
            item = self.right_items[self.right_selected]
            if item['type'] != 'file':
                self.status_message = "Можно копировать только файлы"
                return
            
            remote_path = self.right_path / item['name']
            local_path = self.left_path / item['name']
            self.get_remote_file(remote_path, local_path)
    
    def move_file(self):
        """Перемещение файла (копирование + удаление)"""
        # В данной реализации просто копируем, т.к. перемещение между разными системами
        # требует дополнительной логики
        self.copy_file()
        self.status_message = "Перемещение: скопируйте файл, затем удалите оригинал (F8)"
    
    def create_directory(self):
        """Создание новой директории"""
        stdscr = curses.initscr()
        curses.echo()
        curses.curs_set(1)
        
        try:
            height, width = stdscr.getmaxyx()
            stdscr.addstr(height - 2, 0, "Имя директории: ".ljust(width)[:width])
            stdscr.refresh()
            
            name = stdscr.getstr(height - 2, 17, 50).decode('utf-8').strip()
            
            if name:
                if self.active_panel == 0:
                    self.mkdir_local(name)
                else:
                    self.mkdir_remote(name)
        finally:
            curses.noecho()
            curses.curs_set(0)
    
    def delete_item(self):
        """Удаление файла или директории"""
        if self.active_panel == 0:
            if self.left_selected >= len(self.left_items):
                return
            item = self.left_items[self.left_selected]
            if item['name'] == '..':
                return
            
            path = self.left_path / item['name']
            self.delete_local(path)
        else:
            if self.right_selected >= len(self.right_items):
                return
            item = self.right_items[self.right_selected]
            if item['name'] == '..':
                return
            
            path = self.right_path / item['name']
            self.delete_remote(path)
    
    def change_server(self):
        """Смена адреса сервера"""
        stdscr = curses.initscr()
        curses.echo()
        curses.curs_set(1)
        
        try:
            height, width = stdscr.getmaxyx()
            stdscr.addstr(height - 2, 0, f"Сервер ({self.server_host}:{self.server_port}): ".ljust(width)[:width])
            stdscr.refresh()
            
            addr = stdscr.getstr(height - 2, 40, 50).decode('utf-8').strip()
            
            if addr:
                if ':' in addr:
                    host, port = addr.rsplit(':', 1)
                    try:
                        port = int(port)
                        self.server_host = host
                        self.server_port = port
                        self.status_message = f"Подключено к {host}:{port}"
                        self.list_remote_dir()
                    except ValueError:
                        self.status_message = "Неверный формат порта"
                else:
                    self.server_host = addr
                    self.status_message = f"Хост изменен на {addr}"
        finally:
            curses.noecho()
            curses.curs_set(0)


def main():
    if len(sys.argv) > 1:
        server_addr = sys.argv[1]
        if ':' in server_addr:
            host, port = server_addr.rsplit(':', 1)
            port = int(port)
        else:
            host = server_addr
            port = 5000
    else:
        host = '127.0.0.1'
        port = 5000
    
    client = UDPFileClient(host, port)
    
    print("=" * 60)
    print("UDP File Manager - Клиент в стиле Total Commander")
    print("=" * 60)
    print(f"Подключение к серверу: {host}:{port}")
    print("Нажмите Ctrl+C для выхода")
    print("=" * 60)
    
    try:
        curses.wrapper(client.run)
    except KeyboardInterrupt:
        print("\nВыход...")
    except Exception as e:
        print(f"\nОшибка: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
