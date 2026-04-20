#!/usr/bin/env python3
"""
UDP File Manager Server
Серверная часть файлового менеджера с интерфейсом в стиле Total Commander
"""

import socket
import os
import json
import struct
from pathlib import Path
from datetime import datetime

class UDPFileServer:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.socket = None
        self.clients = {}
        
    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        print(f"UDP File Server запущен на {self.host}:{self.port}")
        
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
                self.handle_request(data, addr)
            except KeyboardInterrupt:
                print("\nОстановка сервера...")
                break
            except Exception as e:
                print(f"Ошибка: {e}")
    
    def handle_request(self, data, addr):
        try:
            request = json.loads(data.decode('utf-8'))
            command = request.get('command')
            
            if command == 'list_dir':
                response = self.list_directory(request.get('path', '.'))
            elif command == 'get_drives':
                response = self.get_drives()
            elif command == 'get_file':
                response = self.get_file(request.get('path'), addr)
                self.send_response(response, addr)
                return
            elif command == 'put_file':
                response = self.put_file(request, addr)
            elif command == 'delete':
                response = self.delete_item(request.get('path'))
            elif command == 'mkdir':
                response = self.create_directory(request.get('path'))
            elif command == 'rename':
                response = self.rename_item(request.get('old_path'), request.get('new_path'))
            elif command == 'get_info':
                response = self.get_file_info(request.get('path'))
            else:
                response = {'status': 'error', 'message': 'Неизвестная команда'}
            
            self.send_response(response, addr)
        except json.JSONDecodeError:
            response = {'status': 'error', 'message': 'Неверный формат JSON'}
            self.send_response(response, addr)
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}
            self.send_response(response, addr)
    
    def list_directory(self, path):
        try:
            path = Path(path).resolve()
            if not path.exists():
                return {'status': 'error', 'message': 'Путь не существует'}
            
            items = []
            # Добавляем родительскую директорию
            if path.parent != path:
                items.append({
                    'name': '..',
                    'type': 'dir',
                    'size': 0,
                    'modified': datetime.fromtimestamp(path.parent.stat().st_mtime).isoformat()
                })
            
            for item in path.iterdir():
                try:
                    stat = item.stat()
                    items.append({
                        'name': item.name,
                        'type': 'dir' if item.is_dir() else 'file',
                        'size': stat.st_size if item.is_file() else 0,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except PermissionError:
                    items.append({
                        'name': item.name,
                        'type': 'error',
                        'size': 0,
                        'modified': ''
                    })
            
            return {
                'status': 'ok',
                'path': str(path),
                'items': items
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_file(self, path, addr):
        try:
            path = Path(path).resolve()
            if not path.exists() or not path.is_file():
                return {'status': 'error', 'message': 'Файл не найден'}
            
            # Отправляем метаданные файла
            metadata = {
                'status': 'ok',
                'filename': path.name,
                'size': path.stat().st_size,
                'type': 'file_data'
            }
            self.send_response(metadata, addr)
            
            # Отправляем содержимое файла частями
            chunk_size = 1400  # Размер чанка для UDP
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    # Кодируем бинарные данные в base64 для безопасной передачи
                    import base64
                    chunk_data = {
                        'status': 'ok',
                        'type': 'chunk',
                        'data': base64.b64encode(chunk).decode('ascii')
                    }
                    self.send_response(chunk_data, addr)
            
            # Сигнал окончания передачи
            self.send_response({'status': 'ok', 'type': 'end'}, addr)
            return None
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def put_file(self, request, addr):
        try:
            import base64
            path = Path(request['path']).resolve()
            data = base64.b64decode(request['data'])
            is_last = request.get('last', False)
            
            mode = 'wb' if not hasattr(self, '_current_file') or self._current_file != path else 'ab'
            self._current_file = path
            
            with open(path, mode) as f:
                f.write(data)
            
            if is_last:
                self._current_file = None
            
            return {'status': 'ok', 'message': 'Файл получен'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def delete_item(self, path):
        try:
            path = Path(path).resolve()
            if not path.exists():
                return {'status': 'error', 'message': 'Путь не существует'}
            
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
            
            return {'status': 'ok', 'message': 'Удалено успешно'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def create_directory(self, path):
        try:
            path = Path(path).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return {'status': 'ok', 'message': 'Директория создана'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def rename_item(self, old_path, new_path):
        try:
            old_path = Path(old_path).resolve()
            new_path = Path(new_path).resolve()
            old_path.rename(new_path)
            return {'status': 'ok', 'message': 'Переименовано успешно'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_file_info(self, path):
        try:
            path = Path(path).resolve()
            if not path.exists():
                return {'status': 'error', 'message': 'Путь не существует'}
            
            stat = path.stat()
            return {
                'status': 'ok',
                'name': path.name,
                'type': 'dir' if path.is_dir() else 'file',
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'permissions': oct(stat.st_mode)[-3:]
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_drives(self):
        """Получение списка доступных дисков/разделов"""
        try:
            import os
            drives = []
            
            # Для Windows - список букв дисков
            if os.name == 'nt':
                import string
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if os.path.exists(drive):
                        drives.append(drive)
            else:
                # Для Linux/Unix - монтированные разделы
                try:
                    with open('/proc/mounts', 'r') as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2:
                                mount_point = parts[1]
                                if mount_point.startswith('/') and os.path.isdir(mount_point):
                                    drives.append(mount_point)
                except:
                    # Fallback для Unix
                    drives = ['/', '/home', '/mnt', '/media']
            
            return {
                'status': 'ok',
                'drives': drives
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def send_response(self, response, addr):
        if response is None:
            return
        data = json.dumps(response).encode('utf-8')
        # Разбиваем большие ответы на части
        if len(data) > 1400:
            chunks = [data[i:i+1400] for i in range(0, len(data), 1400)]
            for i, chunk in enumerate(chunks):
                is_last = i == len(chunks) - 1
                chunk_response = {
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'is_last': is_last,
                    'data': chunk.decode('latin-1')
                }
                self.socket.sendto(json.dumps(chunk_response).encode('utf-8'), addr)
        else:
            self.socket.sendto(data, addr)


if __name__ == '__main__':
    server = UDPFileServer()
    server.start()
