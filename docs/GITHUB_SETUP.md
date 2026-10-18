# GitHub Publication Guide
1. Create a new **public** repo named `opsentia-ai-builder-cup` under the team owner's GitHub account. This handoff creates a *local Git-ready project*, not an online repository or live URL.
2. Audit `git status --short`; check for `.env`, tokens, credentials, databases, private content. Rotate the old Gemini key if authentic.
3. From root:
```bash
git init
git add .
git commit -m "chore: bootstrap Opsentia v2 competition handoff"
git branch -M main
gh repo create opsentia-ai-builder-cup --public --source=. --remote=origin --push
```
If `gh` not available, create repo in GitHub UI and `git remote add origin https://github.com/ORG/opsentia-ai-builder-cup.git` then `git push -u origin main`.
4. Create GitHub issues from TASKS.md; protect main; keep CI running; use PRs for code migrations.
5. Before submitting, verify visibility and that README shows real deployed URL and 3-min demo link; no TODO links.
6. GitHub connector in ChatGPT is optional for publishing changes once connected; it requires the user's action and is not connected just because these files exist.
