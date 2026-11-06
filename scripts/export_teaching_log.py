"""Export the latest real run into a slide-friendly Markdown example."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = sorted((root / "logs").glob("*/events.jsonl"))
if not files:
    raise SystemExit("No run logs found")
events = [json.loads(line) for line in files[-1].read_text(encoding="utf-8").splitlines()]
def first(stage):
    return next(e["data"] for e in events if e["stage"] == stage)
def block(data):
    return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```\n"

parts = ["# 自然語言如何變成無人機飛行：實際執行範例\n",
    f"來源：`{files[-1].relative_to(root)}`。以下數值來自同一次實際執行。\n",
    "## 1. 使用者自然語言\n", first("natural_language")["text"] + "\n",
    "## 2. LLM 的 Function Calling 輸出\n",
    block(first("llm_response")["message"]["tool_calls"]),
    "這是 LLM 選擇的工具與參數，尚未送至飛控。\n",
    "## 3. 控制程式驗證後的計畫\n", block(first("validated_plan")),
    "程式檢查欄位、資料型別、有限數字、高度 1–5 m、距離 0–10 m、角度 ±180°，並要求最後降落。\n",
    "## 4. 相對方向換算成 NED 位置目標\n", block(first("coordinate_conversion")),
    "NED = 北、東、下。前進以當下機頭方向為準；向上 3 m 對應 down=-3 m。yaw 以北為 0°，順時針為正。\n",
    "## 5. MAVSDK 呼叫（實際送出的高階命令）\n",
    block([e["data"] for e in events if e["stage"] == "sdk_command"]),
    "MAVSDK 將這些呼叫轉成 MAVLink 命令／setpoint，PX4 接收後執行飛控迴路，Gazebo 模擬物理與感測器。此紀錄保存 SDK 層，未擷取 MAVLink 線上封包，不能把上述 JSON 當成實際封包。LLM 不產生馬達或高頻姿態訊號。\n",
    "## 6. 實際遙測與落地結果\n", block(first("result")),
    "距離與旋轉量以進入前進動作時的位置與機頭為基準。落地欄位由 PX4 in_air 遙測判定；NED 估測高度可能有小幅漂移。\n"]
(root / "教學展示_實際指令轉換範例.md").write_text("\n".join(parts), encoding="utf-8")
print(files[-1])
