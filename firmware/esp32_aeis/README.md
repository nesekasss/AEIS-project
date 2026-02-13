# AEIS ESP32 Firmware (JSON Lines)

Serial: 115200 baud  
Output: JSON Lines (1 JSON object per line)

Commands (send via Serial):
- {"type":"cmd","cmd":"fan_set","value":1}
- {"type":"cmd","cmd":"fan_set","value":0}
- {"type":"cmd","cmd":"json_only","value":1}
- {"type":"cmd","cmd":"json_only","value":0}

Pins:
- MQ2: GPIO 34
- DHT22: GPIO 27
- LDR: GPIO 35
- HC-SR04: TRIG 5, ECHO 18
- MPU6050: I2C addr 0x68
- LEDs: 16/17/19
- FAN_PIN: mapped to LED_RED by default
