#include <AccelStepper.h>

#define STEP_PIN 2
#define DIR_PIN 3

AccelStepper stepper(AccelStepper::DRIVER, STEP_PIN, DIR_PIN);

#define STEPS_PER_MM 3200  

float distances[] = {1, 1, 1.5, 1.5, 1, 1};
float times[]     = {100,150,200,300,400,800};

int totalStages = 6;
int stage = 0;
bool stageRunning = false;
bool testingStarted = false;

void setup() {
  Serial.begin(9600);
  pinMode(DIR_PIN, OUTPUT);
  digitalWrite(DIR_PIN, HIGH);
  stepper.setAcceleration(300);
  
  Serial.println("Waiting for 'START' command from Python...");
}

void loop() {
  // Wait for serial start signal
  if (!testingStarted) {
    if (Serial.available() > 0) {
      String msg = Serial.readStringUntil('\n');
      msg.trim();
      if (msg == "START") {
        Serial.println("START received! Motor running.");
        testingStarted = true;
      }
    }
    return; // Don't run motor until started
  }

  if (stage < totalStages) {
    if (!stageRunning) {
      float mm = distances[stage];
      float time_sec = times[stage];
      long steps = mm * STEPS_PER_MM;
      float speed = steps / time_sec;

      if (speed < 10) speed = 10;
      stepper.setMaxSpeed(speed);
      stepper.move(steps);
      stageRunning = true;

      Serial.print("Stage ");
      Serial.print(stage + 1);
      Serial.print(" | Steps: ");
      Serial.print(steps);
      Serial.print(" | Speed: ");
      Serial.println(speed);
    }

    stepper.run();

    if (stepper.distanceToGo() == 0) {
      stage++;
      stageRunning = false;
    }
  }
}
