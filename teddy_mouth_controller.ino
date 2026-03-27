/*
 * Teddy Mouth Controller (PCA9685 edition)
 *
 * Keeps the existing Windows bridge protocol:
 *   ANGLE <n>\n
 *
 * Logical range:
 *   4  = closed mouth
 *   12 = open mouth
 *
 * Hardware:
 * - Arduino Nano on USB serial at 9600 baud
 * - PCA9685 on I2C
 * - Mouth servo on PCA9685 channel 0
 *
 * Required Arduino libraries:
 * - Adafruit PWM Servo Driver Library
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Serial protocol settings.
const long BAUD_RATE = 9600;
String inputString = "";
bool stringComplete = false;

// PCA9685 configuration.
const uint8_t PCA9685_ADDRESS = 0x40;
const uint8_t SERVO_CHANNEL = 0;
const uint16_t PWM_FREQUENCY = 60;
const uint16_t PULSE_MIN = 150;
const uint16_t PULSE_MAX = 600;

// Teddy logical mouth range expected by the PC bridge.
const int LOGICAL_MIN = 4;
const int LOGICAL_MAX = 12;
const int LOGICAL_CLOSED = 4;

// Servo pulse calibration for this specific mouth linkage.
// These values are intentionally easy to edit during calibration.
const uint16_t PULSE_CLOSED = 220;
const uint16_t PULSE_OPEN = 325;

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(PCA9685_ADDRESS);

void setup() {
  Serial.begin(BAUD_RATE);
  inputString.reserve(40);

  Wire.begin();
  pwm.begin();
  pwm.setPWMFreq(PWM_FREQUENCY);
  delay(10);

  setMouthAngle(LOGICAL_CLOSED);

  Serial.println("Teddy Mouth Controller initialized");
  printStatus();
}

void loop() {
  if (!stringComplete) {
    return;
  }

  processCommand(inputString);
  inputString = "";
  stringComplete = false;
}

void processCommand(String command) {
  command.trim();
  if (command.length() == 0) {
    return;
  }

  if (command.startsWith("ANGLE")) {
    int angleIndex = command.indexOf(' ');
    if (angleIndex == -1) {
      Serial.println("ERR missing angle");
      return;
    }

    String angleStr = command.substring(angleIndex + 1);
    int logicalAngle = angleStr.toInt();
    logicalAngle = constrain(logicalAngle, LOGICAL_MIN, LOGICAL_MAX);
    setMouthAngle(logicalAngle);

    Serial.print("OK angle ");
    Serial.print(logicalAngle);
    Serial.print(" pulse ");
    Serial.println(logicalToPulse(logicalAngle));
    return;
  }

  if (command.startsWith("PULSE")) {
    int pulseIndex = command.indexOf(' ');
    if (pulseIndex == -1) {
      Serial.println("ERR missing pulse");
      return;
    }

    String pulseStr = command.substring(pulseIndex + 1);
    int pulseValue = pulseStr.toInt();
    pulseValue = constrain(pulseValue, PULSE_MIN, PULSE_MAX);
    setMouthPulse((uint16_t)pulseValue);

    Serial.print("OK pulse ");
    Serial.println(pulseValue);
    return;
  }

  if (command.equalsIgnoreCase("STATUS")) {
    printStatus();
    return;
  }

  if (command.equalsIgnoreCase("OPEN")) {
    setMouthAngle(LOGICAL_MAX);
    Serial.println("OK open");
    return;
  }

  if (command.equalsIgnoreCase("CLOSE")) {
    setMouthAngle(LOGICAL_CLOSED);
    Serial.println("OK close");
    return;
  }

  Serial.print("ERR unknown command: ");
  Serial.println(command);
}

void setMouthAngle(int logicalAngle) {
  uint16_t pulse = logicalToPulse(logicalAngle);
  setMouthPulse(pulse);
}

void setMouthPulse(uint16_t pulse) {
  pwm.setPWM(SERVO_CHANNEL, 0, pulse);
}

uint16_t logicalToPulse(int logicalAngle) {
  logicalAngle = constrain(logicalAngle, LOGICAL_MIN, LOGICAL_MAX);
  long pulse = map(
    logicalAngle,
    LOGICAL_MIN,
    LOGICAL_MAX,
    PULSE_CLOSED,
    PULSE_OPEN
  );
  return (uint16_t)pulse;
}

void printStatus() {
  Serial.print("STATUS channel=");
  Serial.print(SERVO_CHANNEL);
  Serial.print(" logical=");
  Serial.print(LOGICAL_MIN);
  Serial.print("-");
  Serial.print(LOGICAL_MAX);
  Serial.print(" pulse=");
  Serial.print(PULSE_CLOSED);
  Serial.print("-");
  Serial.print(PULSE_OPEN);
  Serial.print(" raw=");
  Serial.print(PULSE_MIN);
  Serial.print("-");
  Serial.println(PULSE_MAX);
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    inputString += inChar;
    if (inChar == '\n') {
      stringComplete = true;
    }
  }
}
