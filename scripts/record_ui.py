import asyncio
import subprocess
import time
from pathlib import Path

from playwright.async_api import async_playwright


async def main() -> None:
    output = Path.home() / "llm-drone-demo-runtime" / "recordings"
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1000, "height": 1080},
            record_video_dir=str(output),
            record_video_size={"width": 1000, "height": 1080},
            locale="zh-TW",
        )
        page = await context.new_page()
        await page.goto("http://127.0.0.1:8000", wait_until="domcontentloaded", timeout=30_000)
        await page.locator("#run").wait_for(state="visible", timeout=15_000)
        window = subprocess.check_output(["xdotool", "search", "--name", "^Gazebo Sim$"], text=True).splitlines()[0]
        recorder = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab",
            "-framerate", "30", "-window_id", window, "-i", ":0.0", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(output / "gazebo.mkv")], stdin=subprocess.PIPE)
        started = time.monotonic()
        await page.wait_for_timeout(2500)
        async with page.expect_response(lambda r: '/api/run' in r.url and r.request.method == 'POST'):
            await page.evaluate("document.querySelector('#run').click()")
        await page.wait_for_timeout(1500)
        await page.wait_for_function(
            "document.querySelector('#status span').textContent.includes('已落地') || document.querySelector('#status').classList.contains('error')",
            timeout=300_000,
        )
        await page.screenshot(path=str(output / "ui-final.png"))
        await page.wait_for_timeout(max(6000, int((65-(time.monotonic()-started))*1000)))
        if recorder.stdin:
            recorder.stdin.write(b"q\n")
            recorder.stdin.flush()
        recorder.wait(timeout=20)
        video = page.video
        await context.close()
        if video:
            await video.save_as(str(output / "ui.webm"))
        await browser.close()


asyncio.run(main())
