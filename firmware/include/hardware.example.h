#pragma once

// Copy to config.local.h only when the physical wiring differs.
// Use actual ESP32 GPIO numbers, not the Grove connector labels.
#define SMART_CLASSROOM_UNO_SDA 11
#define SMART_CLASSROOM_UNO_SCL 12
#define SMART_CLASSROOM_UNO_LIGHT 1
#define SMART_CLASSROOM_UNO_PIR 10
#define SMART_CLASSROOM_UNO_TRIG 6
#define SMART_CLASSROOM_UNO_ECHO 7
#define SMART_CLASSROOM_UNO_SERVO 5
#define SMART_CLASSROOM_UNO_LED 48
#define SMART_CLASSROOM_UNO_RGB 45
#define SMART_CLASSROOM_LED_ACTIVE_HIGH 1
#define SMART_CLASSROOM_LCD_ADDRESS 0x21
#define SMART_CLASSROOM_PIR_ACTIVE_HIGH 1
#define SMART_CLASSROOM_PIR_WARMUP_MS 30000

// 0 selects CoreIOT ownership. Calibrate before selecting a local mode.
// +1 means smaller ADC readings are darker. -1 means larger readings are darker.
#define SMART_CLASSROOM_LIGHT_POLARITY 0
#define SMART_CLASSROOM_LIGHT_DARK_THRESHOLD 1000
#define SMART_CLASSROOM_LIGHT_BRIGHT_THRESHOLD 1200
