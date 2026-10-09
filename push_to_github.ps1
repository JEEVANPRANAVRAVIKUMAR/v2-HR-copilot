# Push all updates to v2-HR-copilot repository
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "🚀 Pushing Enterprise HR Copilot to GitHub..." -ForegroundColor Cyan
Write-Host "Repository: https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

$repoUrl = "https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot.git"

# Check if origin exists, set or add
$existingRemote = git remote get-url origin 2>$null
if ($existingRemote) {
    git remote set-url origin $repoUrl
} else {
    git remote add origin $repoUrl
}

# Stage all files
git add .

# Commit changes
git commit -m "feat: enhance employee listing with joining dates and collect full work history during onboarding"

# Push to main branch (force push to overwrite remote initial commit)
git branch -M main
git push -u origin main --force

Write-Host "================================================" -ForegroundColor Green
Write-Host "✅ Repository successfully pushed to GitHub!" -ForegroundColor Green
Write-Host "Link: https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green

