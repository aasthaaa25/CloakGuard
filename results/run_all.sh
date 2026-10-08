#!/usr/bin/env bash
# macOS / Linux one-click run script
# Usage: bash run_all.sh
set -e

echo ""
echo "============================================================"
echo "  Active Defense System -- Full Run (macOS/Linux)"
echo "============================================================"
echo ""

python3 run_all.py

echo ""
echo "All done! Opening report..."
if command -v open &>/dev/null; then
    open report/report.html
elif command -v xdg-open &>/dev/null; then
    xdg-open report/report.html
fi
