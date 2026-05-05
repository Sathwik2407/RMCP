#!/bin/bash
# RMCP Backend — Start Script
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   RAJ MULTI COLOR PRINT — Order System       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Starting backend server..."
cd "$(dirname "$0")"
python3 server.py
