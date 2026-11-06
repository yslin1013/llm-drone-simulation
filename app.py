from __future__ import annotations

import asyncio
import json
import math
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from dataclasses import asdict, dataclass
from typing import Any

import requests
from flask import Flask, jsonify, render_template, request
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw


DEFAULT_COMMAND = "請讓無人機起飛到 3 公尺，往前飛行 5 公尺，原地旋轉 90 度，最後安全降落。"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

app = Flask(__name__)


@dataclass
class DemoState:
    phase: str = "idle"
    message: str = "等待指令"
    backend: str = ""
    tool_call: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None
    log: list[str] | None = None
    error: str = ""


state = DemoState(log=[])
state_lock = threading.Lock()
running = False
run_dir: Path | None = None


def audit(stage: str, data: Any) -> None:
    if run_dir is None:
        return
    event = {"time": datetime.now().astimezone().isoformat(), "stage": stage, "data": data}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")


def sdk_call(method: str, **parameters: Any) -> None:
    audit("sdk_command", {"method": method, "parameters": parameters})


def update(phase: str, message: str, **extra: Any) -> None:
    stamp = time.strftime("%H:%M:%S")
    with state_lock:
        state.phase = phase
        state.message = message
        if state.log is None:
            state.log = []
        entry = f"[{stamp}] {message}"
        if not state.log or not state.log[-1].endswith(message):
            state.log.append(entry)
        state.log = state.log[-80:]
        for key, value in extra.items():
            setattr(state, key, value)
    audit("state", {"phase": phase, "message": message, **extra})


TOOL = {
    "type": "function",
    "function": {
        "name": "execute_flight_plan",
        "description": "建立安全的高階無人機飛行計畫。旋轉未指定方向時採順時針。",
        "parameters": {
            "type": "object",
            "properties": {
                "takeoff_altitude_m": {"type": "number", "description": "相對起飛點高度，公尺"},
                "forward_distance_m": {"type": "number", "description": "沿當下機頭方向前進距離，公尺"},
                "yaw_clockwise_deg": {"type": "number", "description": "原地順時針旋轉角度"},
                "land": {"type": "boolean", "description": "任務結尾是否降落"},
            },
            "required": ["takeoff_altitude_m", "forward_distance_m", "yaw_clockwise_deg", "land"],
            "additionalProperties": False,
        },
    },
}


def parse_with_ollama(text: str) -> tuple[dict[str, Any], str]:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "keep_alive": -1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是無人機任務規劃器。只能呼叫提供的工具，不得輸出馬達、推力或姿態控制。"
                    "必須逐字擷取使用者提到的高度、距離與角度，不可改成 0。"
                    "中文的『旋轉 90 度』未指定方向時，使用順時針 90 度。"
                    "例如『起飛到 3 公尺、往前 5 公尺、旋轉 90 度、降落』必須呼叫："
                    "takeoff_altitude_m=3, forward_distance_m=5, yaw_clockwise_deg=90, land=true。"
                ),
            },
            {"role": "user", "content": text},
        ],
        "tools": [TOOL],
    }
    response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    response.raise_for_status()
    body = response.json()
    audit("llm_response", body)
    calls = body.get("message", {}).get("tool_calls", [])
    if not calls:
        raise ValueError("本機 LLM 未產生工具呼叫")
    call = calls[0]
    if len(calls) != 1 or call.get("function", {}).get("name") != "execute_flight_plan":
        raise ValueError("只允許單一 execute_flight_plan 工具呼叫")
    args = call.get("function", {}).get("arguments", {})
    if isinstance(args, str):
        args = json.loads(args)
    return args, f"Ollama / {OLLAMA_MODEL}"


def parse_with_openai(text: str) -> tuple[dict[str, Any], str]:
    from openai import OpenAI

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": "只使用 execute_flight_plan 工具建立高階飛行計畫；未指定旋轉方向時採順時針。",
            },
            {"role": "user", "content": text},
        ],
        tools=[TOOL["function"] | {"type": "function"}],
        tool_choice={"type": "function", "name": "execute_flight_plan"},
    )
    call = next(item for item in response.output if item.type == "function_call")
    return json.loads(call.arguments), f"OpenAI / {model}"


def parse_command(text: str) -> tuple[dict[str, Any], str]:
    if os.getenv("LLM_PROVIDER", "ollama") == "openai":
        return parse_with_openai(text)
    return parse_with_ollama(text)


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    required = {"takeoff_altitude_m", "forward_distance_m", "yaw_clockwise_deg", "land"}
    if set(plan) != required:
        raise ValueError(f"工具參數欄位不符：需要 {sorted(required)}")
    if type(plan["land"]) is not bool:
        raise ValueError("land 必須是布林值")
    for key in required - {"land"}:
        if type(plan[key]) not in (int, float) or not math.isfinite(plan[key]):
            raise ValueError(f"{key} 必須是有限數字")
    clean = {
        "takeoff_altitude_m": float(plan["takeoff_altitude_m"]),
        "forward_distance_m": float(plan["forward_distance_m"]),
        "yaw_clockwise_deg": float(plan["yaw_clockwise_deg"]),
        "land": bool(plan["land"]),
    }
    if not 1.0 <= clean["takeoff_altitude_m"] <= 5.0:
        raise ValueError("安全限制：起飛高度須介於 1–5 公尺")
    if not 0.0 <= clean["forward_distance_m"] <= 10.0:
        raise ValueError("安全限制：前進距離須介於 0–10 公尺")
    if not -180.0 <= clean["yaw_clockwise_deg"] <= 180.0:
        raise ValueError("安全限制：旋轉角度須介於 -180–180 度")
    if not clean["land"]:
        raise ValueError("安全限制：示範任務必須以降落結束")
    return clean


async def latest(stream: Any, timeout: float = 10.0) -> Any:
    return await asyncio.wait_for(anext(stream), timeout)


async def hold_position(drone: System, n: float, e: float, d: float, yaw: float, seconds: float) -> None:
    sdk_call("offboard.set_position_ned", north_m=n, east_m=e, down_m=d, yaw_deg=yaw,
             note="目標持續送出；MAVSDK 負責 Offboard setpoint 串流")
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        await drone.offboard.set_position_ned(PositionNedYaw(n, e, d, yaw))
        pos = await latest(drone.telemetry.position_velocity_ned(), 2)
        heading = await latest(drone.telemetry.heading(), 2)
        update(
            state.phase,
            state.message,
            telemetry={
                "north_m": round(pos.position.north_m, 2),
                "east_m": round(pos.position.east_m, 2),
                "height_m": round(-pos.position.down_m, 2),
                "heading_deg": round(heading.heading_deg, 1),
            },
        )
        await asyncio.sleep(0.2)


async def fly(plan: dict[str, Any]) -> None:
    drone = System()
    try:
        await asyncio.wait_for(_fly(plan, drone), timeout=150)
    except Exception:
        audit("recovery", {"action": "request_land", "reason": "flight exception or timeout"})
        try:
            await asyncio.wait_for(drone.action.land(), timeout=8)
        except Exception as recovery_error:
            audit("recovery_error", {"error": str(recovery_error)})
        raise


async def _fly(plan: dict[str, Any], drone: System) -> None:
    update("connecting", "連線至 PX4 SITL（udp://:14540）")
    await drone.connect(system_address="udpin://0.0.0.0:14540")
    async for connection in drone.core.connection_state():
        if connection.is_connected:
            break

    update("preflight", "等待位置估測與安全檢查")
    async for health in drone.telemetry.health():
        if health.is_local_position_ok and health.is_home_position_ok:
            break

    altitude = plan["takeoff_altitude_m"]
    update("takeoff", f"解鎖並起飛至 {altitude:.1f} 公尺")
    await drone.action.set_takeoff_altitude(altitude)
    sdk_call("action.set_takeoff_altitude", altitude_m=altitude)
    sdk_call("action.arm")
    await drone.action.arm()
    sdk_call("action.takeoff")
    await drone.action.takeoff()

    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        pos = await latest(drone.telemetry.position_velocity_ned(), 2)
        if -pos.position.down_m >= altitude - 0.35:
            break
        await asyncio.sleep(0.3)
    else:
        raise TimeoutError("起飛高度逾時")

    pos = await latest(drone.telemetry.position_velocity_ned())
    heading = await latest(drone.telemetry.heading())
    start_n = pos.position.north_m
    start_e = pos.position.east_m
    down = -altitude
    yaw = heading.heading_deg
    await drone.offboard.set_position_ned(PositionNedYaw(start_n, start_e, down, yaw))
    try:
        await drone.offboard.start()
    except OffboardError as exc:
        raise RuntimeError(f"無法進入 Offboard 模式：{exc._result.result}") from exc

    distance = plan["forward_distance_m"]
    rad = math.radians(yaw)
    target_n = start_n + distance * math.cos(rad)
    target_e = start_e + distance * math.sin(rad)
    audit("coordinate_conversion", {"frame": "NED", "start_north_m": start_n,
        "start_east_m": start_e, "initial_heading_deg": yaw,
        "forward_distance_m": distance, "target_north_m": target_n,
        "target_east_m": target_e, "target_down_m": down,
        "formula": "N=N0+distance*cos(yaw); E=E0+distance*sin(yaw); D=-altitude"})
    update("forward", f"依機頭方向前進 {distance:.1f} 公尺")
    await hold_position(drone, target_n, target_e, down, yaw, 8.0)

    target_yaw = (yaw + plan["yaw_clockwise_deg"]) % 360
    update("rotate", f"原地順時針旋轉 {plan['yaw_clockwise_deg']:.0f} 度")
    await hold_position(drone, target_n, target_e, down, target_yaw, 6.0)
    actual = await latest(drone.telemetry.position_velocity_ned())
    actual_heading = await latest(drone.telemetry.heading())
    metrics = {"distance_m": math.hypot(actual.position.north_m-start_n, actual.position.east_m-start_e),
        "height_m": -actual.position.down_m,
        "yaw_change_deg": (actual_heading.heading_deg-yaw+180)%360-180,
        "position_error_m": math.hypot(actual.position.north_m-target_n, actual.position.east_m-target_e)}
    audit("flight_measurement", metrics)

    update("landing", "停止 Offboard 控制並安全降落")
    await drone.offboard.stop()
    sdk_call("action.land")
    await drone.action.land()
    async for in_air in drone.telemetry.in_air():
        if not in_air:
            break
    final_pos = await latest(drone.telemetry.position_velocity_ned())
    final_heading = await latest(drone.telemetry.heading())
    final = {
        "north_m": round(final_pos.position.north_m, 2),
        "east_m": round(final_pos.position.east_m, 2),
        "height_m": round(-final_pos.position.down_m, 2),
        "heading_deg": round(final_heading.heading_deg, 1),
    }
    update("complete", "任務完成：無人機已落地", telemetry=final)
    audit("result", {"landed": True, "metrics": metrics, "final": final})


def worker(text: str) -> None:
    global running, run_dir
    run_dir = Path(__file__).parent / "logs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    with state_lock:
        state.log = []
    audit("natural_language", {"text": text})
    try:
        update("llm", "LLM 正在理解自然語言", error="", tool_call=None, telemetry=None)
        plan, backend = parse_command(text)
        update("validation", "收到工具呼叫，開始安全驗證", backend=backend, tool_call=plan)
        plan = validate_plan(plan)
        audit("validated_plan", {"tool": "execute_flight_plan", "arguments": plan,
            "sequence": ["takeoff", "forward_body_heading", "yaw_relative_clockwise", "land"]})
        update("validated", "參數驗證通過，準備送往 MAVSDK", tool_call=plan)
        asyncio.run(fly(plan))
    except Exception as exc:
        update("error", f"執行失敗：{exc}", error=str(exc))
    finally:
        running = False


@app.get("/")
def index() -> str:
    return render_template("index.html", default_command=DEFAULT_COMMAND)


@app.get("/api/status")
def status() -> Any:
    with state_lock:
        return jsonify(asdict(state) | {"running": running})


@app.post("/api/run")
def run() -> Any:
    global running
    if running:
        return jsonify({"error": "已有任務執行中"}), 409
    body = request.get_json(force=True)
    text = str(body.get("command", "")).strip()
    if not text:
        return jsonify({"error": "請輸入指令"}), 400
    running = True
    threading.Thread(target=worker, args=(text,), daemon=True).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)
