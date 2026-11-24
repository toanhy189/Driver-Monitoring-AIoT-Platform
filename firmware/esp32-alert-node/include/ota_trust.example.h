#pragma once
// Configure with backend/scripts/ota_firmware.py configure-device. Public material only.
// Empty trust disables OTA without affecting existing LED/buzzer/motor commands.
constexpr char OTA_PUBLIC_KEY_PEM[] = "";
constexpr char OTA_TRUSTED_ORIGIN[] = "";
constexpr char OTA_TLS_CA[] = "";
