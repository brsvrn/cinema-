---
name: new-character
description: Create or modify a persistent character (Character ID, design, voice profile, model sheet, approval). Use when the owner wants a new character or to change a character's look or voice.
---
# New / changed character

- Design keys are documented by the two references in `worker/studio/demo/characters.py` (Ada, Tomo) and read by `studio/rig.py::CharacterRig`.
  Supported: height, head_ratio, head_width, torso_ratio, build, jaw, skin, outline, blush, freckles, lashes, eye_color, eye_size,
  brow_color, brow_thickness, nose, mouth_width, hair{style: curly_bob|short_white, color}, beard, mustache, glasses, hat{color, band, emblem},
  outfit{top: raincoat|sweater, top_color, collar_color, sleeves, hem, flare, bottom: shorts|pants, bottom_color, shoes, scarf, emblem}.
- Voice: `{engine: piper, model, pitch_semitones, speed, noise_scale, elevenlabs_voice_id}`. Keep voices of a cast clearly distinct (pitch ≥4 semitones apart).
- Create with `studio.bible.new_character(spec, series_id)` and `store.put('characters', id, rec)`; add id to `series.characters`.
- Render references: `python -m studio sheets <id>` and look at the PNGs (front/3/4/side/back, expressions, mouth shapes).
- Changing design/voice changes `design_hash`/`voice_hash`: existing episodes keep their hashes; new episodes require re-approval (continuity checker enforces it).
- New hair/outfit styles: add drawing branches in `rig.py` (`_draw_hair_back/_front`, `_draw_torso`), then run `pytest` (test draws every pose × view).
