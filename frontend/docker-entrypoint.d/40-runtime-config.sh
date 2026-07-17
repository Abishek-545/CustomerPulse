#!/bin/sh
set -eu
API_URL="${API_URL:-http://localhost:8000}"
cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__CUSTOMERPULSE_CONFIG__ = { API_URL: "${API_URL}" };
EOF
