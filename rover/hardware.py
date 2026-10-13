"""The rover's hardware: the L298N on the Jetson header, and the MPU6050 heading.

Adapted from the friend's Jetson Xavier NX code (ugv_waypoint_drive.py, test_motors_l298n.py)
for the Orin Nano: the same BOARD pins and the same two speed modes, with the IMU's I2C bus
found by scanning (i2c-7 on the Orin Nano, i2c-8 on the Xavier NX).

- PWM mode (`use_pwm: true`): ENA/ENB jumpers removed, hardware PWM on pins 32 and 33,
  enabled once with `sudo /opt/nvidia/jetson-io/jetson-io.py` and a reboot.
- Jumper mode (`use_pwm: false`, the default): ENA/ENB jumpers fitted; speed made by switching
  the IN pins in a 20 Hz cycle of ten slots. Off-slots brake, which is harsh but needs no
  jetson-io change.

SAFETY: Ctrl-C and errors stop the motors. A hard crash may not: in PWM mode the hardware PWM
keeps its last duty. Wheels off the ground for first tests; a battery switch within reach.
"""

from __future__ import annotations

import statistics
import struct
import threading
import time

from drivemap import clamp

SIDES = ("left", "right")


class Motors:
    """set(left, right) takes duty in -100..100 per side."""

    def __init__(self, cfg: dict) -> None:
        import Jetson.GPIO as GPIO

        self.G, self.cfg = GPIO, cfg
        self.duty = {s: 0.0 for s in SIDES}
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)
        for s in SIDES:
            p = cfg["pins"][s]
            GPIO.setup(p["a"], GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(p["b"], GPIO.OUT, initial=GPIO.LOW)
        self.pwm = {}
        self._stop = threading.Event()
        if cfg["use_pwm"]:
            for s in SIDES:
                en = cfg["pins"][s]["en"]
                GPIO.setup(en, GPIO.OUT, initial=GPIO.LOW)
                self.pwm[s] = GPIO.PWM(en, cfg["pwm_hz"])
                self.pwm[s].start(0)
        else:
            threading.Thread(target=self._soft_pwm, daemon=True).start()

    def _dir(self, side: str, d: float) -> None:
        p, G = self.cfg["pins"][side], self.G
        if self.cfg["invert_" + side]:
            d = -d
        G.output(p["a"], G.HIGH if d > 0 else G.LOW)
        G.output(p["b"], G.HIGH if d < 0 else G.LOW)

    def _soft_pwm(self) -> None:
        slot = 0
        while not self._stop.is_set():
            for s in SIDES:
                d = self.duty[s]
                on = slot < int(round(abs(d) / 10.0))
                self._dir(s, (1 if d > 0 else -1) if on and d != 0 else 0)
            slot = (slot + 1) % 10
            time.sleep(self.cfg["soft_pwm_slot_s"])

    def set(self, left: float, right: float) -> None:
        if self.cfg["swap_sides"]:
            left, right = right, left
        self.duty["left"], self.duty["right"] = clamp(left, -100, 100), clamp(right, -100, 100)
        for s in self.pwm:
            self._dir(s, self.duty[s])
            self.pwm[s].ChangeDutyCycle(abs(self.duty[s]))

    def stop(self) -> None:
        self.duty = {s: 0.0 for s in SIDES}
        for s in SIDES:
            self._dir(s, 0)
            if s in self.pwm:
                self.pwm[s].ChangeDutyCycle(0)

    def close(self) -> None:
        self.stop()
        self._stop.set()
        time.sleep(0.02)
        self.stop()
        for p in self.pwm.values():
            p.stop()
        self.G.cleanup()


class DryMotors:
    """Same interface, no hardware: for --dry-run and for a bench without the L298N."""

    def __init__(self, cfg: dict | None = None) -> None:
        self.duty = {s: 0.0 for s in SIDES}

    def set(self, left: float, right: float) -> None:
        self.duty = {"left": clamp(left, -100, 100), "right": clamp(right, -100, 100)}

    def stop(self) -> None:
        self.duty = {s: 0.0 for s in SIDES}

    def close(self) -> None:
        self.stop()


def find_imu(buses: list[int], addr: int) -> int | None:
    """The first I2C bus where something answers at `addr` (the MPU6050's WHO_AM_I is 0x68)."""
    from smbus2 import SMBus

    for bus in buses:
        try:
            with SMBus(bus) as b:
                b.read_byte_data(addr, 0x75)
                return bus
        except OSError:
            continue
    return None


class MPU6050Heading:
    """Yaw from the gyro, integrated in a background thread (the friend's design).

    The up axis and its sign come from gravity during the still calibration, so the board can
    sit face-up or face-down. Bias is the median yaw rate while still; a median-of-3 filter and
    a rate limit stop one corrupted I2C read from injecting a false rotation.
    """

    def __init__(self, bus: int, addr: int, max_rate_dps: float) -> None:
        from smbus2 import SMBus

        self.b, self.addr, self.max_rate = SMBus(bus), addr, max_rate_dps
        self.b.write_byte_data(addr, 0x6B, 0x01)  # wake, gyro clock
        time.sleep(0.1)
        self.b.write_byte_data(addr, 0x1A, 0x03)  # ~44 Hz low-pass
        self.b.write_byte_data(addr, 0x1B, 0x00)  # +-250 deg/s
        self.b.write_byte_data(addr, 0x1C, 0x00)  # +-2 g
        time.sleep(0.05)
        self.axis, self.sign, self.bias = 2, 1.0, 0.0
        self.heading, self.stamp = 0.0, 0.0
        self._lock, self._stop, self._hist = threading.Lock(), threading.Event(), []

    def _raw(self) -> tuple[list[float], list[float]]:
        v = struct.unpack(">7h", bytes(self.b.read_i2c_block_data(self.addr, 0x3B, 14)))
        return [x / 16384.0 for x in v[0:3]], [x / 131.0 for x in v[4:7]]

    def calibrate(self, seconds: float) -> None:
        acc, gyr, t0 = [], [], time.time()
        while time.time() - t0 < seconds:
            a, g = self._raw()
            acc.append(a)
            gyr.append(g)
        means = [statistics.mean(a[i] for a in acc) for i in range(3)]
        self.axis = max(range(3), key=lambda i: abs(means[i]))
        self.sign = 1.0 if means[self.axis] > 0 else -1.0
        self.bias = statistics.median(g[self.axis] for g in gyr)

    def _loop(self) -> None:
        last = time.time()
        while not self._stop.is_set():
            try:
                _, g = self._raw()
            except OSError:
                continue
            now = time.time()
            self._hist = ([*self._hist, self.sign * (g[self.axis] - self.bias)])[-3:]
            rate = sorted(self._hist)[len(self._hist) // 2]
            if abs(rate) > self.max_rate:
                rate = 0.0
            with self._lock:
                self.heading += rate * (now - last)
                self.stamp = now
            last = now

    def start(self) -> None:
        self.stamp = time.time()
        threading.Thread(target=self._loop, daemon=True).start()

    def get(self) -> tuple[float, float]:
        """(heading in degrees, counter-clockwise positive; seconds since the last read)."""
        with self._lock:
            return self.heading, time.time() - self.stamp

    def close(self) -> None:
        self._stop.set()
