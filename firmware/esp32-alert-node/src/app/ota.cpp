// OTA touches only the inactive application slot. Never update bootloader, eFuse or NVS layout over OTA.
#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <mbedtls/pk.h>
#include <mbedtls/sha256.h>
#include <mbedtls/base64.h>
#include <time.h>
#include "config.h"
#include "mqtt_client.h"
#include "command_handler.h"
#include "ota.h"
#if __has_include("ota_trust.h")
#include "ota_trust.h"
#else
#include "ota_trust.example.h"
#endif

// Arduino normally confirms a candidate before setup(). Defer until our real self-test.
extern "C" bool verifyRollbackLater() { return true; }

static Preferences store;
static JsonDocument record;
static String pendingRequest, lastReport;
static bool queued=false, downloading=false, candidate=false, trusted=false;
static char keyHash[65]={0}, imageHash[65]={0};
static unsigned long bootAt=0, reportAt=0;

static String hex(const uint8_t* bytes,size_t count) {
    String result;result.reserve(count*2);
    const char* digits="0123456789abcdef";
    for(size_t i=0;i<count;i++){result+=digits[bytes[i]>>4];result+=digits[bytes[i]&15];}
    return result;
}
static bool hexDigest(const char* value) {
    if(!value || strlen(value)!=64)return false;
    for(int i=0;i<64;i++)if(!isxdigit(value[i]) || (value[i]>='A'&&value[i]<='F'))return false;
    return true;
}
static void currentDigest() {
    uint8_t hash[32];
    if(esp_partition_get_sha256(esp_ota_get_running_partition(),hash)==ESP_OK)
        strlcpy(imageHash,hex(hash,32).c_str(),sizeof(imageHash));
    else memset(imageHash,'0',64);
}
static bool save() {
    String encoded;serializeJson(record,encoded);return store.putString("job",encoded)==encoded.length();
}
static void publishReport() {
    if(lastReport.length() && mqtt.connected()) {
        String topic=String("driver/")+DEVICE_CODE+"/ota/status";
        mqtt.publish(topic.c_str(),lastReport.c_str(),false);
        reportAt=millis();
    }
}
static void report(const char* state,const char* error=nullptr,uint32_t received=0) {
    if(!record["job_id"].is<unsigned int>())return;
    record["sequence"]=record["sequence"].as<unsigned int>()+1;
    record["stage"]=state;
    record["bytes_received"]=received;
    record["error"]=error ? error : "";
    save();
    JsonDocument doc;
    doc["protocol"]="driver-ota-v1";doc["device_code"]=DEVICE_CODE;
    doc["job_id"]=record["job_id"];doc["request_id"]=record["request_id"];
    doc["sequence"]=record["sequence"];doc["state"]=state;
    doc["bytes_received"]=received;doc["firmware_version"]=FIRMWARE_VERSION;
    doc["image_sha256"]=imageHash;
    if(strcmp(state,"CONFIRMED")==0)doc["download_sha256"]=record["sha256"];
    if(error)doc["error"]=error;
    lastReport="";serializeJson(doc,lastReport);
    // Persist the exact event for deduplicated replay after network loss/reboot.
    store.putString("report",lastReport);
    publishReport();
}
static void reject(JsonDocument& request,const char* error) {
    JsonDocument doc;
    doc["protocol"]="driver-ota-v1";doc["device_code"]=DEVICE_CODE;
    doc["job_id"]=request["job_id"];doc["request_id"]=request["request_id"];
    doc["sequence"]=0;doc["state"]="REJECTED";doc["error"]=error;
    char output[512];serializeJson(doc,output,sizeof(output));
    String topic=String("driver/")+DEVICE_CODE+"/ota/status";
    mqtt.publish(topic.c_str(),output,false);
}
static bool verifyManifest(JsonObject manifest) {
    const char* version=manifest["version"] | "";
    const char* hardware=manifest["hardware_version"] | "";
    const char* hash=manifest["sha256"] | "";
    const char* signature=manifest["signature"] | "";
    if(strcmp(manifest["format"] | "","driver-ota-v1") || strcmp(manifest["key_id"] | "","ota-key-v1") ||
       strcmp(hardware,HARDWARE_VERSION) || !hexDigest(hash) || !strlen(version) || strlen(version)>40)return false;
    for(size_t i=0;i<strlen(version);i++)if(!isalnum(version[i])&&version[i]!='.'&&version[i]!='_'&&version[i]!='-')return false;
    String content=String("driver-ota-v1\nota-key-v1\n")+version+"\n"+hardware+"\n"+
        String(manifest["size_bytes"].as<unsigned int>())+"\n"+hash+"\n";
    uint8_t digest[32], decoded[256];size_t length=0;
    mbedtls_sha256_ret((const unsigned char*)content.c_str(),content.length(),digest,0);
    if(mbedtls_base64_decode(decoded,sizeof(decoded),&length,(const unsigned char*)signature,strlen(signature)) || length!=256)return false;
    mbedtls_pk_context key;mbedtls_pk_init(&key);
    bool valid=mbedtls_pk_parse_public_key(&key,(const unsigned char*)OTA_PUBLIC_KEY_PEM,strlen(OTA_PUBLIC_KEY_PEM)+1)==0 &&
        mbedtls_pk_verify(&key,MBEDTLS_MD_SHA256,digest,sizeof(digest),decoded,length)==0;
    mbedtls_pk_free(&key);return valid;
}

bool otaBlocksCommands(){return queued||downloading||candidate;}

void otaCapabilities(JsonObject output) {
    const esp_partition_t* slot=esp_ota_get_next_update_partition(nullptr);
    output["protocol"]="driver-ota-v1";
#ifdef CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE
    output["rollback_supported"]=true;
    output["supported"]=trusted && slot!=nullptr;
#else
    output["rollback_supported"]=false;output["supported"]=false;
#endif
    output["max_image_bytes"]=slot ? slot->size : 0;
    output["signature_required"]=true;output["key_sha256"]=keyHash;
    output["image_sha256"]=imageHash;output["outputs_busy"]=deviceOutputsBusy()||otaBlocksCommands();
}

void otaBegin() {
    bootAt=millis();store.begin("driver-ota",false);
    deserializeJson(record,store.getString("job","{}"));
    lastReport=store.getString("report","");
    currentDigest();memset(keyHash,'0',64);
    mbedtls_pk_context key;mbedtls_pk_init(&key);
    if(strlen(OTA_PUBLIC_KEY_PEM)>100 && strncmp(OTA_TRUSTED_ORIGIN,"https://",8)==0 && strlen(OTA_TLS_CA)>100 &&
        mbedtls_pk_parse_public_key(&key,(const unsigned char*)OTA_PUBLIC_KEY_PEM,strlen(OTA_PUBLIC_KEY_PEM)+1)==0) {
        unsigned char der[512];int length=mbedtls_pk_write_pubkey_der(&key,der,sizeof(der));
        if(length>0){uint8_t digest[32];mbedtls_sha256_ret(der+sizeof(der)-length,length,digest,0);
            strlcpy(keyHash,hex(digest,32).c_str(),sizeof(keyHash));trusted=true;}
    }
    mbedtls_pk_free(&key);
    esp_ota_img_states_t state;
    if(esp_ota_get_state_partition(esp_ota_get_running_partition(),&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY)
        candidate=true;
    const char* stage=record["stage"] | "";
    if(!candidate && (!strcmp(stage,"REBOOTING")||!strcmp(stage,"ROLLBACK_PENDING"))) {
        if(esp_ota_get_running_partition()->address==record["previous_address"].as<uint32_t>() &&
            !strcmp(imageHash,record["previous_sha256"] | ""))report("ROLLED_BACK","NEW_IMAGE_NOT_CONFIRMED");
        else report("FAILED","UNEXPECTED_BOOT_IMAGE");
    } else if(!candidate && (!strcmp(stage,"ACCEPTED")||!strcmp(stage,"DOWNLOADING")||!strcmp(stage,"VERIFYING")))
        report("FAILED","UPDATE_INTERRUPTED_BEFORE_REBOOT");
    Serial.printf("[OTA] %s trust=%s pending_self_test=%s\n","driver-ota-capable-v1;bootloader-rollback;RSA2048-SHA256",
        trusted?"OK":"NOT_CONFIGURED",candidate?"YES":"NO");
}

void otaOnMessage(JsonDocument& request) {
    if(strcmp(request["protocol"] | "","driver-ota-v1") || strcmp(request["device_code"] | "",DEVICE_CODE) ||
       !request["job_id"].is<unsigned int>() || !request["request_id"].is<const char*>())return;
    if(!strcmp(request["request_id"] | "",record["request_id"] | "")) {
        if(request["job_id"].as<unsigned int>()==record["job_id"].as<unsigned int>() &&
            !strcmp(request["manifest"]["sha256"] | "",record["sha256"] | ""))publishReport();
        return;
    }
    if(otaBlocksCommands()||deviceOutputsBusy()){reject(request,"OUTPUTS_OR_OTA_BUSY");return;}
    if(!trusted){reject(request,"OTA_TRUST_NOT_CONFIGURED");return;}
    if(time(nullptr)<1704067200 || request["expires_at"].as<uint64_t>()<=(uint64_t)time(nullptr) ||
        request["expires_at"].as<uint64_t>()>(uint64_t)time(nullptr)+610){reject(request,"OTA_EXPIRED_OR_CLOCK_INVALID");return;}
    JsonObject manifest=request["manifest"].as<JsonObject>();
    const esp_partition_t* slot=esp_ota_get_next_update_partition(nullptr);
    unsigned int size=manifest["size_bytes"] | 0;
    String expected=String(OTA_TRUSTED_ORIGIN)+"/api/ota/device/jobs/"+String(request["job_id"].as<unsigned int>())+"/image";
    if(!slot || size<256 || size>slot->size || size>2097152 || !verifyManifest(manifest) ||
        expected!=String(request["url"] | "") || strlen(request["download_token"] | "")>600 ||
        strlen(request["request_id"] | "")>80){reject(request,"INVALID_SIGNED_FIRMWARE_OR_ORIGIN");return;}
    if(!strcmp(manifest["version"] | "",FIRMWARE_VERSION)){reject(request,"ALREADY_RUNNING_VERSION");return;}
    record.clear();record["job_id"]=request["job_id"];record["request_id"]=request["request_id"];
    record["sha256"]=manifest["sha256"];record["target_version"]=manifest["version"];
    record["size_bytes"]=size;record["previous_address"]=esp_ota_get_running_partition()->address;
    record["previous_sha256"]=imageHash;record["previous_version"]=FIRMWARE_VERSION;
    record["target_address"]=slot->address;record["sequence"]=0;
    if(!save()){record.clear();reject(request,"NVS_WRITE_FAILED");return;}
    pendingRequest="";serializeJson(request,pendingRequest);queued=true;report("ACCEPTED");
}

static void downloadImage() {
    queued=false;downloading=true;
    JsonDocument request;deserializeJson(request,pendingRequest);pendingRequest="";
    WiFiClientSecure connection;connection.setCACert(OTA_TLS_CA);connection.setTimeout(15000);
    HTTPClient http;http.setConnectTimeout(10000);http.setTimeout(15000);
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    if(!http.begin(connection,request["url"].as<String>())){report("FAILED","HTTP_BEGIN_FAILED");downloading=false;return;}
    http.addHeader("Authorization",String("Bearer ")+request["download_token"].as<String>());
    int code=http.GET();unsigned int size=record["size_bytes"].as<unsigned int>();
    if(code!=200 || http.getSize()!=(int)size){http.end();report("FAILED","HTTP_STATUS_OR_SIZE_INVALID");downloading=false;return;}
    const esp_partition_t* slot=esp_ota_get_next_update_partition(nullptr);
    esp_ota_handle_t handle;
    if(esp_ota_begin(slot,size,&handle)!=ESP_OK){http.end();report("FAILED","PARTITION_BEGIN_FAILED");downloading=false;return;}
    mbedtls_sha256_context hash;mbedtls_sha256_init(&hash);mbedtls_sha256_starts_ret(&hash,0);
    uint8_t buffer[2048];uint32_t received=0,lastPercent=0;unsigned long lastByte=millis();bool valid=true;
    report("DOWNLOADING");
    while(received<size) {
        mqtt.loop();
        int available=http.getStreamPtr()->available();
        if(available>0) {
            int count=http.getStreamPtr()->readBytes(buffer,min((uint32_t)sizeof(buffer),min((uint32_t)available,size-received)));
            if(count<=0 || esp_ota_write(handle,buffer,count)!=ESP_OK){valid=false;break;}
            mbedtls_sha256_update_ret(&hash,buffer,count);received+=count;lastByte=millis();
            uint32_t percent=received*100/size;
            if(percent>=lastPercent+10){lastPercent=percent;report("DOWNLOADING",nullptr,received);}
        } else if(millis()-lastByte>20000 || !http.connected()) {valid=false;break;}
        if((uint64_t)time(nullptr)>=request["expires_at"].as<uint64_t>()){valid=false;break;}
        delay(1);
    }
    uint8_t digest[32];mbedtls_sha256_finish_ret(&hash,digest);mbedtls_sha256_free(&hash);http.end();
    if(!valid || received!=size || hex(digest,32)!=String(record["sha256"] | "")) {
        esp_ota_abort(handle);report("FAILED","DOWNLOAD_OR_SHA256_FAILED",received);downloading=false;return;
    }
    report("VERIFYING",nullptr,received);
    if(esp_ota_end(handle)!=ESP_OK){report("FAILED","IMAGE_VALIDATION_FAILED",received);downloading=false;return;}
    uint8_t installed[32];
    if(esp_partition_get_sha256(slot,installed)!=ESP_OK){report("FAILED","FLASH_HASH_FAILED",received);downloading=false;return;}
    record["target_sha256"]=hex(installed,32);report("REBOOTING",nullptr,received);
    if(!save()){report("FAILED","NVS_WRITE_FAILED",received);downloading=false;return;}
    if(esp_ota_set_boot_partition(slot)!=ESP_OK){report("FAILED","SET_BOOT_PARTITION_FAILED",received);downloading=false;return;}
    for(int i=0;i<20;i++){mqtt.loop();delay(10);} // let the progress publish leave the socket
    ESP.restart();
}

void otaLoop() {
    if(candidate) {
        bool identity=!strcmp(record["target_version"] | "",FIRMWARE_VERSION) &&
            !strcmp(record["target_sha256"] | "",imageHash);
        bool healthy=identity && trusted && ESP.getFreeHeap()>20000 && !deviceOutputsBusy() && mqtt.connected() && time(nullptr)>1704067200;
#ifdef OTA_SELF_TEST_FORCE_FAIL
        healthy=false;
        if(millis()-bootAt>3000) {
#else
        if(millis()-bootAt>60000) {
#endif
            record["stage"]="ROLLBACK_PENDING";save();
            Serial.println("[OTA] self-test failed; rolling back");
            esp_ota_mark_app_invalid_rollback_and_reboot();
            ESP.restart();
        }
        if(healthy && millis()-bootAt>3000 && esp_ota_mark_app_valid_cancel_rollback()==ESP_OK) {
            candidate=false;report("CONFIRMED",nullptr,record["size_bytes"].as<unsigned int>());
            Serial.printf("[OTA] confirmed firmware=%s\n",FIRMWARE_VERSION);
        }
    }
    if(mqtt.connected() && millis()-reportAt>5000)publishReport();
    if(queued && mqtt.connected())downloadImage();
}
