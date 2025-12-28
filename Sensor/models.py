# sensor/models.py
from django.db import models

class Sensor(models.Model):
    SENSOR_TEMP = 'temp'
    SENSOR_HUM  = 'hum'
    SENSOR_LIGHT = 'light'
    SENSOR_CHOICES = [
        (SENSOR_TEMP, '温度'),
        (SENSOR_HUM, '湿度'),
        (SENSOR_LIGHT, '光照'),
    ]

    # 设备/通道的 ID 字节（十进制保存，31/32/33）
    id_code = models.PositiveSmallIntegerField(db_index=True, unique=True)
    kind = models.CharField(max_length=10, choices=SENSOR_CHOICES, db_index=True)
    name = models.CharField(max_length=50, default='', blank=True)
    unit = models.CharField(max_length=10, default='', blank=True)
    latest_value = models.FloatField(null=True, blank=True)
    latest_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_kind_display()}(id=0x{self.id_code:02X})"


class Reading(models.Model):
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name='readings')
    value = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']  # 最新在前
        indexes = [
            models.Index(fields=['sensor', 'created_at']),
        ]

    def __str__(self):
        return f"{self.sensor}={self.value} @ {self.created_at}"
