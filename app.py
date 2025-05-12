# app.py (Cập nhật từ DES sang AES)
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, join_room, emit
# Thay đổi: Thay thế import DES bằng AES
from Crypto.Cipher import AES  # Thay đổi: Sử dụng AES thay vì DES
from Crypto.Util.Padding import pad, unpad
import base64
import os
import secrets
from io import BytesIO
import pandas as pd
from datetime import datetime
import numpy as np
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")

# Thay đổi: Thay đổi kích thước IV từ 8 bytes (DES) sang 16 bytes (AES)
IV = os.urandom(16)  # Thay đổi: Sử dụng IV 16 bytes cho AES thay vì 8 bytes cho DES, và tạo ngẫu nhiên
print('IV: ', IV)
# Đảm bảo thư mục logs tồn tại
os.makedirs('logs', exist_ok=True)

# Thay đổi: Cập nhật hàm mã hóa để sử dụng AES thay vì DES
def aes_encrypt(data, key):
    # Thay đổi: AES yêu cầu key độ dài 16, 24 hoặc 32 bytes (AES-128, AES-192, AES-256)
    key = pad_key(key)  # Đảm bảo key đủ 16 bytes
    print('Key sau khi padding:', key)
    
    cipher = AES.new(key, AES.MODE_CBC, IV)
    print('Cipher object:', cipher)
    
    padded_data = pad(data, AES.block_size)  # Thay đổi: AES block size là 16 bytes
    print('Data sau khi padding:', padded_data)
    
    print('Block size:', AES.block_size)
    
    encrypted_data = cipher.encrypt(padded_data)
    print('Data sau khi mã hóa:', encrypted_data)
    
    return encrypted_data   

# Thay đổi: Cập nhật hàm giải mã để sử dụng AES thay vì DES
def aes_decrypt(ciphertext, key):
    key = pad_key(key)
    cipher = AES.new(key, AES.MODE_CBC, IV)
    decrypted = cipher.decrypt(ciphertext)
    return unpad(decrypted, AES.block_size)  # Thay đổi: AES block size là 16 bytes

# Thay đổi: Thêm hàm mới để điều chỉnh key cho AES
def pad_key(key):
    # Thay đổi: Đảm bảo key đủ 16 bytes cho AES-128
    if len(key) > 16:
        return key[:16]  # Nếu key dài hơn, cắt bớt
    else:
        return key.ljust(16, b'\0')  # Nếu key ngắn hơn, thêm đệm

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/decrypt', methods=['POST'])
def decrypt():
    try:
        data = request.json
        key = data['key'].encode()
        # Thay đổi: Sử dụng aes_decrypt thay vì des_decrypt
        decrypted = aes_decrypt(base64.b64decode(data['ciphertext']), key)
        return jsonify({'plaintext': decrypted.decode()})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@socketio.on('join')
def handle_join(data):
    room_id = data['room_id']
    username = data.get('username', 'Unknown')
    join_room(room_id)
    
    # Thông báo cho các thành viên khác trong phòng
    emit('new_message', {
        'sender': 'System',
        'ciphertext': f'Người dùng {username} đã tham gia phòng chat.'
    }, room=room_id)

def log_to_excel(room, sender, message, key=None, ciphertext=None, file_name=None):
    try:
        log_file = os.path.join('logs', 'messages.xlsx')
        log_entry = {
            'Thời gian': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'Tên phòng': room,
            'Tên người dùng': sender,
            'Loại': 'Tin nhắn' if message else 'File',
            'Nội dung tin nhắn': message if message else f'File: {file_name}',
            'Mã khóa': key if key else 'N/A',
            'Mã hóa (Base64)': ciphertext if ciphertext else 'N/A'
        }

        # Nếu file đã tồn tại, load và thêm vào cuối
        if os.path.exists(log_file):
            df = pd.read_excel(log_file)
            df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
        else:
            df = pd.DataFrame([log_entry])

        df.to_excel(log_file, index=False)
    except Exception as e:
        print(f"Error logging to Excel: {e}")

@socketio.on('send_message')
def handle_message(data):
    try:
        room = data['room_id']
        sender = data['sender']
        message = data['message']
        key = data['key']
    
        # Thay đổi: Sử dụng aes_encrypt thay vì des_encrypt
        encrypted = aes_encrypt(message.encode(), key.encode())
        b64_cipher = base64.b64encode(encrypted).decode()

        # Emit cho người dùng trong phòng
        socketio.emit('new_message', {
            'ciphertext': b64_cipher,
            'sender': sender
        }, room=room)

        # Ghi log vào Excel
        log_to_excel(room, sender, message, key, b64_cipher)

    except Exception as e:
        print(f"Encryption error: {str(e)}")

# Xử lý metadata của file
@socketio.on('file_metadata')
def handle_file_metadata(data):
    try:
        room_id = data['room_id']
        sender = data['sender']
        file_id = data['fileId']
        file_name = data['fileName']
        
        # Gửi metadata cho tất cả người trong phòng
        emit('file_complete', {
            'fileId': file_id,
            'sender': sender,
            'fileName': file_name,
            'fileType': data['fileType'],
            'totalChunks': data['totalChunks'],
            'fileSize': data['fileSize']
        }, room=room_id)
        
        # Ghi log về việc gửi file
        log_to_excel(room_id, sender, None, file_name=file_name)
        
    except Exception as e:
        print(f"File metadata error: {str(e)}")

# Xử lý từng chunk của file
@socketio.on('file_chunk')
def handle_file_chunk(data):
    try:
        room_id = data['room_id']
        
        # Chuyển tiếp chunk đến tất cả các thành viên trong phòng
        emit('file_chunk', {
            'fileId': data['fileId'],
            'chunkIndex': data['chunkIndex'],
            'chunk': data['chunk'],
            'isLast': data.get('isLast', False)
        }, room=room_id)
        
    except Exception as e:
        print(f"File chunk error: {str(e)}")

# Thêm API endpoint cho mã hóa dữ liệu
@app.route('/encrypt_data', methods=['POST'])
def encrypt_data():
    try:
        data = request.json
        key = data['key']
        input_data = bytes(data['data'])
        
        # Thay đổi: Sử dụng aes_encrypt thay vì des_encrypt
        encrypted = aes_encrypt(input_data, key.encode())
        
        # Trả về mảng byte đã mã hóa
        return jsonify({
            'encrypted': list(encrypted)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Thêm API endpoint cho giải mã dữ liệu
@app.route('/decrypt_data', methods=['POST'])
def decrypt_data():
    try:
        data = request.json
        key = data['key']
        encrypted_data = bytes(data['data'])
        
        # Thay đổi: Sử dụng aes_decrypt thay vì des_decrypt
        decrypted = aes_decrypt(encrypted_data, key.encode())
        
        # Trả về mảng byte đã giải mã
        return jsonify({
            'decrypted': list(decrypted)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    os.makedirs('logs', exist_ok=True)
    socketio.run(app, port=5000, debug=True)