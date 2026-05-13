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
 *   Power-on  — runs a 3-second bias calibration. DO NOT MOVE the device,
 *               and place it FLAT (Z axis up) so accel reads (0,0,+9.81 m/s²).
 *   Button A  — start / stop a measurement session
 *   Button B  — short press: log a corner waypoint
 *               long  press (>1.5 s in IDLE): magnetometer hard-iron calibration
 *               (slowly rotate CLUE through every orientation for 25 s)
 *   Auto-log  — a waypoint is also logged whenever the device goes still
 *
 * Fine-tuning applied:
 *   * Gyro + accel bias calibration on startup
 *   * Magnetometer hard-iron calibration via long-press
 *   * Tighter accel range (±2 g) + gyro range (±500 dps) for better resolution
 *   * 208 Hz IMU sampling, 155 Hz mag w/ ultra-high performance
 *   * 6-DOF fallback (no mag) until mag-cal is performed
 *   * Soft velocity damping between ZUPT events
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
// CLUE display is on SPI1, not the default SPI bus
Adafruit_ST7789 tft(&SPI1, PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);

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
// Thresholds tightened after bias calibration is applied
static const float ZUPT_ACCEL_THR = 0.07f;  // m/s² deviation from g
static const float ZUPT_GYRO_THR  = 0.025f; // rad/s total magnitude
static const int   ZUPT_HOLD      = 8;       // consecutive 100-Hz ticks (~80 ms)
// Soft velocity damping per tick when slow but not fully stationary
static const float VEL_DAMP       = 0.985f;

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

// ── Sensor biases (computed at startup / via mag-cal long-press) ─────────────
float gyroBiasX  = 0, gyroBiasY  = 0, gyroBiasZ  = 0;
float accelBiasX = 0, accelBiasY = 0, accelBiasZ = 0;
float magOffX    = 0, magOffY    = 0, magOffZ    = 0;
bool  magCalibrated = false;

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
    } else if (force) {
        // IDLE hints + mag-cal status
        tft.fillRect(0, 170, 240, 60, ST77XX_BLACK);
        tft.setTextSize(1);
        tft.setTextColor(0x7BEF);
        tft.setCursor(4, 178);
        tft.print("[A] start   [B] waypoint");
        tft.setCursor(4, 196);
        tft.setTextColor(magCalibrated ? ST77XX_GREEN : 0xFC00);
        tft.print(magCalibrated ? "Mag: calibrated" : "Mag: hold B 1.5s in IDLE");
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

// ── Gyro + accelerometer bias calibration ────────────────────────────────────
// Device MUST be sitting flat & still during this routine.
// Computes the average reading of each axis and treats it as a bias.
// Accelerometer assumes +Z is up, so 9.81 is subtracted from the Z average.
void calibrateBiases() {
    tft.fillScreen(ST77XX_BLACK);
    tft.setTextSize(2);
    tft.setTextColor(ST77XX_YELLOW);
    tft.setCursor(20, 50);
    tft.print("CALIBRATING");
    tft.setCursor(40, 80);
    tft.print("HOLD STILL");
    tft.setTextSize(1);
    tft.setTextColor(ST77XX_WHITE);
    tft.setCursor(20, 120);
    tft.print("Place flat, do not move");
    delay(800);  // settling

    const int N = 500;
    double sgX = 0, sgY = 0, sgZ = 0;
    double saX = 0, saY = 0, saZ = 0;
    sensors_event_t aEv, gEv, tEv;
    int barW = 0;

    for (int i = 0; i < N; i++) {
        imu.getEvent(&aEv, &gEv, &tEv);
        sgX += gEv.gyro.x;
        sgY += gEv.gyro.y;
        sgZ += gEv.gyro.z;
        saX += aEv.acceleration.x;
        saY += aEv.acceleration.y;
        saZ += aEv.acceleration.z;
        int newBar = (i + 1) * 200 / N;
        if (newBar > barW) {
            tft.fillRect(20, 160, newBar, 12, ST77XX_GREEN);
            barW = newBar;
        }
        delay(5);  // ~200 Hz
    }

    gyroBiasX  = sgX / N;
    gyroBiasY  = sgY / N;
    gyroBiasZ  = sgZ / N;
    accelBiasX = saX / N;
    accelBiasY = saY / N;
    accelBiasZ = (saZ / N) - 9.81f;

    Serial.print("Gyro bias (rad/s):  ");
    Serial.print(gyroBiasX, 4); Serial.print(" ");
    Serial.print(gyroBiasY, 4); Serial.print(" ");
    Serial.println(gyroBiasZ, 4);
    Serial.print("Accel bias (m/s2): ");
    Serial.print(accelBiasX, 3); Serial.print(" ");
    Serial.print(accelBiasY, 3); Serial.print(" ");
    Serial.println(accelBiasZ, 3);

    tft.fillScreen(ST77XX_BLACK);
    tft.setTextSize(2);
    tft.setTextColor(ST77XX_GREEN);
    tft.setCursor(40, 100);
    tft.print("CAL DONE");
    delay(700);
}

// ── Magnetometer hard-iron calibration (long-press B in IDLE) ────────────────
// User rotates the device through all orientations for ~25 s; we capture
// min/max of each axis and compute the center as the hard-iron offset.
void calibrateMagnetometer() {
    tft.fillScreen(ST77XX_BLACK);
    tft.setTextSize(2);
    tft.setTextColor(ST77XX_YELLOW);
    tft.setCursor(50, 20);
    tft.print("MAG CAL");
    tft.setTextSize(1);
    tft.setTextColor(ST77XX_WHITE);
    tft.setCursor(10, 60);
    tft.print("Slowly rotate CLUE");
    tft.setCursor(10, 75);
    tft.print("through every");
    tft.setCursor(10, 90);
    tft.print("orientation (figure-8");
    tft.setCursor(10, 105);
    tft.print("in all 3 axes).");

    float mxMin =  1e6, mxMax = -1e6;
    float myMin =  1e6, myMax = -1e6;
    float mzMin =  1e6, mzMax = -1e6;
    const uint32_t DURATION = 25000;
    uint32_t start = millis();
    sensors_event_t mEv;
    int barW = 0;

    while (millis() - start < DURATION) {
        mag.getEvent(&mEv);
        float mx = mEv.magnetic.x, my = mEv.magnetic.y, mz = mEv.magnetic.z;
        if (mx < mxMin) mxMin = mx;  if (mx > mxMax) mxMax = mx;
        if (my < myMin) myMin = my;  if (my > myMax) myMax = my;
        if (mz < mzMin) mzMin = mz;  if (mz > mzMax) mzMax = mz;

        int newBar = (millis() - start) * 220 / DURATION;
        if (newBar > barW) {
            tft.fillRect(10, 180, newBar, 12, ST77XX_GREEN);
            barW = newBar;
        }
        delay(15);
    }

    magOffX = (mxMin + mxMax) * 0.5f;
    magOffY = (myMin + myMax) * 0.5f;
    magOffZ = (mzMin + mzMax) * 0.5f;
    magCalibrated = true;

    Serial.print("Mag offsets (uT): ");
    Serial.print(magOffX, 2); Serial.print(" ");
    Serial.print(magOffY, 2); Serial.print(" ");
    Serial.println(magOffZ, 2);

    tft.fillScreen(ST77XX_BLACK);
    tft.setTextSize(2);
    tft.setTextColor(ST77XX_GREEN);
    tft.setCursor(20, 100);
    tft.print("MAG CAL OK");
    delay(800);
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

    // BMP280 chip-ID probe — some CLUE units have 0x58, others 0x60
    Wire.beginTransmission(0x77);
    Wire.write(0xD0);
    Wire.endTransmission();
    Wire.requestFrom((uint8_t)0x77, (uint8_t)1);
    uint8_t baroChipId = Wire.available() ? Wire.read() : 0;
    Serial.print("Baro chip ID: 0x"); Serial.println(baroChipId, HEX);

    bool baroOk = baro.begin(0x77, baroChipId);
    Serial.println(baroOk ? "Baro OK" : "Baro fail (elevation disabled)");

    // Tighter range on accel = better resolution for small movements.
    // Faster ODR + hardware filter = lower aliasing.
    imu.setAccelRange(LSM6DS_ACCEL_RANGE_2_G);
    imu.setAccelDataRate(LSM6DS_RATE_208_HZ);
    imu.setGyroRange(LSM6DS_GYRO_RANGE_500_DPS);   // 500 dps is more than enough for handheld
    imu.setGyroDataRate(LSM6DS_RATE_208_HZ);

    mag.setDataRate(LIS3MDL_DATARATE_155_HZ);
    mag.setRange(LIS3MDL_RANGE_4_GAUSS);
    mag.setPerformanceMode(LIS3MDL_ULTRAHIGHMODE);
    mag.setOperationMode(LIS3MDL_CONTINUOUSMODE);
    Serial.println("Sensors configured");

    pinMode(PIN_BUTTON1, INPUT_PULLUP);
    pinMode(PIN_BUTTON2, INPUT_PULLUP);

    // Bias calibration — device must be flat and still for ~3 s
    calibrateBiases();

    Serial.println("Starting BLE...");
    Bluefruit.begin();
    Bluefruit.setName("Moasure-DIY");
    Serial.println("BLE init done");

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
    Serial.println("BLE chars done");

    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addService(measSvc);
    Bluefruit.ScanResponse.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(32, 244);
    Bluefruit.Advertising.setFastTimeout(30);
    Bluefruit.Advertising.start(0);
    Serial.println("Advertising");

    resetMeasurement();
    Serial.println("Reset done");
    tft.fillScreen(ST77XX_BLACK);
    refreshDisplay(true);
    Serial.println("Display drawn");

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

    // Button B — short press = manual waypoint, long press (>1.5s) = mag cal
    static bool     prevB           = HIGH;
    static uint32_t bDownMs         = 0;
    static bool     bLongHandled    = false;
    bool curB = digitalRead(PIN_BUTTON2);
    if (prevB && !curB) {                // press edge
        bDownMs = millis();
        bLongHandled = false;
    }
    if (!curB && !bLongHandled && (millis() - bDownMs > 1500)) {
        // Long-press fired while still held — only in IDLE for safety
        if (measState == IDLE) {
            calibrateMagnetometer();
            refreshDisplay(true);
        }
        bLongHandled = true;
    }
    if (!prevB && curB) {                // release edge
        if (!bLongHandled && measState == MEASURING) {
            logWaypoint();
            refreshDisplay();
        }
    }
    prevB = curB;

    // 100 Hz sensor tick
    if ((int32_t)(micros() - nextLoopUs) < 0) return;
    nextLoopUs += (uint32_t)(DT * 1.0e6f);

    // Read IMU + apply calibrated biases
    sensors_event_t aEv, gEv, tEv;
    imu.getEvent(&aEv, &gEv, &tEv);
    float ax = aEv.acceleration.x - accelBiasX;
    float ay = aEv.acceleration.y - accelBiasY;
    float az = aEv.acceleration.z - accelBiasZ;
    float gx = gEv.gyro.x - gyroBiasX;
    float gy = gEv.gyro.y - gyroBiasY;
    float gz = gEv.gyro.z - gyroBiasZ;

    // Read magnetometer + apply hard-iron offsets
    sensors_event_t mEv;
    mag.getEvent(&mEv);
    float mx = mEv.magnetic.x - magOffX;
    float my = mEv.magnetic.y - magOffY;
    float mz = mEv.magnetic.z - magOffZ;

    // Madgwick update — feed mag only if calibrated, else fall back to 6-DOF
    // (uncalibrated mag actively HURTS yaw because of hard-iron bias).
    if (magCalibrated) {
        ahrs.update(gx, gy, gz, ax, ay, az, mx, my, mz);
    } else {
        ahrs.updateIMU(gx, gy, gz, ax, ay, az);
    }

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
        // Partial damping when we're trending toward still — kills residual
        // drift between explicit ZUPT events without affecting real motion.
        if (zuptTicks >= ZUPT_HOLD / 2) {
            vx *= VEL_DAMP;
            vy *= VEL_DAMP;
            vz *= VEL_DAMP;
        }
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
