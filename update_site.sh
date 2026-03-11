# Navigate to the project directory
cd ~/ServerStorage/IranMonitor

git stash
# 1. Force local to match GitHub (clears any conflicts from GitHub Actions)
git fetch origin
git reset --hard origin/main

git stash pop
# 3. Add all changes (updated .db and .json)
git add .

# 4. Commit and Push
# We check if there are changes to avoid empty commit errors
if git diff-index --quiet HEAD --; then
    echo "No changes to commit."
else
    git commit -m "Auto update from local machine: $(date +'%Y-%m-%d %H:%M')"
    git push origin main
fi
