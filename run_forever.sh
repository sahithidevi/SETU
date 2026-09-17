#!/bin/bash
DIR="/Users/sahithi/Desktop/Setu"
cd "$DIR"

# Ensure Python server is running
if ! pgrep -f "server/app.py" > /dev/null; then
  PORT=5001 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 server/app.py > "$DIR/server.log" 2>&1 &
  sleep 2
fi

# Ensure Cloudflare tunnel is running
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
  "$DIR/cloudflared" tunnel --url http://127.0.0.1:5001 > "$DIR/cloudflare.log" 2>&1 &
  sleep 6
fi

# Extract the live URL and write to Desktop and project directory
URL=$(grep -o "https://[a-zA-Z0-9-]*\.trycloudflare\.com" "$DIR/cloudflare.log" | head -n 1)

if [ -n "$URL" ]; then
  echo "$URL" > "$DIR/LIVE_DEMO_LINK.txt"
  echo "Your Setu Live Demo is running at:" > "/Users/sahithi/Desktop/LIVE_SETU_LINK.txt"
  echo "$URL" >> "/Users/sahithi/Desktop/LIVE_SETU_LINK.txt"
fi
