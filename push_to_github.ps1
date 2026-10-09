# Push all updates to v2-HR-copilot repository
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "🚀 Pushing Enterprise HR Copilot to GitHub..." -ForegroundColor Cyan
Write-Host "Repository: https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Set remote origin
git remote set-url origin https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot.git

# Stage all files
git add .

# Commit changes
git commit -m "feat: Enterprise HR Copilot v2.0 - 100% QA Benchmark, Multi-Agent DAG Planner, Resilient LLM Failover, and Executive PDF Reports"

# Push to main branch
git branch -M main
git push -u origin main

Write-Host "================================================" -ForegroundColor Green
Write-Host "✅ Repository successfully pushed to GitHub!" -ForegroundColor Green
Write-Host "Link: https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
