// Cat water bowl camera: Seeed XIAO ESP32S3 Sense + Telegram.
// Send /photo to your own Telegram bot from anywhere and get a picture of the bowl back.
// No port forwarding, no VPN, no extra hardware: the board polls Telegram over HTTPS.
//
// Arduino IDE:  Board "XIAO_ESP32S3"  |  Tools > PSRAM: "OPI PSRAM"  |  USB CDC On Boot: Enabled
// Library Manager: install "ArduinoJson" by Benoit Blanchon (7.x).
// Copy secrets.h.example to secrets.h (same folder) and fill it in.
//
// Bot commands:  /photo (also /water /bowl /pic)   /status   /help

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "secrets.h"

// ---------------- settings you may want to change ----------------
static const framesize_t FRAME_SIZE   = FRAMESIZE_UXGA;  // 1600x1200 still. FRAMESIZE_HD (1280x720) if uploads are slow.
static const int         JPEG_QUALITY = 12;              // 0 (best) .. 63 (worst)
static const bool        VFLIP        = false;           // true if mounted upside down
static const bool        HMIRROR      = false;
static const bool        LOW_LIGHT    = true;            // raise sensor gain for a dim basement (grainier)
static const uint32_t    AUTO_PHOTO_MINUTES = 0;         // >0: also send a photo every N minutes without being asked
static const bool        VERIFY_TLS   = true;            // false = accept any certificate (only if Telegram changes its CA)
static const int         POLL_TIMEOUT_S = 20;            // how long each Telegram long-poll waits for a command
static const uint32_t    WIFI_RETRY_MS = 20000;          // reboot after this long without Wi-Fi
// ------------------------------------------------------------------

// XIAO ESP32S3 Sense camera wiring (OV2640 on the expansion board)
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13
#define LED_PIN        21   // onboard user LED, LOW = on

// Go Daddy Root Certificate Authority - G2: the root that signs api.telegram.org's certificate.
static const char TELEGRAM_ROOT_CA[] = R"PEM(-----BEGIN CERTIFICATE-----
MIIDxTCCAq2gAwIBAgIBADANBgkqhkiG9w0BAQsFADCBgzELMAkGA1UEBhMCVVMx
EDAOBgNVBAgTB0FyaXpvbmExEzARBgNVBAcTClNjb3R0c2RhbGUxGjAYBgNVBAoT
EUdvRGFkZHkuY29tLCBJbmMuMTEwLwYDVQQDEyhHbyBEYWRkeSBSb290IENlcnRp
ZmljYXRlIEF1dGhvcml0eSAtIEcyMB4XDTA5MDkwMTAwMDAwMFoXDTM3MTIzMTIz
NTk1OVowgYMxCzAJBgNVBAYTAlVTMRAwDgYDVQQIEwdBcml6b25hMRMwEQYDVQQH
EwpTY290dHNkYWxlMRowGAYDVQQKExFHb0RhZGR5LmNvbSwgSW5jLjExMC8GA1UE
AxMoR28gRGFkZHkgUm9vdCBDZXJ0aWZpY2F0ZSBBdXRob3JpdHkgLSBHMjCCASIw
DQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAL9xYgjx+lk09xvJGKP3gElY6SKD
E6bFIEMBO4Tx5oVJnyfq9oQbTqC023CYxzIBsQU+B07u9PpPL1kwIuerGVZr4oAH
/PMWdYA5UXvl+TW2dE6pjYIT5LY/qQOD+qK+ihVqf94Lw7YZFAXK6sOoBJQ7Rnwy
DfMAZiLIjWltNowRGLfTshxgtDj6AozO091GB94KPutdfMh8+7ArU6SSYmlRJQVh
GkSBjCypQ5Yj36w6gZoOKcUcqeldHraenjAKOc7xiID7S13MMuyFYkMlNAJWJwGR
tDtwKj9useiciAF9n9T521NtYJ2/LOdYq7hfRvzOxBsDPAnrSTFcaUaz4EcCAwEA
AaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAQYwHQYDVR0OBBYE
FDqahQcQZyi27/a9BUFuIMGU2g/eMA0GCSqGSIb3DQEBCwUAA4IBAQCZ21151fmX
WWcDYfF+OwYxdS2hII5PZYe096acvNjpL9DbWu7PdIxztDhC2gV7+AJ1uP2lsdeu
9tfeE8tTEH6KRtGX+rcuKxGrkLAngPnon1rpN5+r5N9ss4UXnT3ZJE95kTXWXwTr
gIOrmgIttRD02JDHBHNA7XIloKmf7J6raBKZV8aPEjoJpL1E/QYVN8Gb5DKj7Tjo
2GTzLH4U/ALqn83/B2gX2yKQOC16jdFU8WnjXzPKej17CuPKf1855eJ1usV2GDPO
LPAvTK33sefOT6jEm0pUBsV/fdUID+Ic/n4XuKxe9tQWskMJDE32p2u0mYRlynqI
4uJEvlz36hz1
-----END CERTIFICATE-----
)PEM";

static WiFiClientSecure tls;
static const String API = String("https://api.telegram.org/bot") + BOT_TOKEN + "/";
static long long lastUpdateId = 0;        // Telegram update offset
static uint32_t  lastAutoPhoto = 0;
static int       consecutiveFailures = 0;

static String ll2s(long long v) { char b[24]; snprintf(b, sizeof(b), "%lld", v); return String(b); }

// ---------------- camera ----------------
static bool startCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;  c.pin_d1 = Y3_GPIO_NUM;  c.pin_d2 = Y4_GPIO_NUM;  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;  c.pin_d5 = Y7_GPIO_NUM;  c.pin_d6 = Y8_GPIO_NUM;  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk  = XCLK_GPIO_NUM;  c.pin_pclk  = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href  = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn  = PWDN_GPIO_NUM;  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size   = FRAME_SIZE;
  c.jpeg_quality = JPEG_QUALITY;
  c.fb_count     = 2;
  c.fb_location  = CAMERA_FB_IN_PSRAM;
  c.grab_mode    = CAMERA_GRAB_LATEST;   // sensor keeps running, so auto-exposure is always settled

  if (!psramFound()) {
    Serial.println("PSRAM not found. In the Arduino IDE set Tools > PSRAM to \"OPI PSRAM\". Falling back to 800x600.");
    c.frame_size  = FRAMESIZE_SVGA;
    c.fb_count    = 1;
    c.fb_location = CAMERA_FB_IN_DRAM;
  }
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) { Serial.printf("Camera init failed: 0x%x\n", err); return false; }

  sensor_t* s = esp_camera_sensor_get();
  s->set_vflip(s, VFLIP);
  s->set_hmirror(s, HMIRROR);
  if (LOW_LIGHT) {
    s->set_gainceiling(s, GAINCEILING_128X);
    s->set_ae_level(s, 2);
    s->set_aec2(s, 1);
    s->set_lenc(s, 1);
  }
  return true;
}

static camera_fb_t* takePhoto() {
  // Drop two frames so the exposure reflects the scene right now, then keep the next one.
  for (int i = 0; i < 2; i++) { camera_fb_t* f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  return esp_camera_fb_get();
}

// ---------------- Telegram ----------------
static int tgGet(const String& url, String& out, uint16_t timeoutMs) {
  HTTPClient http;
  http.setConnectTimeout(10000);
  http.setTimeout(timeoutMs);
  if (!http.begin(tls, url)) return -1;
  int code = http.GET();
  if (code > 0) out = http.getString();
  http.end();
  return code;
}

static bool sendMessage(long long chatId, const String& text) {
  JsonDocument doc;
  doc["chat_id"] = chatId;
  doc["text"]    = text;
  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.setConnectTimeout(10000);
  http.setTimeout(15000);
  if (!http.begin(tls, API + "sendMessage")) return false;
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  if (code != 200) Serial.printf("sendMessage: HTTP %d %s\n", code, http.getString().c_str());
  http.end();
  return code == 200;
}

static bool sendPhoto(long long chatId, const String& caption) {
  camera_fb_t* fb = takePhoto();
  if (!fb) { sendMessage(chatId, "Camera error: could not grab a frame."); return false; }

  // Build the multipart body in one buffer (PSRAM has plenty of room) and POST it.
  static const char B[] = "----bowlcam7f3a9c1e";
  String head = String("--") + B + "\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n" + ll2s(chatId) + "\r\n"
              + "--" + B + "\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n" + caption + "\r\n"
              + "--" + B + "\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"bowl.jpg\"\r\n"
                "Content-Type: image/jpeg\r\n\r\n";
  String tail = String("\r\n--") + B + "--\r\n";
  size_t total = head.length() + fb->len + tail.length();
  uint8_t* body = (uint8_t*)(psramFound() ? ps_malloc(total) : malloc(total));
  if (!body) {
    esp_camera_fb_return(fb);
    sendMessage(chatId, "Out of memory while building the upload.");
    return false;
  }
  memcpy(body, head.c_str(), head.length());
  memcpy(body + head.length(), fb->buf, fb->len);
  memcpy(body + head.length() + fb->len, tail.c_str(), tail.length());
  size_t jpgLen = fb->len;
  esp_camera_fb_return(fb);

  bool ok = false;
  HTTPClient http;
  http.setConnectTimeout(10000);
  http.setTimeout(30000);
  if (http.begin(tls, API + "sendPhoto")) {
    http.addHeader("Content-Type", String("multipart/form-data; boundary=") + B);
    int code = http.POST(body, total);
    ok = (code == 200);
    if (!ok) Serial.printf("sendPhoto: HTTP %d %s\n", code, http.getString().c_str());
    http.end();
  }
  free(body);
  Serial.printf("photo %u bytes -> %s\n", (unsigned)jpgLen, ok ? "sent" : "FAILED");
  return ok;
}

static void handleCommand(long long chatId, String text) {
  text.trim();
  int at = text.indexOf('@');
  if (text.startsWith("/") && at > 0) text = text.substring(0, at);   // "/photo@MyBot" inside groups
  Serial.printf("chat %lld: %s\n", chatId, text.c_str());

  if (ALLOWED_CHAT_ID == 0) {
    // First-time setup helper: tell the sender their chat id, send nothing else to anyone.
    sendMessage(chatId, "Hi. Your chat id is " + ll2s(chatId) +
                        ". Put it in secrets.h as ALLOWED_CHAT_ID and upload again; until then I answer nobody.");
    return;
  }
  if (chatId != ALLOWED_CHAT_ID) return;   // anyone else gets silence

  if (text == "/photo" || text == "/water" || text == "/bowl" || text == "/pic") {
    sendPhoto(chatId, "Water bowl");
  } else if (text == "/status") {
    sendMessage(chatId, "Online. Wi-Fi " + String(WiFi.RSSI()) + " dBm, IP " + WiFi.localIP().toString() +
                        ", up " + String(millis() / 60000UL) + " min, free heap " + String(ESP.getFreeHeap() / 1024) + " KB.");
  } else if (text == "/start" || text == "/help") {
    sendMessage(chatId, "Commands:\n/photo - picture of the bowl\n/status - signal and uptime\n/help - this list");
  } else {
    sendMessage(chatId, "Send /photo for a picture of the bowl.");
  }
}

static void pollTelegram() {
  String url = API + "getUpdates?limit=1&timeout=" + String(POLL_TIMEOUT_S) + "&allowed_updates=%5B%22message%22%5D";
  if (lastUpdateId) url += "&offset=" + ll2s(lastUpdateId + 1);
  String payload;
  int code = tgGet(url, payload, (POLL_TIMEOUT_S + 10) * 1000);
  if (code != 200) {
    Serial.printf("getUpdates: HTTP %d\n", code);
    if (++consecutiveFailures >= 10) { Serial.println("Telegram unreachable, rebooting"); ESP.restart(); }
    delay(3000);
    return;
  }
  consecutiveFailures = 0;

  JsonDocument doc;
  if (deserializeJson(doc, payload)) { Serial.println("Unparseable reply from Telegram"); return; }
  JsonArray results = doc["result"].as<JsonArray>();
  if (results.isNull() || results.size() == 0) return;
  JsonObject upd = results[0].as<JsonObject>();
  lastUpdateId = upd["update_id"].as<long long>();
  JsonObject msg = upd["message"].as<JsonObject>();
  if (msg.isNull()) return;
  long long chatId = msg["chat"]["id"].as<long long>();
  String text = msg["text"] | "";
  handleCommand(chatId, text);
}

// Commands that piled up while the board was off are discarded, so a reboot never
// answers a stale /photo from hours ago.
static void skipBacklog() {
  String payload;
  if (tgGet(API + "getUpdates?offset=-1&limit=1&timeout=0", payload, 15000) != 200) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload)) return;
  JsonArray r = doc["result"].as<JsonArray>();
  if (!r.isNull() && r.size() > 0) lastUpdateId = r[0]["update_id"].as<long long>();
}

// ---------------- Wi-Fi ----------------
static void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("bowl-cam");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Connecting to %s", WIFI_SSID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    delay(250);
    Serial.print('.');
    if (millis() - t0 > WIFI_RETRY_MS) { Serial.println("\nNo Wi-Fi, rebooting"); ESP.restart(); }
  }
  digitalWrite(LED_PIN, HIGH);
  Serial.printf("\nConnected. IP %s  signal %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

static void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("Wi-Fi lost, reconnecting");
  WiFi.disconnect();
  WiFi.reconnect();
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_RETRY_MS) delay(250);
  if (WiFi.status() != WL_CONNECTED) ESP.restart();
}

// ---------------- main ----------------
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  Serial.begin(115200);
  delay(500);
  Serial.println("\nbowl-cam starting");

  if (!startCamera()) { Serial.println("Rebooting in 5 s"); delay(5000); ESP.restart(); }
  connectWiFi();

  if (VERIFY_TLS) tls.setCACert(TELEGRAM_ROOT_CA); else tls.setInsecure();
  tls.setHandshakeTimeout(15);

  skipBacklog();
  Serial.println("Ready. Send /photo to the bot.");
  if (ALLOWED_CHAT_ID != 0) sendMessage(ALLOWED_CHAT_ID, "Bowl cam online. Send /photo for a picture.");
}

void loop() {
  ensureWiFi();
  pollTelegram();
  if (AUTO_PHOTO_MINUTES > 0 && ALLOWED_CHAT_ID != 0 &&
      millis() - lastAutoPhoto >= AUTO_PHOTO_MINUTES * 60000UL) {
    lastAutoPhoto = millis();
    sendPhoto(ALLOWED_CHAT_ID, "Scheduled check");
  }
  delay(200);
}
