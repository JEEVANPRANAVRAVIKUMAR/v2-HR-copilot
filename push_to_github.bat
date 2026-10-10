@echo off
echo ================================================
echo 🚀 Pushing Enterprise HR Copilot to GitHub...
echo Repository: https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot
echo ================================================

git remote remove origin >nul 2>&1
git remote add origin https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot.git
git add .
git commit -m "fix: greeting crash, precision name search matching, conversational pronoun follow-ups, and full work history collection"
git branch -M main
git push -u origin main --force

echo ================================================
echo ✅ Done! Check repository at:
echo https://github.com/JEEVANPRANAVRAVIKUMAR/v2-HR-copilot
echo ================================================
pause

