#!/usr/bin/env bash
set -euo pipefail
REC="$HOME/llm-drone-demo-runtime/recordings"
OUT="$HOME/llm-drone-demo-runtime/app/LLM_Drone_Demo_1080p.mp4"
ffmpeg -y -loglevel warning -i "$REC/gazebo.mkv" -i "$REC/ui.webm" \
  -filter_complex "[0:v]setpts=PTS-STARTPTS,fps=30,crop=582:620:0:150,scale=960:1022,pad=960:1080:0:58:color=07111f,drawtext=fontfile=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc:text='Gazebo 真實模擬畫面':fontcolor=white:fontsize=26:x=25:y=14[g];[1:v]setpts=PTS-STARTPTS,fps=30,scale=960:1080:force_original_aspect_ratio=decrease,pad=960:1080:(ow-iw)/2:(oh-ih)/2:color=07111f[u];[g][u]hstack=inputs=2:shortest=1[v]" \
  -map "[v]" -r 30 -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -movflags +faststart -shortest "$OUT"
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,r_frame_rate,codec_name -of json "$OUT"
