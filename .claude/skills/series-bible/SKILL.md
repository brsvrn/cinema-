---
name: series-bible
description: Inspect or edit a series' story memory (facts and who knows them, events, threads, timeline, relationships, universe rules, end states). Use before writing episodes and when the owner asks what happened so far.
---
# Series Bible

- Stored as the `series` document; helpers in `worker/studio/bible.py` (`knowledge`, `open_threads`, `memory_brief`, `apply_episode`).
- `apply_episode` runs automatically in the `publish` stage: adds summary, events, facts (with episode number), taught facts, threads, character history and `end_states[n]` (positions, props, env such as lamp/boat signal).
- To retcon: edit the series doc, then re-run `continuity` for affected episodes (`python -m studio produce <id>` after deleting stages from `continuity` onward in state.json).
- Knowledge rule: a character may use a fact only if it is in `known_by` before the episode, or introduced/taught earlier in the same episode.
