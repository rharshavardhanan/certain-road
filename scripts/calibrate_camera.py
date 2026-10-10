"""Measure the robot camera's lens, then its height and tilt above the floor (robot step 2).

    python scripts/calibrate_camera.py board        # write checkerboard.png to print (A4, 100%)
    python scripts/calibrate_camera.py intrinsics   # once: show the board from many angles
    python scripts/calibrate_camera.py mount        # board flat on the floor in front of the car
    ... --target phone                              # a phone screen instead of the A4 print

`intrinsics` captures the board whenever it has moved, then fits the focal length and lens
distortion (cv2.calibrateCamera). `mount` lays the board's plane as the floor: solvePnP gives
the camera's pose against it, so the camera centre's distance to that plane is its height,
and the optical axis's angle below it is the pitch. Both average `mount.frames` frames and
write configs/robot/camera_c920.yaml. Before `intrinsics` has run, `mount` uses the nominal
field of view and says so: heights are then good to a few per cent, not millimetres.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

ROOT = repo_root()
CFG = yaml.safe_load((ROOT / "configs/robot/calibration.yaml").read_text())
A4_M = (0.210, 0.297)


def target(cfg: dict, name: str = "print") -> dict:
    """The checkerboard in use: the A4 print (`board`) or a phone screen (`phone`)."""
    t = cfg["phone"] if name == "phone" else cfg["board"]
    return {
        "inner_corners": t["inner_corners"],
        "square_m": t["square_m"],
        "thickness_m": t.get("thickness_m", 0.0),
    }


def board_points(cfg: dict, name: str = "print") -> np.ndarray:
    """The board's inner corners in its own plane (z = 0), metres."""
    t = target(cfg, name)
    nx, ny = t["inner_corners"]
    g = np.mgrid[0:nx, 0:ny].T.reshape(-1, 2).astype(np.float64) * t["square_m"]
    return np.hstack([g, np.zeros((len(g), 1))])


def mount_from_pose(rvec: np.ndarray, tvec: np.ndarray) -> dict:
    """Height, pitch and roll of a camera whose pose against a floor-lying board is (rvec, tvec).

    The floor's upward normal is the board's z-axis turned toward the camera, whichever way
    solvePnP put it. Pitch: the optical axis below the floor's plane. Roll: rotation about the
    optical axis, zero when the image's horizontal lies parallel to the floor.
    """
    r, _ = cv2.Rodrigues(rvec)
    centre = -r.T @ np.asarray(tvec, float).reshape(3)
    up = np.array([0.0, 0.0, 1.0 if centre[2] >= 0 else -1.0])
    x_img, y_img, axis = (r.T @ e for e in np.eye(3))  # camera axes in the board's frame
    return {
        "height_m": float(abs(centre[2])),
        "pitch_rad": float(math.asin(max(-1.0, min(1.0, -axis @ up)))),
        "roll_rad": float(math.atan2(-(x_img @ up), -(y_img @ up))),
    }


def nominal_k(cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    w, h = cfg["camera"]["size"]
    f = (w / 2) / math.tan(math.radians(cfg["camera"]["nominal_hfov_deg"]) / 2)
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]]), np.zeros(5)


def open_camera(cfg: dict) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(cfg["camera"]["device"], cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["camera"]["size"][0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["camera"]["size"][1])
    return cap


def find_board(gray: np.ndarray, cfg: dict, name: str = "print") -> np.ndarray | None:
    ok, corners = cv2.findChessboardCornersSB(gray, tuple(target(cfg, name)["inner_corners"]))
    return corners.reshape(-1, 2) if ok else None


def write_phone_board(cfg: dict, out: Path) -> None:
    ph = cfg["phone"]
    (w, h), (nx, ny), px = ph["screen_px"], ph["inner_corners"], ph["square_px"]
    page = np.full((h, w), 255, np.uint8)
    y0, x0 = (h - (ny + 1) * px) // 2, (w - (nx + 1) * px) // 2
    for i in range(ny + 1):
        for j in range(nx + 1):
            if (i + j) % 2 == 0:
                page[y0 + i * px : y0 + (i + 1) * px, x0 + j * px : x0 + (j + 1) * px] = 0
    cv2.imwrite(str(out), page)
    print(
        f"{out}: open full-screen on the {ph['model']} (landscape), then measure one square "
        f"with a ruler and set phone.square_m (now {ph['square_m'] * 1000:.1f} mm)"
    )


def write_board(cfg: dict, out: Path) -> None:
    dpi, sq = cfg["board"]["print_dpi"], cfg["board"]["square_m"]
    nx, ny = cfg["board"]["inner_corners"]
    px = round(sq / 0.0254 * dpi)
    page = np.full((round(A4_M[1] / 0.0254 * dpi), round(A4_M[0] / 0.0254 * dpi)), 255, np.uint8)
    bw, bh = (ny + 1) * px, (nx + 1) * px  # the board runs down the portrait page
    y0, x0 = (page.shape[0] - bh) // 2, (page.shape[1] - bw) // 2
    for i in range(nx + 1):
        for j in range(ny + 1):
            if (i + j) % 2 == 0:
                page[y0 + i * px : y0 + (i + 1) * px, x0 + j * px : x0 + (j + 1) * px] = 0
    cv2.imwrite(str(out), page)
    print(f"{out}: print on A4 at 100% ({dpi} dpi); each square should measure {sq * 1000:.0f} mm")


def save(update: dict) -> Path:
    out = ROOT / CFG["out"]
    data = yaml.safe_load(out.read_text()) if out.exists() else {}
    data.update(update)
    out.write_text(yaml.safe_dump(data, sort_keys=False))
    return out


def intrinsics(cfg: dict, name: str) -> None:
    cap, obj = open_camera(cfg), board_points(cfg, name)
    views, last = [], None
    while len(views) < cfg["intrinsics"]["views"]:
        ok, frame = cap.read()
        if not ok:
            sys.exit("no frames from the camera")
        corners = find_board(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cfg, name)
        if corners is not None:
            cv2.drawChessboardCorners(
                frame, tuple(target(cfg, name)["inner_corners"]), corners, True
            )
            moved = (
                last is None
                or np.linalg.norm(corners.mean(0) - last) > cfg["intrinsics"]["min_move_px"]
            )
            if moved:
                views.append(corners)
                last = corners.mean(0)
        msg = f"views {len(views)}/{cfg['intrinsics']['views']}: tilt and move the board; q quits"
        cv2.putText(frame, msg, (10, 30), 0, 0.8, (0, 255, 0), 2)
        cv2.imshow("calibrate: intrinsics", frame)
        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            sys.exit("stopped")
    cap.release()
    cv2.destroyAllWindows()
    size = tuple(cfg["camera"]["size"])
    rms, k, dist, _, _ = cv2.calibrateCamera(
        [obj.astype(np.float32)] * len(views),
        [v.astype(np.float32) for v in views],
        size,
        None,
        None,
    )
    hfov = math.degrees(2 * math.atan(size[0] / (2 * k[0, 0])))
    out = save(
        {
            "intrinsics": {
                "size": list(size),
                "k": k.tolist(),
                "dist": dist.ravel().tolist(),
                "rms_px": float(rms),
                "hfov_deg": hfov,
            }
        }
    )
    print(f"reprojection error {rms:.2f} px (under ~0.5 is good); HFOV {hfov:.1f} deg -> {out}")


def mount(cfg: dict, name: str) -> None:
    out = ROOT / CFG["out"]
    saved = yaml.safe_load(out.read_text()).get("intrinsics") if out.exists() else None
    if saved:
        k, dist, source = np.array(saved["k"]), np.array(saved["dist"]), "calibrated"
    else:
        k, dist = nominal_k(cfg)
        source = "NOMINAL field of view (run `intrinsics` for millimetre accuracy)"
    print(f"intrinsics: {source}")
    cap, obj, got = open_camera(cfg), board_points(cfg, name), []
    while len(got) < cfg["mount"]["frames"]:
        ok, frame = cap.read()
        if not ok:
            sys.exit("no frames from the camera")
        corners = find_board(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cfg, name)
        if corners is not None:
            ok, rvec, tvec = cv2.solvePnP(obj, corners.astype(np.float64), k, dist)
            if ok:
                got.append(mount_from_pose(rvec, tvec))
                cv2.drawFrameAxes(frame, k, dist, rvec, tvec, cfg["board"]["square_m"] * 3)
        msg = f"board flat on the floor in view: {len(got)}/{cfg['mount']['frames']}; q quits"
        cv2.putText(frame, msg, (10, 30), 0, 0.8, (0, 255, 0), 2)
        cv2.imshow("calibrate: mount", frame)
        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            sys.exit("stopped")
    cap.release()
    cv2.destroyAllWindows()
    med = {key: float(np.median([g[key] for g in got])) for key in got[0]}
    med["height_m"] += target(cfg, name)["thickness_m"]  # the board's surface sits this high
    spread = {key: float(np.std([g[key] for g in got])) for key in got[0]}
    out = save(
        {
            "mount": {
                **med,
                "pitch_deg": math.degrees(med["pitch_rad"]),
                "roll_deg": math.degrees(med["roll_rad"]),
                "frames": len(got),
                "intrinsics": source.split(" ")[0].lower(),
            }
        }
    )
    print(
        f"height {med['height_m'] * 100:.1f} cm (+/- {spread['height_m'] * 100:.1f}), "
        f"pitch {math.degrees(med['pitch_rad']):.1f} deg down, "
        f"roll {math.degrees(med['roll_rad']):.1f} deg -> {out}"
    )
    print("height is to the board's surface: the floor, for a sheet lying flat on it")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=["board", "intrinsics", "mount"])
    ap.add_argument("--target", choices=["print", "phone"], default="print")
    args = ap.parse_args()
    if args.step == "board" and args.target == "phone":
        write_phone_board(CFG, ROOT / "checkerboard_phone.png")
    elif args.step == "board":
        write_board(CFG, ROOT / "checkerboard.png")
    elif args.step == "intrinsics":
        intrinsics(CFG, args.target)
    else:
        mount(CFG, args.target)


if __name__ == "__main__":
    main()
