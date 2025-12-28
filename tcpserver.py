import socket
import threading
import datetime
import requests
import logging

# ===================== 配置 =====================
HOST = ''          # 监听所有网卡
PORT = 7777
LIST = 5
BUFFSIZE = 1024
SOCK_TIMEOUT = 1000  # 秒
HTTP_TIMEOUT = 5     # 秒

# Django 写入接口（改成你的服务地址）
DJANGO_INGEST_URL = 'http://192.168.1.127:8000/sensor/ingest/'

# 设备回写协议（保持你的原有格式）
SUCCESS = 'code=0000'
FAILURE = 'code=0001'

# 是否把“数据位的 ASCII 字符串”（如 "4" / "57" / "123"）也回给设备
ECHO_VALUE = True
# =================================================

# 帧协议常量：66 [ID] [35/36/37] [ASCII数字...] BB
START = 0x66
END   = 0xBB
MARKER_TO_DIGITS = {0x35: 1, 0x36: 2, 0x37: 3}

def extract_frames(buffer: bytearray):
    """
    从 buffer 里提取 0~N 个完整帧：
    [0x66][ID][0x35/36/37][ASCII DIGITS...][0xBB]
    返回 list[dict]，并在原地裁剪 buffer（已消费的字节被丢弃）
    """
    frames = []
    i = 0
    n = len(buffer)
    while True:
        # 找起始
        while i < n and buffer[i] != START:
            i += 1
        if i >= n:
            del buffer[:]
            break

        # 最小帧长度=5
        if n - i < 5:
            if i > 0:
                del buffer[:i]
            break

        id_byte = buffer[i+1]
        marker  = buffer[i+2]
        digits  = MARKER_TO_DIGITS.get(marker)
        if not digits:
            i += 1
            continue

        frame_len = 1 + 1 + 1 + digits + 1
        if n - i < frame_len:
            if i > 0:
                del buffer[:i]
            break

        data_bytes = buffer[i+3:i+3+digits]
        end_byte   = buffer[i+3+digits]
        if end_byte != END:
            i += 1
            continue

        # 数据位必须是 '0'..'9'
        if not all(0x30 <= b <= 0x39 for b in data_bytes):
            i += 1
            continue

        value_str = bytes(data_bytes).decode('ascii')   # 如 "4" / "57" / "123"
        value_int = int(value_str)

        frames.append({
            'id': id_byte,
            'digits': digits,
            'value_str': value_str,
            'value_int': value_int,
            'raw_hex': buffer[i:i+frame_len].hex()
        })

        i += frame_len
        n = len(buffer)
        if i >= n:
            del buffer[:]
            break

    if i > 0 and len(buffer) > 0:
        del buffer[:i]
    return frames


def upload_reading_to_django(id_byte: int, value_int: int):
    """
    上传到 Django /sensor/ingest/ 接口。
    采用 JSON: {"id":"0x31","value":26}
    成功返回 (True, response_text)；失败返回 (False, error_text)
    """
    payload = {"id": f"0x{id_byte:02X}", "value": value_int}
    try:
        r = requests.post(DJANGO_INGEST_URL, json=payload, timeout=HTTP_TIMEOUT)
        text = r.text
        if r.status_code == 200:
            try:
                js = r.json()
                ok = bool(js.get('ok', 0))
            except Exception:
                ok = False
            return ok, text
        else:
            return False, text
    except requests.RequestException as e:
        return False, f"http_error={e.__class__.__name__}: {e}"


def handle(client: socket.socket, address):
    device_ip = address[0]
    device_id_str = ""  # 可记录为 "0x33" 等
    client.settimeout(SOCK_TIMEOUT)

    recv_buf = bytearray()

    while True:
        try:
            chunk = client.recv(BUFFSIZE)
            if not chunk:
                print("connection lost:", device_ip)
                break

            # 打印原始十六进制（排查）
            logging.debug(f"RAW HEX from {device_ip}: {chunk.hex()}")
            recv_buf.extend(chunk)

            # 尽可能多地抠帧
            frames = extract_frames(recv_buf)
            if not frames:
                continue

            for fr in frames:
                id_byte   = fr['id']            # 0x31/0x32/0x33
                value_str = fr['value_str']     # "4"/"57"/"123"
                value_int = fr['value_int']     # 4/57/123
                raw_hex   = fr['raw_hex']       # 原始帧 hex

                device_id_str = f"0x{id_byte:02X}"  # 记录一下

                print(f"parsed frame from {device_ip}: HEX={raw_hex}  ID={device_id_str}  value_str='{value_str}'  value_int={value_int}")

                # === 上传到 Django ===
                ok, res_text = upload_reading_to_django(id_byte, value_int)

                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ")
                print(now, 'Upload:', {'id': device_id_str, 'value': value_int}, '>>>', res_text)

                # === 回写给设备 ===
                try:
                    client.send((SUCCESS if ok else FAILURE).encode('utf-8'))
                except Exception as e:
                    logging.error(f"send result error to {device_ip}: {e}")

                if ECHO_VALUE:
                    try:
                        # 把数据位 ASCII 原样回显，例如 b'57'
                        client.send(value_str.encode('ascii'))
                    except Exception as e:
                        logging.error(f"send value_str back error to {device_ip}: {e}")

        except socket.timeout:
            print("Heartbeat time out:", device_ip)
            break
        except ConnectionResetError:
            print("Peer reset:", device_ip)
            break
        except Exception as e:
            logging.exception(f"Unexpected error with {device_ip}: {e}")
            break

    print("Client close:", device_id_str, ":", device_ip)
    logging.warning("Client close:" + device_id_str + ":" + device_ip)
    try:
        client.close()
    except Exception:
        pass


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        filename='device.log',
        filemode='a',
        format='%(asctime)s - %(levelname)s: %(message)s'
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(LIST)
    print(PORT)

    while True:
        client, address = sock.accept()
        print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S "), 'New door_controller connection from', address)
        logging.warning('New door_controller connection from ' + address[0])
        thread = threading.Thread(target=handle, args=(client, address), daemon=True)
        thread.start()


if __name__ == '__main__':
    main()
