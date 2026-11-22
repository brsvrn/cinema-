---
name: new-episode
description: Write and produce a new episode of an existing series with full story continuity. Use when the owner gives an episode topic, asks for the next episode, or wants to edit/re-render an episode script.
---
# New episode

1. Load memory: `cd worker && python -c "from studio.store import get_store; from studio.bible import memory_brief; s=get_store(); ser=s.get('series','<SERIES_ID>'); import json; print(json.dumps(memory_brief(ser,{c:s.get('characters',c) for c in ser['characters']},{l:s.get('locations',l) for l in ser['locations']}),ensure_ascii=False,indent=1))"`
2. Write the script in the schema of `studio/writer.py::SCHEMA_DOC` (see `studio/demo/episodes.py` for references):
   - 30 s: 6–8 short lines (≤70 spoken words total) + 2–4 action beats.
   - Every line has Turkish `text` and English `text_en`.
   - Characters may only use facts they know (`uses_facts`); introduce new facts with `new_facts` and teach with `teaches`.
   - Set `continues_from` to the previous episode number to inherit positions/props/lamp state.
   - Resolve or advance an open thread; open at most one new thread.
   - Only use poses/emotions/objects/sfx listed in `writer._vocab`.
3. Save it as the episode's `script` (`store.put('episodes', '<SERIES>_epNNN', {...,'script': script})`) or enqueue from the app.
4. Run `python -m studio produce <episode_id>`; check `work/<id>/continuity.json` and `qc.json`.
5. Look at `work/<id>/storyboard.png` and a few extracted frames before reporting success.
