#pragma once
#include <ArduinoJson.h>
void otaBegin();
void otaLoop();
void otaOnMessage(JsonDocument& doc);
void otaCapabilities(JsonObject output);
bool otaBlocksCommands();
