# Arduino Nano ⇄ Raspberry Pi protocol

USB serial, **115200 baud**, plain text, one message per line ending in `\n`.

## Messages

| Direction | Message | Meaning |
|---|---|---|
| Nano → Pi | `READY` | Nano has booted (send once in `setup()`) |
| Nano → Pi | `SCAN <station> <side>` | "Photograph this plant now". Station = 1, 2, 3… Side = `A` or `B`. Example: `SCAN 3 A` |
| Pi → Nano | `CAPTURED <station> <side>` | Photos taken. Nano may now flip the camera / drive on |
| Pi → Nano | `ERR <station> <side> <reason>` | Photos failed (e.g. `ERR 3 A CAMERA`). Nano should carry on anyway |
| Nano → Pi | `STATE <name>` | *Optional.* Tell the dashboard what the robot is doing: `driving`, `stopped`, `idle`, `error` |

## The loop at each station

```
Nano: follow line … thick marker line → stop motors
Nano: wait ~400 ms (let the robot stop shaking)
Nano → Pi:  SCAN 3 A
Pi   → Nano: CAPTURED 3 A        (usually within ~0.2 s)
Nano: turn servo to side B, wait ~400 ms
Nano → Pi:  SCAN 3 B
Pi   → Nano: CAPTURED 3 B
Nano: turn servo back to side A, resume line-following
```

The Pi replies **as soon as the photos are taken**, before the AI runs. The AI works in the background, so the robot never waits for it.

## Rules for the Nano side

1. **Count stations yourself** (1, 2, 3…) and send the number in every `SCAN`.
2. **If no `CAPTURED` within 3 seconds**, send the same `SCAN` once more. The Pi recognises a repeat and won't take the photos twice. If there's still no answer, move on anyway: never freeze at the booth.
3. **Opening the USB port resets the Nano** (normal for Arduinos). The Pi opens it once at start-up and waits for `READY`, so just send `READY` at the end of `setup()`.
4. **Don't power the servo from the Nano's 5V pin**: servo current spikes can reset the Nano mid-demo. Use a separate 5V supply with a shared ground.
5. Anything else the Nano prints (debug text) is ignored by the Pi, but keep it short.

## Minimal Arduino example

```cpp
int station = 0;

bool waitCaptured(unsigned long ms) {
  unsigned long t = millis();
  while (millis() - t < ms) {
    if (Serial.available()) {
      String line = Serial.readStringUntil('\n');
      if (line.startsWith("CAPTURED") || line.startsWith("ERR")) return true;
    }
  }
  return false;
}

void scanSide(char side) {
  delay(400);                                   // let the robot settle
  Serial.print("SCAN "); Serial.print(station); Serial.print(' '); Serial.println(side);
  if (!waitCaptured(3000)) {                    // no answer: try once more
    Serial.print("SCAN "); Serial.print(station); Serial.print(' '); Serial.println(side);
    waitCaptured(3000);                         // then carry on regardless
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);
  // ... motors, sensors, servo ...
  Serial.println("READY");
}

// when the thick marker line is detected:
//   stopMotors(); station++;
//   servoToSideA(); scanSide('A');
//   servoToSideB(); scanSide('B');
//   servoToSideA(); resumeLineFollowing();
```
