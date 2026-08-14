#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>

#define DHTPIN 2
#define DHTTYPE DHT11
#define LCD_ADDR 0x27

DHT dht(DHTPIN, DHTTYPE);
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);

#define MAX_INPUT 64

char inputBuffer[MAX_INPUT];
int inputIndex = 0;
boolean stringComplete = false;
int cpuLoad = 0;
int ramLoad = 0;
bool statsReceived = false;
bool showError = false;
unsigned long lastStatsTime = 0;
const unsigned long statsTimeout = 2000;
float temperature = 0;
float humidity = 0;

unsigned long lastDHTRead = 0;
const unsigned long dhtInterval = 2000;

void setup() {
  Serial.begin(9600);
  dht.begin();
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(2, 0);
  lcd.print("system ready");
  delay(2000);
  lcd.clear();
  inputIndex = 0;
}

static bool parse_stats(const char *buf, int len, int &cpu, int &ram) {
  const char *p = buf;
  while ((int)(p - buf) < len - 4) {
    if (p[0] == 'C' && p[1] == 'P' && p[2] == 'U' && p[3] == ':') break;
    ++p;
  }
  if ((int)(p - buf) >= len - 4) return false;

  const char *cpuEnd = p + 4;
  while ((int)(cpuEnd - buf) < len && *cpuEnd != ';' && *cpuEnd != ',') ++cpuEnd;
  int cpuLen = cpuEnd - (p + 4);
  if (cpuLen <= 0 || cpuLen > 3) return false;

  char cpuStr[5] = {0};
  for (int i = 0; i < cpuLen && i < 4; ++i) cpuStr[i] = *(p + 4 + i);
  for (int i = 0; i < cpuLen; ++i) {
    if (cpuStr[i] < '0' || cpuStr[i] > '9') return false;
  }
  int val = atoi(cpuStr);
  if (val < 0 || val > 100) return false;

  const char *ramTag = p + 4 + cpuLen;
  if ((int)(ramTag - buf) >= len - 5) return false;
  if (strncmp(ramTag, ";RAM:", 5) != 0) return false;

  const char *ramEnd = ramTag + 5;
  while ((int)(ramEnd - buf) < len && *ramEnd != '\n' && *ramEnd != '\r') ++ramEnd;
  int ramLen = ramEnd - (ramTag + 5);
  if (ramLen <= 0 || ramLen > 3) return false;

  char ramStr[5] = {0};
  for (int i = 0; i < ramLen && i < 4; ++i) ramStr[i] = *(ramTag + 5 + i);
  for (int i = 0; i < ramLen; ++i) {
    if (ramStr[i] < '0' || ramStr[i] > '9') return false;
  }
  val = atoi(ramStr);
  if (val < 0 || val > 100) return false;

  cpu = atoi(cpuStr);
  ram = atoi(ramStr);
  return true;
}

void loop() {
  if (stringComplete) {
    int cpu = 0, ram = 0;
    if (parse_stats(inputBuffer, inputIndex, cpu, ram)) {
      cpuLoad = cpu;
      ramLoad = ram;
      statsReceived = true;
      lastStatsTime = millis();
      if (showError) {
        showError = false;
        lcd.clear();
      }
    } else {
      // невалидный пакет — сбрасываем таймер
      lastStatsTime = 0;
    }
    inputIndex = 0;
    stringComplete = false;
  }

  if (millis() - lastDHTRead >= dhtInterval) {
    lastDHTRead = millis();
    float newH = dht.readHumidity();
    float newT = dht.readTemperature();
    if (!isnan(newH) && !isnan(newT)) {
      humidity = newH;
      temperature = newT;
    }
  }

  unsigned long elapsed = millis() - lastStatsTime;
  bool timeout = statsReceived && (elapsed >= statsTimeout);

  if (timeout && !showError) {
    showError = true;
    lcd.clear();
    lcd.setCursor(3, 0);
    lcd.print("wire error");
  } else if (!showError && statsReceived) {
    lcd.setCursor(0, 0);
    lcd.print("CPU:");
    lcd.print(cpuLoad);
    lcd.print("% ");
    lcd.setCursor(10, 0);
    lcd.print("T:");
    lcd.print((int)temperature);
    lcd.print("C");

    lcd.setCursor(0, 1);
    lcd.print("RAM:");
    lcd.print(ramLoad);
    lcd.print("% ");
    lcd.setCursor(10, 1);
    lcd.print("H:");
    lcd.print((int)humidity);
    lcd.print("%");
  }
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      inputBuffer[inputIndex] = '\0';
      stringComplete = true;
    } else if (inputIndex < MAX_INPUT - 1) {
      inputBuffer[inputIndex++] = inChar;
    }
  }
}
