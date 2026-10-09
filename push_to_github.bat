@echo off
echo ================================================
echo 🚀 Pushing Enterprise HR Copilot to GitHub...
echo Repository: https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot
echo ================================================

git remote set-url origin https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot.git
git add .
git commit -m "feat: Enterprise HR Copilot v2.0 - 100% QA Benchmark, Multi-Agent DAG Planner, Resilient LLM Failover, and Executive PDF Reports"
git branch -M main
git push -u origin main

echo ================================================
echo ✅ Done! Check repository at:
echo https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot
echo ================================================
pause
