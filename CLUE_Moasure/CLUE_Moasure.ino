/*
 * CLUE_Moasure — DIY motion-based measuring tool
 *
 * Hardware : Adafruit CLUE (nRF52840)
 * Sensors  : LSM6DS33 accel/gyro + LIS3MDL mag + BMP280 baro (all on-board)
 *
 * Install these libraries via Tools → Manage Libraries:
 *   Adafruit LSM6DS          (IMU driver)
 *   Adafruit LIS3MDL         (magnetometer driver)
 *   Adafruit BMP280          (barometer driver)
 *   Adafruit GFX Library     (display graphics primitives)
 *   Adafruit ST7789          (display driver)
 *   Adafruit AHRS            (Madgwick sensor-fusion filter)
 *
 * NOTE: Do NOT install ArduinoBLE. BLE is handled by the bluefruit.h library
 *       that ships with the Adafruit nRF52 BSP.
 *
 * Usage:
 *   Button A  — start / stop a measurement session
 *   Button B  — manually log a corner waypoint
 *   Auto-log  — a waypoint is also logged whenever the device goes still
 *
 * BLE service UUID : 19B10000-E8F2-537E-4F6C-D104768A1214
 *   Waypoint char  : 19B10001  (notify, 12 bytes = 3x float32 x/y/z metres)
 *   Command char   : 19B10002  (write 1 byte: 0=idle 1=start 2=reset)
 */

#include <Wire.h>
#include <SPI.h>
#include <Adafruit_LSM6DS33.h>
#include <Adafruit_LIS3MDL.h>
#include <Adafruit_BMP280.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <Adafruit_AHRS.h>
#include <bluefruit.h>   // built into the Adafruit nRF52 BSP — do not install separately

// ── Display ──────────────────────────────────────────────────────────────────
// PIN_TFT_CS / _DC / _RST / _LITE defined in the CLUE BSP variant.h
Adafruit_ST7789 tft(PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);

// ── Sensors ──────────────────────────────────────────────────────────────────
Adafruit_LSM6DS33 imu;
Adafruit_LIS3MDL  mag;
Adafruit_BMP280   baro;

// 9-DOF Madgwick filter
Adafruit_Madgwick ahrs;

// ── BLE ──────────────────────────────────────────────────────────────────────
BLEService        measSvc("19B10000-E8F2-537E-4F6C-D104768A1214");
BLECharacteristic wpChar("19B10001-E8F2-537E-4F6C-D104768A1214");   // notify, 12 bytes
BLECharacteristic cmdChar("19B10002-E8F2-537E-4F6C-D104768A1214");  // write,  1 byte

// ── Tuning constants ─────────────────────────────────────────────────────────
static const float RATE_HZ       = 100.0f;
static const float DT            = 1.0f / RATE_HZ;
static const float ZUPT_ACCEL_THR = 0.12f;  // m/s² deviation from g
static const float ZUPT_GYRO_THR  = 0.04f;  // rad/s total magnitude
static const int   ZUPT_HOLD      = 8;       // consecutive 100-Hz ticks (~80 ms)

// ── State ─────────────────────────────────────────────────────────────────────
enum MeasState : uint8_t { IDLE, MEASURING };
MeasState measState = IDLE;

// World-frame position and velocity (metres, ENU)
float vx, vy, vz;
float px, py, pz;
float totalDist;
float refAlt;
uint16_t nWaypoints;

// ZUPT hysteresis
int  zuptTicks     = 0;
bool wasStationary = false;

// Pending command from BLE write callback (processed in loop())
volatile int8_t pendingCmd = -1;

// ── Timing ────────────────────────────────────────────────────────────────────
uint32_t nextLoopUs = 0;
uint8_t  dispTick   = 0;

// ── Math helper ──────────────────────────────────────────────────────────────
// Rotate body-frame vector by quaternion into world frame.
inline void quatRotate(float qw, float qx, float qy, float qz,
                       float bx, float by, float bz,
                       float &wx, float &wy, float &wz) {
    wx = (1.0f - 2.0f*(qy*qy + qz*qz))*bx
       +         2.0f*(qx*qy - qw*qz) *by
       +         2.0f*(qx*qz + qw*qy) *bz;
    wy =         2.0f*(qx*qy + qw*qz) *bx
       + (1.0f - 2.0f*(qx*qx + qz*qz))*by
       +         2.0f*(qy*qz - qw*qx) *bz;
    wz =         2.0f*(qx*qz - qw*qy) *bx
       +         2.0f*(qy*qz + qw*qx) *by
       + (1.0f - 2.0f*(qx*qx + qy*qy))*bz;
}

// ── BLE callbacks ─────────────────────────────────────────────────────────────
void onCmdWrite(uint16_t /*conn*/, BLECharacteristic* /*chr*/,
                uint8_t* data, uint16_t len) {
    if (len > 0) pendingCmd = (int8_t)data[0];
}

// ── Waypoint publish ──────────────────────────────────────────────────────────
void logWaypoint() {
    float payload[3] = { px, py, pz };
    if (Bluefruit.connected()) {
        wpChar.notify((uint8_t*)payload, 12);
    }
    nWaypoints++;
}

// ── Display ───────────────────────────────────────────────────────────────────
void refreshDisplay(bool force = false) {
    static float     lastDist  = -999.0f;
    static float     lastElev  = -999.0f;
    static uint16_t  lastPts   = 0xFFFF;
    static MeasState lastState = (MeasState)0xFF;
    static bool      lastBLE   = false;

    if (force) {
        lastDist = lastElev = -999.0f;
        lastPts   = 0xFFFF;
        lastState = (MeasState)0xFF;
        lastBLE   = false;
        tft.fillScreen(ST77XX_BLACK);
    }

    bool  bleConn = Bluefruit.connected();
    float elev    = baro.readAltitude(1013.25f) - refAlt;
    char  buf[20];

    // State banner + static labels
    if (lastState != measState) {
        tft.fillRect(0, 0, 240, 28, ST77XX_BLACK);
        tft.setTextSize(2);
        tft.setCursor(4, 6);
        if (measState == MEASURING) {
            tft.setTextColor(ST77XX_GREEN);
            tft.print("MEASURING");
        } else {
            tft.setTextColor(ST77XX_YELLOW);
            tft.print("READY  [A]=start");
        }
        tft.setTextColor(0x7BEF);
        tft.setTextSize(1);
        tft.setCursor(4, 38);  tft.print("Distance");
        tft.setCursor(4, 82);  tft.print("Elevation");
        tft.setCursor(4, 126); tft.print("Waypoints");
        lastState = measState;
    }

    if (force || fabsf(totalDist - lastDist) > 0.005f) {
        tft.fillRect(4, 48, 180, 22, ST77XX_BLACK);
        snprintf(buf, sizeof(buf), "%.2f m", totalDist);
        tft.setTextColor(ST77XX_WHITE); tft.setTextSize(2);
        tft.setCursor(4, 50); tft.print(buf);
        lastDist = totalDist;
    }

    if (force || fabsf(elev - lastElev) > 0.05f) {
        tft.fillRect(4, 92, 180, 22, ST77XX_BLACK);
        snprintf(buf, sizeof(buf), "%+.1f m", elev);
        tft.setTextColor(ST77XX_CYAN); tft.setTextSize(2);
        tft.setCursor(4, 94); tft.print(buf);
        lastElev = elev;
    }

    if (force || lastPts != nWaypoints) {
        tft.fillRect(4, 136, 100, 22, ST77XX_BLACK);
        snprintf(buf, sizeof(buf), "%u", nWaypoints);
        tft.setTextColor(ST77XX_MAGENTA); tft.setTextSize(2);
        tft.setCursor(4, 138); tft.print(buf);
        lastPts = nWaypoints;
    }

    if (force || bleConn != lastBLE) {
        uint16_t col = bleConn ? 0x001F : 0x39E7;
        tft.fillCircle(228, 14, 10, col);
        lastBLE = bleConn;
    }

    if (measState == MEASURING) {
        bool still = (zuptTicks >= ZUPT_HOLD);
        tft.fillRect(4, 170, 160, 18, ST77XX_BLACK);
        tft.setTextSize(1);
        tft.setTextColor(still ? ST77XX_GREEN : 0x7BEF);
        tft.setCursor(4, 174);
        tft.print(still ? "STILL - auto-log" : "moving...");
    }
}

// ── Reset session ─────────────────────────────────────────────────────────────
void resetMeasurement() {
    vx = vy = vz = 0.0f;
    px = py = pz = 0.0f;
    totalDist     = 0.0f;
    nWaypoints    = 0;
    zuptTicks     = 0;
    wasStationary = false;
    refAlt        = baro.readAltitude(1013.25f);
    ahrs.begin(RATE_HZ);
}

// ── setup() ──────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    pinMode(PIN_TFT_LITE, OUTPUT);
    digitalWrite(PIN_TFT_LITE, HIGH);

    tft.init(240, 240, SPI_MODE2);
    tft.setRotation(1);
    tft.fillScreen(ST77XX_BLACK);
    tft.setTextColor(ST77XX_WHITE);
    tft.setTextSize(2);
    tft.setCursor(4, 4);
    tft.println("Starting up...");

    Wire.begin();
    Serial.println("Wire OK");
    if (!imu.begin_I2C()) { Serial.println("IMU fail");  tft.println("IMU fail!");  while (1) delay(10); }
    Serial.println("IMU OK");
    if (!mag.begin_I2C()) { Serial.println("Mag fail");  tft.println("Mag fail!");  while (1) delay(10); }
    Serial.println("Mag OK");
    if (!baro.begin(0x77)) { Serial.println("Baro fail"); tft.println("Baro fail!"); while (1) delay(10); }
    Serial.println("Baro OK");

    imu.setAccelRange(LSM6DS_ACCEL_RANGE_4_G);
    imu.setAccelDataRate(LSM6DS_RATE_104_HZ);
    imu.setGyroRange(LSM6DS_GYRO_RANGE_2000_DPS);
    imu.setGyroDataRate(LSM6DS_RATE_104_HZ);

    mag.setDataRate(LIS3MDL_DATARATE_80_HZ);
    mag.setRange(LIS3MDL_RANGE_4_GAUSS);
    mag.setPerformanceMode(LIS3MDL_HIGHMODE);
    mag.setOperationMode(LIS3MDL_CONTINUOUSMODE);

    pinMode(PIN_BUTTON1, INPUT_PULLUP);
    pinMode(PIN_BUTTON2, INPUT_PULLUP);

    // BLE — using Adafruit Bluefruit (built into the nRF52 BSP)
    Bluefruit.begin();
    Bluefruit.setName("Moasure-DIY");

    measSvc.begin();

    wpChar.setProperties(CHR_PROPS_READ | CHR_PROPS_NOTIFY);
    wpChar.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
    wpChar.setFixedLen(12);
    wpChar.begin();

    cmdChar.setProperties(CHR_PROPS_READ | CHR_PROPS_WRITE);
    cmdChar.setPermission(SECMODE_OPEN, SECMODE_OPEN);
    cmdChar.setFixedLen(1);
    cmdChar.setWriteCallback(onCmdWrite);
    cmdChar.begin();

    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addService(measSvc);
    Bluefruit.ScanResponse.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(32, 244);
    Bluefruit.Advertising.setFastTimeout(30);
    Bluefruit.Advertising.start(0);

    resetMeasurement();
    tft.fillScreen(ST77XX_BLACK);
    refreshDisplay(true);

    nextLoopUs = micros();
}

// ── loop() ───────────────────────────────────────────────────────────────────
void loop() {
    // Process BLE command written by callback
    if (pendingCmd >= 0) {
        switch (pendingCmd) {
            case 1: resetMeasurement(); measState = MEASURING; refreshDisplay(true); break;
            case 0: measState = IDLE;                          refreshDisplay(true); break;
            case 2: resetMeasurement(); measState = IDLE;      refreshDisplay(true); break;
        }
        pendingCmd = -1;
    }

    // Button A — toggle session
    static bool prevA = HIGH;
    bool curA = digitalRead(PIN_BUTTON1);
    if (prevA && !curA) {
        if (measState == IDLE) { resetMeasurement(); measState = MEASURING; }
        else                   { measState = IDLE; }
        refreshDisplay(true);
    }
    prevA = curA;

    // Button B — manual waypoint
    static bool prevB = HIGH;
    bool curB = digitalRead(PIN_BUTTON2);
    if (prevB && !curB && measState == MEASURING) {
        logWaypoint();
        refreshDisplay();
    }
    prevB = curB;

    // 100 Hz sensor tick
    if ((int32_t)(micros() - nextLoopUs) < 0) return;
    nextLoopUs += (uint32_t)(DT * 1.0e6f);

    // Read IMU
    sensors_event_t aEv, gEv, tEv;
    imu.getEvent(&aEv, &gEv, &tEv);
    float ax = aEv.acceleration.x;
    float ay = aEv.acceleration.y;
    float az = aEv.acceleration.z;
    float gx = gEv.gyro.x;
    float gy = gEv.gyro.y;
    float gz = gEv.gyro.z;

    // Read magnetometer
    sensors_event_t mEv;
    mag.getEvent(&mEv);
    float mx = mEv.magnetic.x;
    float my = mEv.magnetic.y;
    float mz = mEv.magnetic.z;

    // Madgwick update — runs in IDLE too so filter converges before measuring
    ahrs.update(gx, gy, gz, ax, ay, az, mx, my, mz);

    // Display refresh ~5 Hz
    if (++dispTick >= 20) {
        refreshDisplay();
        dispTick = 0;
    }

    if (measState != MEASURING) return;

    // Quaternion → world-frame acceleration
    float qw, qx, qy, qz;
    ahrs.getQuaternion(&qw, &qx, &qy, &qz);

    float wax, way, waz;
    quatRotate(qw, qx, qy, qz, ax, ay, az, wax, way, waz);

    // Remove gravity (ENU: +Z up, stationary reads +9.81 in world Z).
    // If distance grows when stationary, change -= to +=
    waz -= 9.81f;

    // ZUPT
    float accelDev = fabsf(sqrtf(ax*ax + ay*ay + az*az) - 9.81f);
    float gyroMag  = sqrtf(gx*gx + gy*gy + gz*gz);
    bool  still    = (accelDev < ZUPT_ACCEL_THR) && (gyroMag < ZUPT_GYRO_THR);

    if (still) { if (zuptTicks < ZUPT_HOLD) zuptTicks++; }
    else       { if (zuptTicks > 0)         zuptTicks--; }

    bool stationary = (zuptTicks >= ZUPT_HOLD);

    if (stationary) {
        vx = vy = vz = 0.0f;
        if (!wasStationary) logWaypoint();  // auto-log on leading edge of stillness
    } else {
        vx += wax * DT;
        vy += way * DT;
        vz += waz * DT;
    }
    wasStationary = stationary;

    float dx = vx * DT;
    float dy = vy * DT;
    float dz = vz * DT;
    px += dx;
    py += dy;
    pz += dz;
    totalDist += sqrtf(dx*dx + dy*dy + dz*dz);
}
