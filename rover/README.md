# The rover: live pothole avoidance on the 6-wheel UGV

The Jetson Orin Nano rides on the rover, reads the Logitech C920, runs Model P and Model B,
and drives the L298N motor driver straight from its 40-pin header, as the friend's Jetson
Xavier NX build did. The Orin Nano's header has the same layout, so the same BOARD pin numbers
apply. No ESP32 or CAN bus is needed to drive this rover; `--can vcan0` can still mirror every
decision as a CAN frame for the demo.

## 1. Wiring (battery switch OFF while wiring)

**L298N (red HW-095 board) ↔ Jetson 40-pin header** (BOARD numbers, printed beside the header):

| L298N | Goes to | Note |
|---|---|---|
| IN1 | Jetson pin **29** | left side, direction A |
| IN2 | Jetson pin **31** | left side, direction B |
| IN3 | Jetson pin **35** | right side, direction A |
| IN4 | Jetson pin **37** | right side, direction B |
| ENA, ENB | **jumpers fitted** (start here) | PWM mode instead: jumpers off, ENA → pin **32**, ENB → pin **33** |
| GND (screw terminal) | Jetson pin **30** **and** battery − | the common ground: without it the motors ignore the Jetson |
| +12V / VS (screw terminal) | battery + (through the switch) | **never** to the Jetson |
| +5V (screw terminal) | nothing | |
| 5V-enable jumper (beside the 3-way terminal) | leave fitted | the board's own logic supply, fine at ≤ 12 V |
| OUT1 / OUT2 | the three left motors, in parallel | |
| OUT3 / OUT4 | the three right motors, in parallel | |

**MPU6050 (blue GY-521, optional, for `--heading-hold`) ↔ Jetson:**

| GY-521 | Jetson pin | |
|---|---|---|
| VCC | **1** (3.3 V) | not 5 V |
| GND | **6** | |
| SDA | **3** | |
| SCL | **5** | i2c-7 on the Orin Nano (i2c-8 on the Xavier NX); found automatically |
| XDA, XCL, AD0, INT | nothing | |

**Webcam:** the C920 into any blue **USB-A** port (not the USB-C port). Mount it rigidly:
the planner's corridor assumes a fixed height and tilt (about 18–25 cm, 15° down).

## 2. Power

- **Bench test (Jetson on its wall adapter, motors on the battery): yes, safe.** The adapter's
  output floats, so joining Jetson GND (pin 30) to L298N GND is correct and required. Only the
  four IN wires (plus ENA/ENB in PWM mode) and GND go between them. Wheels off the ground.
- **The 2 × 18650 pack** (2S: 7.4 V nominal, 8.4 V full) **runs the motors only.** It is too low
  for the Jetson.
- **The Jetson on the rover needs its own supply** within the developer kit's DC-jack range
  (the kit ships with a 19 V adapter; check NVIDIA's spec for the accepted range before
  connecting anything else). A 3S LiPo (11.1 V nominal, 12.6 V full) with a 5.5 × 2.5 mm barrel
  plug, like the friend's orange pack, is the usual choice.
- The blue LM2596 buck converter is not needed; do not feed the Jetson from it.
- Before pulling the Jetson's power: `sudo shutdown now`.

## 3. Working from the Mac over SSH

1. **Once, on the Jetson** (with a monitor): `sudo systemctl enable --now ssh`. Join the same
   Wi-Fi as the Mac. If the lab network blocks devices from reaching each other, use the
   phone's hotspot for both. `hostname -I` shows the Jetson's address (it changes; today it
   was 172.16.61.115).
2. **On the Mac, Terminal:** `ssh host123@host123.local` (or `ssh host123@<address>`). Type
   `yes` the first time, then the Jetson's password.
3. Optional, no more passwords: `ssh-keygen -t ed25519`, then `ssh-copy-id host123@host123.local`.
4. Keep a run alive if Wi-Fi drops: on the Jetson `sudo apt install tmux`, then `tmux new -s
   rover`; detach with Ctrl-b then d; come back with `tmux attach -t rover`.
5. **Watch the camera:** while `pothole_drive.py` runs, open **http://host123.local:8080** in the
   Mac's browser: the annotated view, the drive state, both motor duties and the frame rate.
6. Copy a log back: `scp host123@host123.local:~/certain-road/runs/rover/<stamp>/decisions.csv .`
7. VS Code on the Mac: the Remote-SSH extension, host `host123@host123.local`.

## 4. Run order (from `~/certain-road`, over SSH)

1. **Motor test, wheels off the ground:** `.venv/bin/python rover/test_motors.py`. It checks
   each side's direction and where the motors start turning, and saves the results to
   `configs/rover/calibrated.yaml`, which every rover script then uses.
2. **Dry run, motors off:** `.venv/bin/python rover/pothole_drive.py`. Watch the browser and hold
   a printed pothole in front of the camera at rover height: the state should go WARNING, then
   AVOID, and the duties change. Nothing moves.
3. **Armed on a stand, wheels off the ground:** `.venv/bin/python rover/pothole_drive.py --arm
   --max-run-s 20`. The wheels should slow and turn when a pothole is held in front.
4. **On the track:** `.venv/bin/python rover/pothole_drive.py --arm --record run.mp4`. Add
   `--heading-hold` with the IMU wired (keep the rover still for 3 s at start) and `--can vcan0`
   to show each decision as a CAN frame (`candump vcan0` in a second SSH window).

Always use `.venv/bin/python`: it has torch, ultralytics and Jetson.GPIO.

## 5. Safety

- Motors move only with `--arm`, after a 3 s countdown.
- They stop on Ctrl-C, on any error, when no fresh decision arrives within 0.5 s (the
  watchdog), and after `safety.max_run_s` (120 s; `--max-run-s` overrides it).
- A hard crash may not stop them, especially in PWM mode, where the hardware PWM keeps its
  last duty. Keep the battery switch within reach.

## 6. What to tune (configs/rover/rover.yaml)

- `min_duty`, `max_duty`: speed. Below `min_duty` a TT motor stalls; the motor test sets it.
- `turn_duty`: how hard an avoid manoeuvre turns.
- `invert_left`, `invert_right`, `swap_sides`: set by the motor test if a side runs backwards.
- The driving corridor is `configs/driving/corridor.yaml`, designed for this robot class (a
  camera about 18 cm high, 15° down). After the camera calibration
  (`scripts/calibrate_camera.py`), re-derive it from the measured height and tilt.

Verified on this Jetson (2026-10-13): the pins claimed without sudo; the motor-mapping tests
pass; a 20 s dry run processed 277 camera frames at 13.5 fps with P + B, and the live view
streamed at about 14 fps. Not yet run on the rover itself.
