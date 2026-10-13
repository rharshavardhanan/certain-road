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
- **The Jetson's DC jack accepts 9–20 V, at most 4.2 A** (the Orin Nano developer kit carrier
  board spec, as quoted on NVIDIA's forum). Feeding it anything outside that range can damage it.
- **The blue LM2596 buck converter only steps voltage DOWN**, by at least ~1.5 V, at most 3 A.
  So it can make 12 V only from ≥ ~13.5 V. Five cells **in parallel** stay at 3.0–4.2 V and can
  never give 12 V through it; to get 12 V from a buck, the cells must be **in series**.
- **Measure before you connect:** a multimeter across the pack: ~15–21 V means 5 in series (5S),
  ~3–4.2 V means parallel. Set the LM2596's output with its screw to 12.0 V **with nothing
  connected to it**, then connect the Jetson.
- **Option 1 — THIS ROVER (confirmed 2026-10-13: 5 cells in series, 15–21 V):** 5S → LM2596 at 12 V →
  5.5 × 2.5 mm centre-positive barrel plug → Jetson. The motors need their own lower supply:
  a second buck set to ~7.5 V into the L298N's +12V/VS terminal (a 5 A-class module, since six
  TT motors can draw more than an LM2596's 3 A when they stall). Never feed the L298N straight
  from 5S: TT motors are 3–6 V parts.
- **Option 2, no buck (3 + 2 cells):** 3 in series (9.0–12.6 V) straight into the Jetson's jack,
  2 in series (7.4 V) into the L298N. Simpler, but a near-empty 3S pack sits at the Jetson's
  9 V minimum, so it shuts down earlier.
- **Either way:** a protection board (BMS) matched to the series count (5S or 3S), matched cells
  charged to 4.2 V each before joining them, polarity checked with a multimeter, a 3–5 A fuse on
  the Jetson's positive wire, and only the ground wire shared between the Jetson side and the
  motor side (Jetson pin 30 ↔ L298N GND). Never join the two supplies' positive wires.
- **Run the Jetson at 15 W on battery:** `sudo nvpmodel -m 0` (back to 25 W: `-m 1`). At 25 W the
  board can draw over 2 A from 12 V, close to an LM2596's limit; a brown-out reboots the Jetson
  mid-run. Detection gets somewhat slower at 15 W: measure it with a dry run.
- Before pulling the Jetson's power: `sudo shutdown now`.

## 3. Working from the Mac over SSH

1. **Once, on the Jetson** (with a monitor): `sudo systemctl enable --now ssh`. If that fails
   and `journalctl -u ssh -n 5` says `no hostkeys available`, the image shipped empty
   (0-byte) host key files that `ssh-keygen -A` will not overwrite. Delete them first:
   `sudo rm /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub && sudo ssh-keygen -A`, then
   `sudo systemctl reset-failed ssh.service ssh.socket && sudo systemctl enable --now
   ssh.socket ssh.service`. Join the same Wi-Fi as the Mac. If the lab network blocks devices from reaching each other, use the
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
