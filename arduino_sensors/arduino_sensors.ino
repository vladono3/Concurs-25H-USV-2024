#include <Adafruit_Sensor.h>
#include <Arduino.h>
#include <DHT.h>
#include <ArduinoJson.h>

#define DHTPIN1 14     // Pin connected to DHT11/DHT22 Data pin for Sensor 1
#define DHTTYPE1 DHT11 // Change to DHT22 if you're using it

#define DHTPIN2 12     // Pin connected to DHT11/DHT22 Data pin for Sensor 2
#define DHTTYPE2 DHT11 // Change to DHT22 if you're using it

#define MIC_PIN A0     // Microphone analog pin
#define LED_PIN1 4     // LED pin for Sensor 1
#define LED_PIN2 13    // LED pin for Sensor 2

// Reference value for calibration (adjust based on your setup)
const float REFERENCE_VALUE = 1; // Max value for a 10-bit ADC (0–1023)


// Variables to track reading positions
int currentReadingIndex = 0;
unsigned long lastReadingTime = 0;
unsigned long lastPrintTime = 0;
const unsigned long readingInterval = 10000; // 1 minute
const unsigned long printInterval = 10000; // 1 minute

DHT dht1(DHTPIN1, DHTTYPE1);
DHT dht2(DHTPIN2, DHTTYPE2);

bool complexSensor1Active = false;
bool complexSensor2Active = false;
String errorMessage = ""; // To store any error messages

void setup() {
  Serial.begin(115200);
  dht1.begin();
  dht2.begin();

  pinMode(LED_PIN1, OUTPUT);
  pinMode(LED_PIN2, OUTPUT);
  pinMode(MIC_PIN, INPUT);

  Serial.println("ESP8266 Sensor Monitoring Starting...");
}

void loop() {
  // Create JSON object for output
    StaticJsonDocument<1024> jsonDoc;
  // Check for serial input to toggle sensors
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim(); // Remove any trailing newline or spaces

    if (command == "activate sensor 1") {
      complexSensor1Active = true;
    } else if (command == "deactivate sensor 1") {
      complexSensor1Active = false;
    } else if (command == "activate sensor 2") {
      complexSensor2Active = true;
    } else if (command == "deactivate sensor 2") {
      complexSensor2Active = false;
    } else if (command == "deactivate sensors") {
      complexSensor1Active = false;
      complexSensor2Active = false;
    }
  }

  // Check if it's time to take a reading
  unsigned long currentMillis = millis();
  if (currentMillis - lastReadingTime >= readingInterval) {
    lastReadingTime = currentMillis;
    errorMessage = ""; // Reset error message for the new reading cycle

    // Read data from Sensor 1 if active
    if (complexSensor1Active) {
      digitalWrite(LED_PIN1, HIGH);
      float temperature1 = dht1.readTemperature();
      float humidity1 = dht1.readHumidity();
      if (!isnan(temperature1) && !isnan(humidity1)) {
        jsonDoc["sensor 1"]["temperature"] = temperature1;
        jsonDoc["sensor 1"]["humidity"] = humidity1;
        jsonDoc["sensor 1"]["activated"] = true;
      } else {
        errorMessage += "Error reading from Sensor 1; ";
      }
    } else {
      digitalWrite(LED_PIN1, LOW);
    }

    // Read data from Sensor 2 if active
    if (complexSensor2Active) {
      digitalWrite(LED_PIN2, HIGH);
      float temperature2 = dht2.readTemperature();
      float humidity2 = dht2.readHumidity();
      if (!isnan(temperature2) && !isnan(humidity2)) {
        jsonDoc["sensor 2"]["temperature"] = temperature2;
        jsonDoc["sensor 2"]["humidity"] = humidity2;
        jsonDoc["sensor 2"]["activated"] = true;
      } else {
        errorMessage += "Error reading from Sensor 2; ";
      }
    } else {
      digitalWrite(LED_PIN2, LOW);
    }

    // Read and store microphone data
    int micValue = analogRead(MIC_PIN);
    float dB = 20 * log10(micValue / REFERENCE_VALUE);
    // Include noise level
    jsonDoc["noise"] = dB;
  }

  // Print the readings in JSON format every minute
  if (currentMillis - lastPrintTime >= printInterval) {
    lastPrintTime = currentMillis;

    // Include temperature and humidity for each active sensor
    if (!complexSensor1Active){
      jsonDoc["sensor 1"]["temperature"] = 0;
      jsonDoc["sensor 1"]["humidity"] = 0;
      jsonDoc["sensor 1"]["activated"] = false;
    }

    if (!complexSensor2Active){
      jsonDoc["sensor 2"]["temperature"] = 0;
      jsonDoc["sensor 2"]["humidity"] = 0;
      jsonDoc["sensor 2"]["activated"] = false;
    }

    // Add any error message if exists
    jsonDoc["error"] = errorMessage.isEmpty() ? "" : errorMessage;

    // Print JSON output
    serializeJson(jsonDoc, Serial);
    Serial.println();
  }
}
