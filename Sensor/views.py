# sensor/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Sensor, Reading
from .parser import parse_one_frame, bytes_from_hex_string

ID_KIND_MAP = {
    0x31: Sensor.SENSOR_TEMP,
    0x32: Sensor.SENSOR_HUM,
    0x33: Sensor.SENSOR_LIGHT,
}

@csrf_exempt
def ingest(request):
    """
    数据写入接口（POST）
    支持三种格式（任选其一）：
    A) JSON: {"id": "0x31", "value": 26}
    B) JSON: {"id_ascii": "1", "value": 26}
    C) JSON: {"raw_hex": "66 31 36 32 36 bb"}  # 自动按协议解析
    返回：{"ok":1, "sensor":"temp", "id_code":49, "value":26, "unit":"℃"}
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        # 兼容 form/data
        payload = request.POST.dict()

    id_code = None
    value = None

    # C) raw_hex 优先解析
    raw_hex = payload.get('raw_hex')
    if raw_hex:
        try:
            frame = bytes_from_hex_string(raw_hex)
            parsed = parse_one_frame(frame)
            if not parsed:
                return HttpResponseBadRequest('raw_hex parse failed')
            id_code = parsed['id_code']
            value = parsed['value_int']
        except Exception as e:
            return HttpResponseBadRequest(f'raw_hex error: {e}')

    # A) id + value
    if id_code is None and 'id' in payload and 'value' in payload:
        v = str(payload['id']).strip().lower()
        try:
            id_code = int(v, 16) if v.startswith('0x') else int(v)
        except Exception:
            return HttpResponseBadRequest('bad id')
        value = float(payload['value'])

    # B) id_ascii + value（'1'->0x31，'2'->0x32，'3'->0x33）
    if id_code is None and 'id_ascii' in payload and 'value' in payload:
        s = str(payload['id_ascii'])
        if len(s) != 1 or not s.isdigit():
            return HttpResponseBadRequest('bad id_ascii')
        id_code = ord(s)  # '1'->49(0x31)
        value = float(payload['value'])

    if id_code is None or value is None:
        return HttpResponseBadRequest('need id/value or raw_hex')

    # 映射到 kind
    kind = ID_KIND_MAP.get(id_code)
    if not kind:
        return HttpResponseBadRequest(f'unknown id_code: 0x{id_code:02X}')

    # 取/建 Sensor
    sensor, _ = Sensor.objects.get_or_create(
        id_code=id_code,
        defaults={'kind': kind, 'name': '', 'unit': '℃' if kind=='temp' else '%' if kind=='hum' else 'lx'}
    )

    # 写 Reading
    reading = Reading.objects.create(sensor=sensor, value=float(value))
    # 更新最新值
    sensor.latest_value = reading.value
    sensor.latest_at = timezone.now()
    sensor.save(update_fields=['latest_value', 'latest_at'])

    return JsonResponse({
        'ok': 1,
        'sensor': sensor.kind,
        'id_code': sensor.id_code,
        'value': reading.value,
        'unit': sensor.unit,
        'ts': reading.created_at.isoformat(),
    })


def series(request):
    """
    历史数据接口（GET）
    参数：
      - sensor: temp/hum/light（三选一）或 id_code=49/50/51（二选一传其中一种）
      - limit: 返回点数（默认 200，最大 5000）
      - start/end: ISO 时间范围（可选）
    返回：
      { "ok":1, "name":"温度传感器", "unit":"℃",
        "data":[["2025-10-12T21:01:02", 26.3], ...] }
    """
    sensor_kind = request.GET.get('sensor')
    id_code = request.GET.get('id_code')

    sensor = None
    if id_code:
        try:
            v = int(id_code)
        except Exception:
            return HttpResponseBadRequest('bad id_code')
        sensor = Sensor.objects.filter(id_code=v).first()
    elif sensor_kind:
        sensor = Sensor.objects.filter(kind=sensor_kind).first()

    if not sensor:
        return HttpResponseBadRequest('sensor not found')

    limit = min(int(request.GET.get('limit', 200)), 5000)

    qs = sensor.readings.all().order_by('-created_at')
    start = request.GET.get('start')
    end = request.GET.get('end')
    if start:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(start)
        if dt:
            qs = qs.filter(created_at__gte=dt)
    if end:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(end)
        if dt:
            qs = qs.filter(created_at__lte=dt)

    rows = list(qs.values('created_at', 'value')[:limit])
    rows.reverse()  # ECharts 通常时间正序更直观

    data = [[r['created_at'].isoformat(), float(r['value'])] for r in rows]

    return JsonResponse({
        'ok': 1,
        'name': sensor.name or sensor.get_kind_display(),
        'unit': sensor.unit,
        'data': data,
    })
