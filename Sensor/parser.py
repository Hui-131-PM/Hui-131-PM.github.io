# sensor/parser.py
START = 0x66
END   = 0xBB
MARKER_TO_DIGITS = {0x35: 1, 0x36: 2, 0x37: 3}

def parse_one_frame(raw_bytes: bytes):
    """
    尝试按 [66][ID][35/36/37][ASCII数字...][BB] 解析一帧。
    成功返回 dict: {'id_code': int, 'value_int': int, 'value_str': str}
    失败返回 None
    """
    b = raw_bytes
    if len(b) < 5 or b[0] != START or b[-1] != END:
        return None
    id_code = b[1]
    marker = b[2]
    digits = MARKER_TO_DIGITS.get(marker)
    if not digits:
        return None
    if len(b) != 1 + 1 + 1 + digits + 1:
        return None
    data_bytes = b[3:3+digits]
    if not all(0x30 <= x <= 0x39 for x in data_bytes):
        return None
    value_str = bytes(data_bytes).decode('ascii')
    value_int = int(value_str)
    return {'id_code': id_code, 'value_int': value_int, 'value_str': value_str}


def bytes_from_hex_string(hex_str: str) -> bytes:
    """
    接受 '66313533bb' 或 '66 31 35 33 BB' 这种，转 bytes
    """
    s = hex_str.replace(' ', '').lower()
    return bytes.fromhex(s)
