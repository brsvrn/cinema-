---
name: new-location
description: Add a new persistent procedural location (set) type to the economic engine. Use when a series needs a new place (forest, city street, interior...).
---
# New location kind

1. In `worker/studio/location.py` create a class with the same interface as `LighthouseCliff`:
   `__init__(loc, lighting)`, `set_lighting`, `draw(c, cam, env, dof)`, `draw_foreground(c, cam, env)`, `beam_intensity_at(env, x)`,
   using parallax layers (`cam.apply(c, p)`), seeded RNG from `loc['id']` (geometry must be identical every episode), and `GROUND_Y` for feet.
2. Register it in `LOCATION_KINDS` and add camera targets in `object_camera` + `pipeline.world_objects`.
3. Record: `{id, name, kind, description(_en), palette, spots{name: x}}` → `store.put('locations', ...)`, add to `series.locations`.
4. Verify with a storyboard contact sheet (`Pipeline.stage_storyboard`) under every lighting preset.
