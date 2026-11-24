// Cat water bowl camera with low-water alert: Seeed XIAO ESP32S3 Sense + Telegram.
//
// What it does
//   /photo            a 1600x1200 picture of the bowl, from anywhere, in a few seconds
//   low-water alert   watches the bowl's level window with the camera (or reads a
//                     non-contact liquid sensor on one pin) and messages you, with a
//                     photo, when the water drops below your line; again when it is back
//
// Arduino IDE:  Board "XIAO_ESP32S3"  |  Tools > PSRAM: "OPI PSRAM"  |  USB CDC On Boot: Enabled
// Library Manager: "ArduinoJson" by Benoit Blanchon (7.x).
// Copy secrets.h.example to secrets.h (same folder) and fill it in.
//
// Bot commands
//   /photo (/water /bowl /pic)  picture now
//   /aim                        picture with the detection box drawn, to position the camera
//   /calibrate full             teach it how the box looks with water above the line
//   /calibrate low              teach it how the box looks with water below the line
//   /calibrate reset            forget both
//   /level                      what it thinks right now, with the numbers behind it
//   /status                     wifi, uptime, memory
//   /help

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include "esp_camera.h"
#include "img_converters.h"
#include "secrets.h"

// ---------------- settings you may want to change ----------------
enum LevelSource { LEVEL_NONE, LEVEL_CAMERA, LEVEL_SENSOR_PIN };
static const LevelSource LEVEL_SOURCE = LEVEL_CAMERA;   // LEVEL_CAMERA: watch the window. LEVEL_SENSOR_PIN: liquid sensor on D1. LEVEL_NONE: photos only.

// Camera watcher: the detection box as fractions of the frame (0..1). Default: a 10% square, dead centre.
// Aim the camera so the window's LOW line runs through this box. /aim shows the box.
static const float MARK_X = 0.45f, MARK_Y = 0.45f, MARK_W = 0.10f, MARK_H = 0.10f;
static const float MIN_CONFIDENCE = 0.25f;               // how clearly a reading must favour one state to count

// Sensor-pin watcher: XKC-Y25-NPN non-contact liquid sensor, OUT wire on D1 (GPIO2), open-collector output.
static const int LEVEL_SENSOR_PIN = D1;
static const int SENSOR_WET_LEVEL = LOW;                 // what the pin reads while the sensor sees water

// Alert timing
static const uint32_t CHECK_EVERY_MIN = 2;               // how often to look
static const int      LOW_CONFIRM     = 3;               // consecutive low readings before alerting (3 x 2 min)
static const uint32_t REMIND_HOURS    = 8;               // repeat the alert while it stays low

// Photos
static const framesize_t FRAME_SIZE   = FRAMESIZE_UXGA;  // 1600x1200 stills. FRAMESIZE_HD if uploads are slow.
static const int         JPEG_QUALITY = 12;              // 0 (best) .. 63 (worst)
static const bool        VFLIP = false, HMIRROR = false; // flip if mounted upside down
static const bool        LOW_LIGHT = true;               // raise sensor gain for a dim basement (grainier)
static const uint32_t    AUTO_PHOTO_MINUTES = 0;         // >0: unasked photo every N minutes

static const bool        VERIFY_TLS = true;              // false = accept any certificate (only if Telegram changes its CA)
static const int         POLL_TIMEOUT_S = 20;            // Telegram long-poll wait
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

// ---------------- state ----------------
static WiFiClientSecure tls;
static const String API = String("https://api.telegram.org/bot") + BOT_TOKEN + "/";
static Preferences prefs;

static long long lastUpdateId = 0;        // Telegram update offset
static uint32_t  lastAutoPhoto = 0;
static int       consecutiveFailures = 0;
static framesize_t photoSize = FRAME_SIZE;   // what /photo uses (smaller if PSRAM is missing)
static framesize_t currentSize;              // what the sensor is producing right now

struct Feat { float f[3]; };                 // how the detection box looks: brightness ratio + two colour ratios
static Feat featFull, featLow;
static bool haveFull = false, haveLow = false;

enum Reading    { R_OK, R_LOW, R_UNSURE, R_DARK, R_UNCAL, R_ERROR };
enum LevelState { S_UNKNOWN, S_OK, S_LOW };
static LevelState levelState = S_UNKNOWN;
static int        lowStreak = 0;
static uint32_t   nextCheckMs = 0, lastAlertMs = 0;
static Reading    lastReading = R_UNCAL;
static String     lastDetail = "no check yet";

static String ll2s(long long v) { char b[24]; snprintf(b, sizeof(b), "%lld", v); return String(b); }
static void* bigAlloc(size_t n) { return psramFound() ? ps_malloc(n) : malloc(n); }

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
  c.grab_mode    = CAMERA_GRAB_LATEST;   // sensor keeps running, so auto-exposure stays settled

  if (!psramFound()) {
    Serial.println("PSRAM not found. In the Arduino IDE set Tools > PSRAM to \"OPI PSRAM\". Falling back to 800x600.");
    c.frame_size  = FRAMESIZE_SVGA;
    c.fb_count    = 1;
    c.fb_location = CAMERA_FB_IN_DRAM;
  }
  photoSize = currentSize = c.frame_size;

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

// Read the real picture size out of a JPEG's header (its SOF marker). The driver reports
// fb->width from the sensor *setting*, which can be ahead of the data for a frame or two
// after a size change; decoding such a frame into a smaller buffer would overrun it.
static bool jpegDims(const uint8_t* b, size_t n, int* w, int* h) {
  if (n < 4 || b[0] != 0xFF || b[1] != 0xD8) return false;
  size_t i = 2;
  while (i + 9 < n) {
    if (b[i] != 0xFF) { i++; continue; }
    uint8_t m = b[i + 1];
    if (m == 0xFF) { i++; continue; }                                         // fill byte
    if (m == 0x01 || (m >= 0xD0 && m <= 0xD8)) { i += 2; continue; }         // markers without a length
    size_t len = ((size_t)b[i + 2] << 8) | b[i + 3];
    if (m == 0xC0 || m == 0xC1 || m == 0xC2) {                               // start of frame
      *h = (b[i + 5] << 8) | b[i + 6];
      *w = (b[i + 7] << 8) | b[i + 8];
      return *w > 0 && *h > 0;
    }
    if (m == 0xDA) return false;                                              // scan data reached, no SOF
    i += 2 + len;
  }
  return false;
}

// Grab a frame whose JPEG data really is `size`, switching the sensor if needed and letting exposure settle.
static camera_fb_t* grabFrame(framesize_t size) {
  sensor_t* s = esp_camera_sensor_get();
  int settle = 2;
  if (size != currentSize) { s->set_framesize(s, size); currentSize = size; settle = 4; }
  for (int i = 0; i < settle; i++) { camera_fb_t* f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  for (int tries = 0; tries < 10; tries++) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) return NULL;
    int w = 0, h = 0;
    if (fb->format == PIXFORMAT_JPEG && jpegDims(fb->buf, fb->len, &w, &h) &&
        w == resolution[size].width && h == resolution[size].height) return fb;
    esp_camera_fb_return(fb);                          // an old-size or broken frame, try the next
  }
  return NULL;
}

// Decode a frame at `size` into a packed 3-bytes-per-pixel buffer (caller frees).
// The byte order of the three channels is whatever the core's converter produces;
// nothing below depends on it, because calibration and checks use the same converter.
static uint8_t* grabRGB(framesize_t size, int* W, int* H) {
  camera_fb_t* fb = grabFrame(size);
  if (!fb) return NULL;
  jpegDims(fb->buf, fb->len, W, H);                    // verified by grabFrame; sizes the buffer from the data
  size_t n = (size_t)(*W) * (*H) * 3;
  uint8_t* rgb = (uint8_t*)bigAlloc(n);
  bool ok = rgb && fmt2rgb888(fb->buf, fb->len, fb->format, rgb);
  esp_camera_fb_return(fb);
  if (!ok) { free(rgb); return NULL; }
  return rgb;
}

// ---------------- level detection ----------------
static void markRect(int W, int H, int& x0, int& y0, int& x1, int& y1) {
  x0 = MARK_X * W; y0 = MARK_Y * H; x1 = (MARK_X + MARK_W) * W; y1 = (MARK_Y + MARK_H) * H;
  if (x1 <= x0) x1 = x0 + 1;
  if (y1 <= y0) y1 = y0 + 1;
}

// Measure the box: brightness relative to the whole frame (cancels lighting changes) plus two colour ratios.
static bool measure(Feat& out, float& frameMean) {
  int W, H;
  uint8_t* rgb = grabRGB(FRAMESIZE_QVGA, &W, &H);
  if (!rgb) return false;

  uint64_t sum = 0; uint32_t n = 0;
  for (int y = 0; y < H; y += 2)
    for (int x = 0; x < W; x += 2) { const uint8_t* p = rgb + ((size_t)y * W + x) * 3; sum += p[0] + p[1] + p[2]; n++; }
  frameMean = sum / (3.0f * n);

  int x0, y0, x1, y1; markRect(W, H, x0, y0, x1, y1);
  uint64_t c0 = 0, c1 = 0, c2 = 0; uint32_t m = 0;
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) { const uint8_t* p = rgb + ((size_t)y * W + x) * 3; c0 += p[0]; c1 += p[1]; c2 += p[2]; m++; }
  free(rgb);

  float a = c0 / (float)m, b = c1 / (float)m, c = c2 / (float)m, S = a + b + c + 0.001f;
  out.f[0] = ((a + b + c) / 3.0f) / max(frameMean, 1.0f);
  out.f[1] = a / S;
  out.f[2] = c / S;
  return true;
}

// Distance between two looks. One unit is roughly a 25% brightness change or a 5% colour shift.
static float dist(const Feat& a, const Feat& b) {
  float d0 = (a.f[0] - b.f[0]) / 0.25f, d1 = (a.f[1] - b.f[1]) / 0.05f, d2 = (a.f[2] - b.f[2]) / 0.05f;
  return sqrtf(d0 * d0 + d1 * d1 + d2 * d2);
}

static Reading readCamera(String& detail) {
  if (!haveFull || !haveLow) { detail = "not calibrated: send /aim, then /calibrate full and /calibrate low"; return R_UNCAL; }
  Feat now; float F;
  if (!measure(now, F)) { detail = "camera error"; return R_ERROR; }
  if (F < 12) { detail = "too dark to judge (frame brightness " + String(F, 0) + "/255)"; return R_DARK; }
  float dF = dist(now, featFull), dL = dist(now, featLow);
  float conf = fabsf(dF - dL) / (dF + dL + 1e-6f);
  detail = "brightness ratio " + String(now.f[0], 2) + " (full " + String(featFull.f[0], 2) + ", low " +
           String(featLow.f[0], 2) + "), confidence " + String(conf, 2);
  if (conf < MIN_CONFIDENCE) return R_UNSURE;
  return dL < dF ? R_LOW : R_OK;
}

static Reading readSensorPin(String& detail) {
  int v = digitalRead(LEVEL_SENSOR_PIN);
  detail = String("sensor pin reads ") + (v ? "HIGH" : "LOW");
  return (v == SENSOR_WET_LEVEL) ? R_OK : R_LOW;
}

static Reading readLevel(String& detail) {
  return (LEVEL_SOURCE == LEVEL_CAMERA) ? readCamera(detail) : readSensorPin(detail);
}

static const char* readingName(Reading r) {
  switch (r) {
    case R_OK:     return "OK, water above the line";
    case R_LOW:    return "LOW";
    case R_UNSURE: return "unsure";
    case R_DARK:   return "too dark";
    case R_UNCAL:  return "not calibrated";
    default:       return "error";
  }
}

static void saveFeat(const char* prefix, const Feat& f) {
  char k[4];
  for (int i = 0; i < 3; i++) { snprintf(k, sizeof(k), "%s%d", prefix, i); prefs.putFloat(k, f.f[i]); }
}
static bool loadFeat(const char* prefix, Feat& f) {
  char k[4];
  for (int i = 0; i < 3; i++) {
    snprintf(k, sizeof(k), "%s%d", prefix, i);
    if (!prefs.isKey(k)) return false;
    f.f[i] = prefs.getFloat(k);
  }
  return true;
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

static bool sendJpeg(long long chatId, const uint8_t* jpg, size_t jpgLen, const String& caption) {
  // Build the multipart body in one buffer and POST it.
  static const char B[] = "----bowlcam7f3a9c1e";
  String head = String("--") + B + "\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n" + ll2s(chatId) + "\r\n"
              + "--" + B + "\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n" + caption + "\r\n"
              + "--" + B + "\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"bowl.jpg\"\r\n"
                "Content-Type: image/jpeg\r\n\r\n";
  String tail = String("\r\n--") + B + "--\r\n";
  size_t total = head.length() + jpgLen + tail.length();
  uint8_t* body = (uint8_t*)bigAlloc(total);
  if (!body) { sendMessage(chatId, "Out of memory while building the upload."); return false; }
  memcpy(body, head.c_str(), head.length());
  memcpy(body + head.length(), jpg, jpgLen);
  memcpy(body + head.length() + jpgLen, tail.c_str(), tail.length());

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

static bool sendPhoto(long long chatId, const String& caption) {
  camera_fb_t* fb = grabFrame(photoSize);
  if (!fb) { sendMessage(chatId, "Camera error: could not grab a frame."); return false; }
  bool ok = sendJpeg(chatId, fb->buf, fb->len, caption);
  esp_camera_fb_return(fb);
  return ok;
}

// ---------------- commands ----------------
static inline void setPx(uint8_t* rgb, int W, int H, int x, int y, uint8_t v) {
  if (x < 0 || y < 0 || x >= W || y >= H) return;
  uint8_t* p = rgb + ((size_t)y * W + x) * 3;
  p[0] = p[1] = p[2] = v;
}

// /aim: a picture with the detection box drawn (white frame, black edge), so you can line the camera up.
static void sendAim(long long chatId) {
  int W, H;
  uint8_t* rgb = grabRGB(FRAMESIZE_VGA, &W, &H);
  if (!rgb) { sendMessage(chatId, "Camera error, try again."); return; }
  int x0, y0, x1, y1; markRect(W, H, x0, y0, x1, y1);
  for (int t = -4; t < 0; t++) {                       // drawn just outside the box, so the box itself is untouched
    uint8_t v = (t == -4) ? 0 : 255;
    for (int x = x0 + t; x < x1 - t; x++) { setPx(rgb, W, H, x, y0 + t, v); setPx(rgb, W, H, x, y1 - 1 - t, v); }
    for (int y = y0 + t; y < y1 - t; y++) { setPx(rgb, W, H, x0 + t, y, v); setPx(rgb, W, H, x1 - 1 - t, y, v); }
  }
  uint8_t* jpg = NULL; size_t jpgLen = 0;
  bool ok = fmt2jpg(rgb, (size_t)W * H * 3, W, H, PIXFORMAT_RGB888, 80, &jpg, &jpgLen);
  free(rgb);
  if (!ok) { sendMessage(chatId, "Could not encode the aim picture."); return; }
  sendJpeg(chatId, jpg, jpgLen, "Aim: the window's LOW line should run through the box. Then /calibrate full and /calibrate low.");
  free(jpg);
}

static void calibrate(long long chatId, const String& which) {
  if (LEVEL_SOURCE != LEVEL_CAMERA) { sendMessage(chatId, "Calibration is only for the camera watcher (LEVEL_SOURCE)."); return; }
  if (which == "reset") {
    prefs.clear(); haveFull = haveLow = false; levelState = S_UNKNOWN; lowStreak = 0;
    sendMessage(chatId, "Calibration cleared.");
    return;
  }
  if (which != "full" && which != "low") { sendMessage(chatId, "Use /calibrate full, /calibrate low or /calibrate reset."); return; }

  Feat f; float F;
  if (!measure(f, F)) { sendMessage(chatId, "Camera error, try again."); return; }
  if (F < 12) { sendMessage(chatId, "Too dark to calibrate. Turn on a light near the bowl first."); return; }
  if (which == "full") { featFull = f; haveFull = true; saveFeat("f", f); }
  else                 { featLow  = f; haveLow  = true; saveFeat("l", f); }

  String msg = "Saved '" + which + "': brightness ratio " + String(f.f[0], 2) + ".";
  if (haveFull && haveLow) {
    float sep = dist(featFull, featLow);
    msg += " Full and low differ by " + String(sep, 1);
    msg += (sep < 1.5f) ? ", which is not much. Improve the light or the angle, then calibrate again."
                        : ", which is clear. Watching now.";
    levelState = S_UNKNOWN; lowStreak = 0;
  } else {
    msg += haveFull ? " Now send /calibrate low when the water is below the line."
                    : " Now send /calibrate full when the water is above the line.";
  }
  sendMessage(chatId, msg);
}

static void handleCommand(long long chatId, String text) {
  text.trim();
  String cmd = text, arg;
  int sp = text.indexOf(' ');
  if (sp > 0) { cmd = text.substring(0, sp); arg = text.substring(sp + 1); arg.trim(); }
  int at = cmd.indexOf('@');
  if (cmd.startsWith("/") && at > 0) cmd = cmd.substring(0, at);   // "/photo@MyBot" inside groups
  Serial.printf("chat %lld: %s\n", chatId, text.c_str());

  if (ALLOWED_CHAT_ID == 0) {
    // First-time setup helper: tell the sender their chat id, send nothing else to anyone.
    sendMessage(chatId, "Hi. Your chat id is " + ll2s(chatId) +
                        ". Put it in secrets.h as ALLOWED_CHAT_ID and upload again; until then I answer nobody.");
    return;
  }
  if (chatId != ALLOWED_CHAT_ID) return;   // anyone else gets silence

  if (cmd == "/photo" || cmd == "/water" || cmd == "/bowl" || cmd == "/pic") {
    sendPhoto(chatId, "Water bowl");
  } else if (cmd == "/aim") {
    sendAim(chatId);
  } else if (cmd == "/calibrate") {
    calibrate(chatId, arg);
  } else if (cmd == "/level") {
    if (LEVEL_SOURCE == LEVEL_NONE) { sendMessage(chatId, "Level watching is off (LEVEL_SOURCE)."); return; }
    String d; Reading r = readLevel(d);
    String st = (levelState == S_LOW) ? "LOW alert active" : (levelState == S_OK) ? "normal" : "nothing confirmed yet";
    sendMessage(chatId, String("Now: ") + readingName(r) + ". " + d + "\nAlert state: " + st +
                        ". Low readings in a row: " + String(lowStreak) + " of " + String(LOW_CONFIRM) + ".");
  } else if (cmd == "/status") {
    sendMessage(chatId, "Online. Wi-Fi " + String(WiFi.RSSI()) + " dBm, IP " + WiFi.localIP().toString() +
                        ", up " + String(millis() / 60000UL) + " min, free heap " + String(ESP.getFreeHeap() / 1024) +
                        " KB.\nLast level check: " + readingName(lastReading) + ", " + lastDetail);
  } else if (cmd == "/start" || cmd == "/help") {
    sendMessage(chatId, "Commands:\n/photo - picture of the bowl\n/aim - picture with the detection box\n"
                        "/calibrate full | low | reset - teach the watcher\n/level - current reading\n"
                        "/status - signal, uptime, last check\n/help - this list");
  } else {
    sendMessage(chatId, "Send /photo for a picture, /level for the water reading, /help for everything.");
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

// ---------------- the watcher ----------------
static void runLevelCheck() {
  String detail;
  Reading r = readLevel(detail);
  lastReading = r; lastDetail = detail;
  Serial.printf("level: %s - %s\n", readingName(r), detail.c_str());
  if (ALLOWED_CHAT_ID == 0) return;

  if (r == R_LOW) {
    if (lowStreak < LOW_CONFIRM) lowStreak++;
    bool due = (levelState != S_LOW) || (millis() - lastAlertMs >= REMIND_HOURS * 3600000UL);
    if (lowStreak >= LOW_CONFIRM && due) {
      levelState = S_LOW;
      lastAlertMs = millis();
      sendPhoto(ALLOWED_CHAT_ID, "LOW WATER: the bowl is below the line. " + detail);
    }
  } else if (r == R_OK) {
    lowStreak = 0;
    if (levelState == S_LOW) sendMessage(ALLOWED_CHAT_ID, "Water is back above the line.");
    levelState = S_OK;
  }
  // unsure, too dark, error: keep the previous state and say nothing
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
  if (LEVEL_SOURCE == LEVEL_SENSOR_PIN) pinMode(LEVEL_SENSOR_PIN, INPUT_PULLUP);

  prefs.begin("bowl", false);
  haveFull = loadFeat("f", featFull);
  haveLow  = loadFeat("l", featLow);

  connectWiFi();
  if (VERIFY_TLS) tls.setCACert(TELEGRAM_ROOT_CA); else tls.setInsecure();
  tls.setHandshakeTimeout(15);

  skipBacklog();
  nextCheckMs = millis() + 60000UL;   // first level check a minute after boot
  Serial.println("Ready. Send /photo to the bot.");
  if (ALLOWED_CHAT_ID != 0) {
    String hello = "Bowl cam online. ";
    if (LEVEL_SOURCE == LEVEL_CAMERA)          hello += (haveFull && haveLow) ? "Watching the window." : "Not calibrated yet: send /aim, then /calibrate full and /calibrate low.";
    else if (LEVEL_SOURCE == LEVEL_SENSOR_PIN) hello += "Watching the liquid sensor.";
    else                                       hello += "Send /photo for a picture.";
    sendMessage(ALLOWED_CHAT_ID, hello);
  }
}

void loop() {
  ensureWiFi();
  pollTelegram();

  if (LEVEL_SOURCE != LEVEL_NONE && (int32_t)(millis() - nextCheckMs) >= 0) {
    nextCheckMs = millis() + CHECK_EVERY_MIN * 60000UL;
    runLevelCheck();
  }
  if (AUTO_PHOTO_MINUTES > 0 && ALLOWED_CHAT_ID != 0 &&
      millis() - lastAutoPhoto >= AUTO_PHOTO_MINUTES * 60000UL) {
    lastAutoPhoto = millis();
    sendPhoto(ALLOWED_CHAT_ID, "Scheduled check");
  }
  delay(200);
}
