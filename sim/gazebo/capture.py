"""The evidence drive: constant /cmd_vel down the lane; every camera frame and the true pose saved.

    source ros/env.sh
    ros2 launch certain_road_gz world.launch.py preset:=poor seed:=0 &
    python -m sim.gazebo.capture --world runs/gazebo/poor_seed0

Listens to the bridge exactly as a ROS node on the Jetson would (/camera/image_raw, /odom,
/joint_states, /clock), sends a constant Twist at the design speed (configs/project.yaml
sim.speed_kmh) with no steering, and stops when the camera nears the road's end. With
--lane-keep it also steers back to the lane centre from the true pose, as a driver would: a
stand-in so the camera stays where the MuJoCo demo's camera is, never part of what is tested.
It writes <world>/drive/: frames/*.jpg, frames.jsonl (frame stamps), odom.jsonl and
joints.jsonl (100 Hz true pose and suspension travel), camera_info.json, and summary.json with
what was measured: real-time factor, camera rate in simulated and wall time, memory, and the
lateral drift.

It does not detect anything (sim/gazebo/evaluate.py does, offline). Without --lane-keep it
does not steer: a constant command is the test, so any drift out of the lane is reported.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from certain_road.core.paths import repo_root
from sim.gazebo.export import load_gz

PROJECT = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())


def demo_lane_keeper() -> dict:
    """The stand-in driver's gains: configs/ros/demo.yaml `lane_keeper`, as lane_keeper_node's."""
    return yaml.safe_load((repo_root() / "configs/ros/demo.yaml").read_text())["lane_keeper"]


def keep_yaw_rate(lateral_m: float, heading_rad: float, cfg: dict) -> float:
    """certain_road_ros.lane_keep.yaw_rate, the one stand-in rule, imported from the ROS package."""
    sys.path.insert(0, str(repo_root() / "ros" / "certain_road_ros"))
    from certain_road_ros.lane_keep import yaw_rate

    return yaw_rate(lateral_m, heading_rad, cfg)


def mem_available_mb() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024  # the file reports KiB
    return float("nan")


def gz_rss_mb() -> float:
    """Resident memory of every `gz sim` process (server, and GUI if any), summed."""
    total = 0.0
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if b"gz sim" not in (p / "cmdline").read_bytes().replace(b"\0", b" "):
                continue
            for line in (p / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) / 1024  # KiB
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return total


def stamp_s(header) -> float:
    return header.stamp.sec + header.stamp.nanosec * 1e-9


def run(
    world: Path,
    out: Path,
    until_m: float | None,
    launch_t0: float | None,
    lane_keep: bool = False,
    record_only: bool = False,
) -> dict:
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import CameraInfo, Image, JointState

    gz = load_gz()
    cap, top = gz["capture"], gz["topics"]
    meta = json.loads((world / "world.json").read_text())
    car = yaml.safe_load((repo_root() / "ros/certain_road_gz/config/car.yaml").read_text())
    speed = PROJECT["sim"]["speed_kmh"] / 3.6
    stop_cam_x = until_m or meta["road"]["length_m"] - cap["end_margin_m"]
    forward = car["camera_xyz"][0]
    keeper = demo_lane_keeper()
    (out / "frames").mkdir(parents=True, exist_ok=True)
    files = {k: (out / f"{k}.jsonl").open("w") for k in ("frames", "odom", "joints")}
    jobs: queue.Queue = queue.Queue()

    def writer():
        while (job := jobs.get()) is not None:
            path, rgb = job
            cv2.imwrite(
                str(path),
                cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, cap["jpeg_quality"]],
            )

    threads = [threading.Thread(target=writer, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()

    rclpy.init()
    node = Node("certain_road_capture", parameter_overrides=[Parameter("use_sim_time", value=True)])
    reliable = QoSProfile(depth=200, reliability=ReliabilityPolicy.RELIABLE)
    st = {
        "frames": 0,
        "first_wall": None,
        "first_stamp": None,
        "last_stamp": None,
        "x": None,
        "lat": 0.0,
        "yaw": 0.0,
        "y": [],
        "done": False,
        "sim": 0.0,
        "info": None,
        "go_wall": None,
        "go_sim": None,
        "end_wall": None,
        "end_sim": None,
        "samples": [],
        "walls": [],
    }

    def frame(header, rgb=None):
        """One camera frame: its stamp logged, its pixels saved unless only recording."""
        if st["done"]:
            return
        now = time.time()
        if st["first_wall"] is None:
            st["first_wall"] = now
        i = st["frames"]
        name = None
        if rgb is not None:
            name = f"frames/{i:06d}.jpg"
            jobs.put((out / name, rgb))
        s = stamp_s(header)
        st["first_stamp"] = s if st["first_stamp"] is None else st["first_stamp"]
        st["last_stamp"] = s
        files["frames"].write(
            json.dumps(
                {
                    "i": i,
                    "file": name,
                    "stamp": s,
                    "wall": round(now, 4),
                    "frame_id": header.frame_id,
                }
            )
            + "\n"
        )
        st["frames"] += 1
        st["walls"].append(now)

    def on_image(msg: Image):
        rgb = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step)[:, : msg.width * 3]
        frame(msg.header, rgb.reshape(msg.height, msg.width, 3).copy())

    def on_odom(msg: Odometry):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        row = [stamp_s(msg.header), p.x, p.y, p.z, q.w, q.x, q.y, q.z, msg.twist.twist.linear.x]
        files["odom"].write(json.dumps([round(v, 6) for v in row]) + "\n")
        st["x"] = p.x
        st["lat"] = p.y - meta["spawn"]["y"]
        st["yaw"] = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        if st["go_sim"] is not None and not st["done"]:
            st["y"].append(p.y - meta["spawn"]["y"])

    def on_joints(msg: JointState):
        row = {
            "t": stamp_s(msg.header),
            **{n: round(v, 6) for n, v in zip(msg.name, msg.position, strict=False)},
        }
        files["joints"].write(json.dumps(row) + "\n")

    def on_info(msg: CameraInfo):
        if record_only:  # camera_info comes with every frame: count it, keep no pixels
            frame(msg.header)
        if st["info"] is None:
            st["info"] = {
                "w": msg.width,
                "h": msg.height,
                "k": list(msg.k),
                "frame_id": msg.header.frame_id,
            }

    def on_clock(msg: Clock):
        st["sim"] = msg.clock.sec + msg.clock.nanosec * 1e-9

    if not record_only:
        node.create_subscription(Image, top["image"]["ros"], on_image, reliable)
    node.create_subscription(Odometry, top["odom"]["ros"], on_odom, reliable)
    node.create_subscription(JointState, top["joint_states"]["ros"], on_joints, reliable)
    node.create_subscription(CameraInfo, top["camera_info"]["ros"], on_info, reliable)
    node.create_subscription(Clock, top["clock"]["ros"], on_clock, 10)
    pub = node.create_publisher(Twist, top["cmd_vel"]["ros"], 10)

    def command():
        cmd = Twist()
        if st["first_wall"] is None or st["x"] is None:
            return
        if st["go_wall"] is None:
            st["go_wall"], st["go_sim"] = time.time(), st["sim"]
        timed_out = record_only and st["sim"] - st["go_sim"] > cap["record_max_sim_s"]
        if st["x"] + forward >= stop_cam_x or timed_out:
            if not st["done"]:
                st["done"] = True
                st["end_wall"], st["end_sim"] = time.time(), st["sim"]
                st["timed_out"] = timed_out
        else:
            cmd.linear.x = speed
            if lane_keep:  # a driver holding the lane, from the true pose; not under test
                cmd.angular.z = keep_yaw_rate(st["lat"], st["yaw"], keeper)
        if not record_only:  # recording only: the closed loop drives, this only watches
            pub.publish(cmd)

    def sample():
        st["samples"].append(
            {"wall": time.time(), "sim": st["sim"], "frames": st["frames"],
             "mem_available_mb": round(mem_available_mb()), "gz_rss_mb": round(gz_rss_mb())}
        )  # fmt: skip

    from rclpy.clock import Clock as RosClock
    from rclpy.clock import ClockType

    wall_clock = RosClock(clock_type=ClockType.STEADY_TIME)
    node.create_timer(1.0 / cap["cmd_hz"], command, clock=wall_clock)
    node.create_timer(cap["stats_every_s"], sample, clock=wall_clock)
    start = time.time()
    mem_before = mem_available_mb()
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        if st["first_wall"] is None and time.time() - start > cap["wait_first_image_s"]:
            raise SystemExit("no camera image: is world.launch.py running?")
        if st["done"] and st["end_wall"] is not None and time.time() - st["end_wall"] > 1.0:
            break
    for _ in threads:
        jobs.put(None)
    for t in threads:
        t.join()
    for f in files.values():
        f.close()
    node.destroy_node()
    rclpy.shutdown()

    drive = [s for s in st["samples"] if s["wall"] >= st["go_wall"] and s["wall"] <= st["end_wall"]]
    sim_s, wall_s = st["end_sim"] - st["go_sim"], st["end_wall"] - st["go_wall"]
    y = np.array(st["y"]) if st["y"] else np.zeros(1)
    summary = {
        "world": str(world.relative_to(repo_root()))
        if world.is_relative_to(repo_root())
        else str(world),
        "speed_mps": round(speed, 4),
        "steering": "recorded only: the closed loop drives"
        if record_only
        else ("lane_keep" if lane_keep else "constant (angular.z = 0)"),
        "timed_out": st.get("timed_out", False),
        "frames": st["frames"],
        "frame_stamps_s": [st["first_stamp"], st["last_stamp"]],
        "drive_sim_s": round(sim_s, 2),
        "drive_wall_s": round(wall_s, 2),
        "real_time_factor": round(sim_s / wall_s, 3) if wall_s else None,
        "camera_hz_sim": round((st["frames"] - 1) / (st["last_stamp"] - st["first_stamp"]), 2)
        if st["frames"] > 1
        else None,
        # frames delivered per wall second while driving: what a node on the bridge receives
        "camera_hz_wall": round(
            sum(st["go_wall"] <= w <= st["end_wall"] for w in st["walls"]) / wall_s, 2
        )
        if wall_s
        else None,
        "first_image_after_capture_start_s": round(st["first_wall"] - start, 1),
        "load_s": round(st["first_wall"] - launch_t0, 1) if launch_t0 else None,
        "mem_available_mb": {
            "before": round(mem_before),
            "min_during": min(s["mem_available_mb"] for s in drive) if drive else None,
        },
        "gz_rss_mb_max": max(s["gz_rss_mb"] for s in drive) if drive else None,
        "lateral_drift_m": {
            "max_abs": round(float(np.abs(y).max()), 3),
            "final": round(float(y[-1]), 3),
        },
        "camera_info": st["info"],
        "samples": drive,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--world", type=Path, required=True, help="the exported world folder")
    ap.add_argument("--out", type=Path, help="default: <world>/drive")
    ap.add_argument("--until-m", type=float, help="stop once the camera passes this x")
    ap.add_argument(
        "--lane-keep",
        action="store_true",
        help="steer to hold the lane from the true pose (a driver stand-in), not constant",
    )
    ap.add_argument(
        "--record-only",
        action="store_true",
        help="send nothing and save no pixels: log pose, joints and frame stamps of a closed loop",
    )
    ap.add_argument(
        "--launch-t0", type=float, help="epoch seconds the launch started, for load time"
    )
    args = ap.parse_args()
    world = args.world.resolve()
    s = run(
        world,
        args.out or world / "drive",
        args.until_m,
        args.launch_t0,
        args.lane_keep,
        args.record_only,
    )
    print(json.dumps({k: v for k, v in s.items() if k != "samples"}, indent=1))


if __name__ == "__main__":
    main()
