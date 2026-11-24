// Basement camera for the Seeed XIAO ESP32S3 Sense.
// Serves a live MJPEG stream, single-shot JPEGs and a status page over HTTP
// with basic-auth. Reconnects Wi-Fi on its own and reboots if it cannot.
//
// Arduino IDE:  Board "XIAO_ESP32S3"  |  Tools > PSRAM: "OPI PSRAM"  |  USB CDC On Boot: Enabled
// Needs secrets.h next to this file (copy secrets.h.example).
//
// URLs once running (http://basement-cam.local or the IP printed on Serial):
//   /         live view page        /jpg      one JPEG frame
//   /stream   raw MJPEG stream      /status   JSON: wifi signal, uptime, memory

#include <WiFi.h>
#include <ESPmDNS.h>
#include <base64.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "secrets.h"

// ---------------- settings you may want to change ----------------
static const char*       HOSTNAME     = "basement-cam";   // -> http://basement-cam.local
static const framesize_t FRAME_SIZE   = FRAMESIZE_HD;     // 1280x720. FRAMESIZE_SVGA (800x600) streams smoother.
static const int         JPEG_QUALITY = 12;               // 0 (best) .. 63 (worst). 10-15 is the sweet spot.
static const bool        VFLIP        = false;            // true if mounted upside down
static const bool        HMIRROR      = false;
static const bool        LOW_LIGHT    = true;             // raise gain/exposure for a dim basement (grainier)
static const uint32_t    WIFI_RETRY_MS = 20000;           // give up and reboot after this long offline
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

static httpd_handle_t server = NULL;
static String expectedAuth;            // "Basic <base64(user:pass)>"
static volatile bool streaming = false;

// ---------------- auth ----------------
static bool authorized(httpd_req_t* req) {
  size_t len = httpd_req_get_hdr_value_len(req, "Authorization");
  if (len == 0 || len > 200) return false;
  char buf[201];
  if (httpd_req_get_hdr_value_str(req, "Authorization", buf, sizeof(buf)) != ESP_OK) return false;
  return expectedAuth.equals(buf);
}

static esp_err_t deny(httpd_req_t* req) {
  httpd_resp_set_status(req, "401 Unauthorized");
  httpd_resp_set_hdr(req, "WWW-Authenticate", "Basic realm=\"basement-cam\"");
  return httpd_resp_send(req, "login required", HTTPD_RESP_USE_STRLEN);
}

// ---------------- handlers ----------------
static const char INDEX_HTML[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Basement cam</title>
<style>
 body{margin:0;background:#111;color:#ccc;font-family:system-ui,sans-serif;text-align:center}
 img{display:block;width:100%;max-width:1280px;margin:0 auto;background:#000}
 p{margin:10px}a{color:#8cf}
</style></head><body>
<img id="v" src="/stream" alt="live view">
<p><a href="/jpg" target="_blank">snapshot</a> &middot; <a href="/status" target="_blank">status</a> &middot; <a href="#" onclick="r();return false">reload stream</a></p>
<script>
 var v=document.getElementById('v');
 function r(){v.src='/stream?t='+Date.now()}
 v.onerror=function(){setTimeout(r,2000)};
 document.addEventListener('visibilitychange',function(){if(!document.hidden)r()});
</script></body></html>)HTML";

static esp_err_t index_handler(httpd_req_t* req) {
  if (!authorized(req)) return deny(req);
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t stream_handler(httpd_req_t* req) {
  if (!authorized(req)) return deny(req);
  if (streaming) {
    httpd_resp_set_status(req, "503 Service Unavailable");
    return httpd_resp_send(req, "another viewer is connected", HTTPD_RESP_USE_STRLEN);
  }
  streaming = true;
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  httpd_resp_set_hdr(req, "Connection", "close");

  esp_err_t res = ESP_OK;
  char part[80];
  while (res == ESP_OK) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) { Serial.println("frame grab failed"); res = ESP_FAIL; break; }
    int n = snprintf(part, sizeof(part),
                     "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
                     (unsigned)fb->len);
    res = httpd_resp_send_chunk(req, part, n);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, "\r\n", 2);
    esp_camera_fb_return(fb);
  }
  streaming = false;
  return res;   // a failed send just means the viewer left
}

static esp_err_t jpg_handler(httpd_req_t* req) {
  if (!authorized(req)) return deny(req);
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=basement.jpg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t res = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t status_handler(httpd_req_t* req) {
  if (!authorized(req)) return deny(req);
  char buf[256];
  snprintf(buf, sizeof(buf),
           "{\"ip\":\"%s\",\"rssi_dbm\":%d,\"uptime_s\":%lu,\"free_heap\":%u,\"free_psram\":%u,\"streaming\":%s}",
           WiFi.localIP().toString().c_str(), WiFi.RSSI(),
           (unsigned long)(millis() / 1000), (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getFreePsram(),
           streaming ? "true" : "false");
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
}

// ---------------- setup pieces ----------------
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
  c.grab_mode    = CAMERA_GRAB_LATEST;   // always serve the newest frame

  if (!psramFound()) {
    Serial.println("PSRAM not found. In the Arduino IDE set Tools > PSRAM to \"OPI PSRAM\". Falling back to 800x600.");
    c.frame_size  = FRAMESIZE_SVGA;
    c.fb_count    = 1;
    c.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  s->set_vflip(s, VFLIP);
  s->set_hmirror(s, HMIRROR);
  if (LOW_LIGHT) {
    s->set_gainceiling(s, GAINCEILING_128X);  // allow high sensor gain
    s->set_ae_level(s, 2);                    // bias auto-exposure brighter
    s->set_aec2(s, 1);                        // night-mode style exposure
    s->set_lenc(s, 1);                        // lens shading correction
  }
  return true;
}

static void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.setSleep(false);                // lower latency, steadier stream
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Connecting to %s", WIFI_SSID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));   // blink while connecting
    delay(250);
    Serial.print('.');
    if (millis() - t0 > WIFI_RETRY_MS) {
      Serial.println("\nNo Wi-Fi, rebooting");
      ESP.restart();
    }
  }
  digitalWrite(LED_PIN, HIGH);   // LED off
  Serial.printf("\nConnected. IP %s  signal %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

static void startServer() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.lru_purge_enable = true;   // drop the oldest idle socket instead of refusing new ones
  cfg.stack_size = 8192;

  static const httpd_uri_t uris[] = {
    { "/",       HTTP_GET, index_handler,  NULL },
    { "/stream", HTTP_GET, stream_handler, NULL },
    { "/jpg",    HTTP_GET, jpg_handler,    NULL },
    { "/status", HTTP_GET, status_handler, NULL },
  };
  if (httpd_start(&server, &cfg) != ESP_OK) {
    Serial.println("HTTP server failed to start");
    return;
  }
  for (const auto& u : uris) httpd_register_uri_handler(server, &u);
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  Serial.begin(115200);
  delay(500);
  Serial.println("\nbasement-cam starting");

  expectedAuth = "Basic " + base64::encode(String(CAM_USER) + ":" + String(CAM_PASS));

  if (!startCamera()) {
    Serial.println("Rebooting in 5 s");
    delay(5000);
    ESP.restart();
  }
  connectWiFi();
  if (MDNS.begin(HOSTNAME)) MDNS.addService("http", "tcp", 80);
  startServer();

  Serial.printf("Live view: http://%s/   or   http://%s.local/\n",
                WiFi.localIP().toString().c_str(), HOSTNAME);
}

void loop() {
  // Keep the link alive: reconnect if the router dropped us, reboot if that fails.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi lost, reconnecting");
    WiFi.disconnect();
    WiFi.reconnect();
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_RETRY_MS) delay(250);
    if (WiFi.status() != WL_CONNECTED) ESP.restart();
    Serial.printf("Back online, IP %s\n", WiFi.localIP().toString().c_str());
  }
  delay(1000);
}
