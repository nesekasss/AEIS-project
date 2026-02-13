#include "DHT.h"
#include <Wire.h>
#include <math.h>

#define MQ2_PIN   34
#define DHT_PIN   27
#define DHT_TYPE  DHT22
#define LDR_PIN   35

#define US_TRIG_PIN 5
#define US_ECHO_PIN 18

#define LED_GREEN 16
#define LED_YELLOW 17
#define LED_RED   19

#define MPU_ADDR 0x68


#define FAN_PIN LED_RED

DHT dht(DHT_PIN, DHT_TYPE);


const int MQ2_WARN_UP   = 1200;
const int MQ2_WARN_DOWN = 1000;

const int MQ2_HAZ_UP    = 2200;
const int MQ2_HAZ_DOWN  = 1900;

const int LDR_DARK_THRESHOLD = 1200;

const unsigned long WARN_CONFIRM_MS  = 4000;
const unsigned long HAZ_CONFIRM_MS   = 3000;

const unsigned long DHT_STALE_MS = 8000;

const long DIST_NEAR_CM = 20;
const long DIST_TIMEOUT_US = 30000;

const long SHOCK_THRESHOLD = 25000;
const unsigned long SHOCK_CONFIRM_MS = 500;


bool JSON_ONLY = true;


enum EnvState { ENV_NORMAL, ENV_WARNING, ENV_HAZARD };
enum SysHealth { SYS_OK, SYS_DEGRADED, SYS_SHOCK };

struct SensorData {
  int mq2Avg;
  int ldrAvg;
  bool isDark;

  float tempC;
  float humPct;
  bool dhtOk;
  unsigned long lastDhtOkMs;

  long distanceCm;

  int ax, ay, az;
  long accelMag;
  bool shockRaw;
};

struct AISStatus {
  EnvState env;
  SysHealth sys;

  float confidence;
  bool dhtFault;
  bool shockConfirmed;
};

unsigned long g_lastDhtOkMs = 0;

EnvState g_candidateEnv = ENV_NORMAL;
unsigned long g_candidateSinceMs = 0;
EnvState g_confirmedEnv = ENV_NORMAL;

bool g_shockCandidate = false;
unsigned long g_shockSinceMs = 0;
bool g_shockConfirmed = false;

bool g_fanOn = false;


int readAnalogAveraged(int pin, int samples = 20) {
  long sum = 0;
  for (int i = 0; i < samples; i++) {
    sum += analogRead(pin);
    delay(5);
  }
  return (int)(sum / samples);
}

const char* envToStr(EnvState s) {
  switch (s) {
    case ENV_NORMAL: return "NORMAL";
    case ENV_WARNING: return "WARNING";
    case ENV_HAZARD: return "HAZARD";
    default: return "UNKNOWN";
  }
}

const char* sysToStr(SysHealth h) {
  switch (h) {
    case SYS_OK: return "OK";
    case SYS_DEGRADED: return "DEGRADED";
    case SYS_SHOCK: return "SHOCK";
    default: return "UNKNOWN";
  }
}

void setLeds(EnvState st) {
  digitalWrite(LED_GREEN,  st == ENV_NORMAL ? HIGH : LOW);
  digitalWrite(LED_YELLOW, st == ENV_WARNING ? HIGH : LOW);
  digitalWrite(LED_RED,    st == ENV_HAZARD ? HIGH : LOW);
}

void setFan(bool on) {
  g_fanOn = on;
  digitalWrite(FAN_PIN, on ? HIGH : LOW);
}

float clamp01(float x) {
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}


long readDistanceCM() {
  digitalWrite(US_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(US_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(US_TRIG_PIN, LOW);

  unsigned long duration = pulseIn(US_ECHO_PIN, HIGH, DIST_TIMEOUT_US);
  if (duration == 0) return -1;

  return (long)(duration * 0.0343 / 2.0);
}

void initMPU() {
  Wire.begin();
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  Wire.endTransmission(true);
}

bool readMPUAccel(int &ax, int &ay, int &az) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;

  Wire.requestFrom(MPU_ADDR, 6, true);
  if (Wire.available() < 6) return false;

  ax = (Wire.read() << 8) | Wire.read();
  ay = (Wire.read() << 8) | Wire.read();
  az = (Wire.read() << 8) | Wire.read();
  return true;
}

long accelMagnitude(int ax, int ay, int az) {
  long x = ax, y = ay, z = az;
  return (long)sqrt((double)(x*x + y*y + z*z));
}


SensorData readSensors() {
  SensorData s;

  s.mq2Avg = readAnalogAveraged(MQ2_PIN, 20);
  s.ldrAvg = readAnalogAveraged(LDR_PIN, 20);
  s.isDark = (s.ldrAvg < LDR_DARK_THRESHOLD);

  s.distanceCm = readDistanceCM();

  float t = dht.readTemperature();
  float h = dht.readHumidity();

  unsigned long now = millis();
  bool ok = !(isnan(t) || isnan(h));

  s.dhtOk = ok;
  if (ok) {
    s.tempC = t;
    s.humPct = h;
    g_lastDhtOkMs = now;
  } else {
    s.tempC = NAN;
    s.humPct = NAN;
  }
  s.lastDhtOkMs = g_lastDhtOkMs;

  int ax, ay, az;
  bool mpuOk = readMPUAccel(ax, ay, az);
  if (mpuOk) {
    s.ax = ax; s.ay = ay; s.az = az;
    s.accelMag = accelMagnitude(ax, ay, az);
    s.shockRaw = (s.accelMag > SHOCK_THRESHOLD);
  } else {
    s.ax = s.ay = s.az = 0;
    s.accelMag = 0;
    s.shockRaw = false;
  }

  return s;
}

EnvState rawDecisionWithHysteresis(const SensorData& s, EnvState prevConfirmed) {
  EnvState gasLevel = prevConfirmed;

  if (prevConfirmed == ENV_NORMAL) {
    if (s.mq2Avg >= MQ2_HAZ_UP) gasLevel = ENV_HAZARD;
    else if (s.mq2Avg >= MQ2_WARN_UP) gasLevel = ENV_WARNING;
  }
  else if (prevConfirmed == ENV_WARNING) {
    if (s.mq2Avg >= MQ2_HAZ_UP) gasLevel = ENV_HAZARD;
    else if (s.mq2Avg <= MQ2_WARN_DOWN) gasLevel = ENV_NORMAL;
  }
  else {
    if (s.mq2Avg <= MQ2_HAZ_DOWN) {
      if (s.mq2Avg >= MQ2_WARN_UP) gasLevel = ENV_WARNING;
      else gasLevel = ENV_NORMAL;
    }
  }

  if (s.isDark && gasLevel == ENV_WARNING) gasLevel = ENV_HAZARD;

  if (s.distanceCm > 0 && s.distanceCm < DIST_NEAR_CM && gasLevel == ENV_WARNING) {
    gasLevel = ENV_HAZARD;
  }

  return gasLevel;
}

EnvState confirmByTime(EnvState candidate, unsigned long nowMs) {
  if (candidate != g_candidateEnv) {
    g_candidateEnv = candidate;
    g_candidateSinceMs = nowMs;
    return g_confirmedEnv;
  }

  if (candidate == g_confirmedEnv) return g_confirmedEnv;

  unsigned long elapsed = nowMs - g_candidateSinceMs;

  if (candidate == ENV_WARNING && elapsed >= WARN_CONFIRM_MS) {
    g_confirmedEnv = ENV_WARNING;
  } else if (candidate == ENV_HAZARD && elapsed >= HAZ_CONFIRM_MS) {
    g_confirmedEnv = ENV_HAZARD;
  } else if (candidate == ENV_NORMAL) {
    g_confirmedEnv = ENV_NORMAL;
  }

  return g_confirmedEnv;
}


float computeConfidence(const SensorData& s, EnvState env, bool dhtFault) {
  float conf = 0.5f;

  if (env == ENV_NORMAL) {
    conf = 1.0f - clamp01((float)s.mq2Avg / (float)MQ2_WARN_UP);
  } else if (env == ENV_WARNING) {
    float span = (float)(MQ2_HAZ_UP - MQ2_WARN_UP);
    conf = clamp01(((float)s.mq2Avg - (float)MQ2_WARN_UP) / (span > 1 ? span : 1));
    conf = 0.6f + 0.4f * conf;
  } else {
    float span = 1200.0f;
    conf = clamp01(((float)s.mq2Avg - (float)MQ2_HAZ_UP) / span);
    conf = 0.7f + 0.3f * conf;
  }

  if (s.isDark && env != ENV_NORMAL) conf = clamp01(conf + 0.08f);

  if (s.distanceCm > 0 && s.distanceCm < DIST_NEAR_CM && env != ENV_NORMAL) {
    conf = clamp01(conf + 0.05f);
  }

  if (dhtFault) conf = clamp01(conf - 0.15f);

  return conf;
}


AISStatus evaluateStatus(const SensorData& s) {
  AISStatus st;

  unsigned long now = millis();

  bool dhtFault = (now - s.lastDhtOkMs) > DHT_STALE_MS;
  st.dhtFault = dhtFault;

  if (s.shockRaw != g_shockCandidate) {
    g_shockCandidate = s.shockRaw;
    g_shockSinceMs = now;
  } else {
    if (g_shockCandidate && (now - g_shockSinceMs) >= SHOCK_CONFIRM_MS) {
      g_shockConfirmed = true;
    }
    if (!g_shockCandidate) {
      g_shockConfirmed = false;
    }
  }
  st.shockConfirmed = g_shockConfirmed;

  st.sys = dhtFault ? SYS_DEGRADED : SYS_OK;
  if (g_shockConfirmed) st.sys = SYS_SHOCK;

  EnvState raw = rawDecisionWithHysteresis(s, g_confirmedEnv);
  EnvState confirmed = confirmByTime(raw, now);
  st.env = confirmed;

  st.confidence = computeConfidence(s, st.env, dhtFault);

  return st;
}


String readSerialLine() {
  static String buf = "";
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      String line = buf;
      buf = "";
      line.trim();
      return line;
    }
    buf += c;
    if (buf.length() > 512) buf = ""; /
  }
  return "";
}


void handleJsonCommandLine(const String& line) {
  if (line.length() == 0) return;


  if (line == "JSON_ONLY=1") { JSON_ONLY = true; return; }
  if (line == "JSON_ONLY=0") { JSON_ONLY = false; return; }

  bool isCmd = (line.indexOf("\"type\"") >= 0 && line.indexOf("cmd") >= 0);
  if (!isCmd) return;


  if (line.indexOf("\"cmd\":\"fan_set\"") >= 0) {
    int i = line.indexOf("\"value\":");
    int val = 0;
    if (i >= 0) val = line.substring(i + 8).toInt();
    setFan(val != 0);
    Serial.print("{\"type\":\"ack\",\"cmd\":\"fan_set\",\"value\":");
    Serial.print(g_fanOn ? 1 : 0);
    Serial.println("}");
    return;
  }

 
  if (line.indexOf("\"cmd\":\"json_only\"") >= 0) {
    int i = line.indexOf("\"value\":");
    int val = 0;
    if (i >= 0) val = line.substring(i + 8).toInt();
    JSON_ONLY = (val != 0);
    Serial.print("{\"type\":\"ack\",\"cmd\":\"json_only\",\"value\":");
    Serial.print(JSON_ONLY ? 1 : 0);
    Serial.println("}");
    return;
  }

  Serial.println("{\"type\":\"error\",\"msg\":\"unknown_cmd\"}");
}

void printJsonTelemetry(const SensorData& s, const AISStatus& st) {
  Serial.print("{\"type\":\"telemetry\"");
  Serial.print(",\"ts_ms\":"); Serial.print(millis());
  Serial.print(",\"mq2\":"); Serial.print(s.mq2Avg);
  Serial.print(",\"ldr\":"); Serial.print(s.ldrAvg);
  Serial.print(",\"dark\":"); Serial.print(s.isDark ? "true" : "false");
  Serial.print(",\"dist_cm\":"); Serial.print(s.distanceCm);
  Serial.print(",\"acc\":"); Serial.print(s.accelMag);
  Serial.print(",\"shock_raw\":"); Serial.print(s.shockRaw ? "true" : "false");
  Serial.print(",\"shock_confirmed\":"); Serial.print(st.shockConfirmed ? "true" : "false");
  Serial.print(",\"env\":\""); Serial.print(envToStr(st.env)); Serial.print("\"");
  Serial.print(",\"sys\":\""); Serial.print(sysToStr(st.sys)); Serial.print("\"");
  Serial.print(",\"confidence\":"); Serial.print(st.confidence, 3);
  Serial.print(",\"fan\":"); Serial.print(g_fanOn ? 1 : 0);

  Serial.print(",\"dht_ok\":"); Serial.print(s.dhtOk ? "true" : "false");
  if (s.dhtOk) {
    Serial.print(",\"temp_c\":"); Serial.print(s.tempC, 2);
    Serial.print(",\"hum_pct\":"); Serial.print(s.humPct, 2);
  }
  Serial.println("}");
}


void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(MQ2_PIN, INPUT);
  pinMode(LDR_PIN, INPUT);

  pinMode(US_TRIG_PIN, OUTPUT);
  pinMode(US_ECHO_PIN, INPUT);

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED, OUTPUT);

  pinMode(FAN_PIN, OUTPUT);
  setFan(false);

  dht.begin();
  g_lastDhtOkMs = millis();

  initMPU();


  Serial.println("{\"type\":\"hello\",\"device\":\"AIS2\",\"v\":\"0.5\",\"baud\":115200}");

  if (!JSON_ONLY) {
    Serial.println("AIS2 v0.5: MQ2 + DHT22 + LDR + HC-SR04 + MPU6050 | JSONL enabled");
    Serial.println("Open Serial Plotter. Look for lines starting with PLOT:");
  }
}

void loop() {

  String cmdLine = readSerialLine();
  if (cmdLine.length() > 0) {
    handleJsonCommandLine(cmdLine);
  }

  SensorData s = readSensors();
  AISStatus st = evaluateStatus(s);

 
  setLeds(st.env);


  if (st.confidence < 0.60f) setFan(true);


  if (!JSON_ONLY) {
    Serial.println("------ AIS2 STATUS ------");
    Serial.print("ENV: "); Serial.print(envToStr(st.env));
    Serial.print(" | SYS: "); Serial.print(sysToStr(st.sys));
    Serial.print(" | confidence: "); Serial.println(st.confidence, 2);

    Serial.print("MQ2 avg: "); Serial.println(s.mq2Avg);
    Serial.print("LDR avg: "); Serial.print(s.ldrAvg);
    Serial.print(" | light: "); Serial.println(s.isDark ? "DARK" : "BRIGHT");
    Serial.print("Distance (cm): "); Serial.println(s.distanceCm);

    Serial.print("AccelMag: "); Serial.print(s.accelMag);
    Serial.print(" | shockRaw: "); Serial.print(s.shockRaw ? "YES" : "NO");
    Serial.print(" | shockConfirmed: "); Serial.println(st.shockConfirmed ? "YES" : "NO");

    if (s.dhtOk) {
      Serial.print("Temp (C): "); Serial.println(s.tempC);
      Serial.print("Humidity (%): "); Serial.println(s.humPct);
    } else {
      Serial.println("DHT read: invalid (NaN) this cycle");
    }

    Serial.print("DHT fault: "); Serial.println(st.dhtFault ? "YES" : "NO");
    Serial.println("-------------------------\n");

    Serial.print("PLOT ");
    Serial.print("mq2:"); Serial.print(s.mq2Avg); Serial.print(" ");
    Serial.print("ldr:"); Serial.print(s.ldrAvg); Serial.print(" ");
    Serial.print("dist:"); Serial.print(s.distanceCm); Serial.print(" ");
    Serial.print("acc:"); Serial.print(s.accelMag); Serial.print(" ");
    Serial.print("env:"); Serial.print((int)st.env); Serial.print(" ");
    Serial.print("sys:"); Serial.print((int)st.sys); Serial.print(" ");
    Serial.print("conf:"); Serial.println(st.confidence, 2);
  }


  printJsonTelemetry(s, st);

  delay(2000);
}
