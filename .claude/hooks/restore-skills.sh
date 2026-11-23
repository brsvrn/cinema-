#!/usr/bin/env bash
# SessionStart: restore third-party agent skills pinned in skills-lock.json (Remotion skills are not
# redistributed in this public repo; they are fetched from remotion-dev/skills at the locked commit).
cd "$(dirname "$0")/../.." || exit 0
[ -f .claude/skills/remotion-best-practices/SKILL.md ] && exit 0
timeout 90 npx -y skills@1.9.0 experimental_install --frozen-lockfile --agent claude-code --yes >/dev/null 2>&1 || true
exit 0
