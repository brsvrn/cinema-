import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio.bible import design_hash, new_character, new_series, apply_episode, knowledge  # noqa: E402
from studio.continuity import check_script, resolve_blocking  # noqa: E402
from studio.demo.characters import ADA, TOMO, LIGHTHOUSE  # noqa: E402
from studio.demo.episodes import SERIES, EP1, EP2  # noqa: E402
from studio.rig import CharacterRig, RigState, POSES, EXPRESSIONS, VISEMES  # noqa: E402
from studio.storyboard import time_beats  # noqa: E402
from studio.store import LocalStore  # noqa: E402
from studio.tts import voice_hash  # noqa: E402
from studio import audio  # noqa: E402


def world():
    s = new_series(SERIES)
    chars = {c["id"]: new_character(c, s["id"]) for c in (ADA, TOMO)}
    locs = {LIGHTHOUSE["id"]: LIGHTHOUSE}
    return s, chars, locs


def test_rig_draws_every_pose_expression_viseme():
    import skia
    surf = skia.Surface(400, 400)
    for spec in (ADA, TOMO):
        rig = CharacterRig(spec["design"])
        for pose in POSES:
            for turn in (-1, -0.45, 0, 0.45, 1):
                rig.draw(surf.getCanvas(), RigState(pose=dict(POSES[pose]), turn=turn), 200, 390, 0.4)
        for e in EXPRESSIONS:
            for v in VISEMES:
                rig.draw(surf.getCanvas(), RigState(expr=dict(EXPRESSIONS[e]), viseme=v), 200, 390, 0.4)
        rig.draw(surf.getCanvas(), RigState(back=True), 200, 390, 0.4)


def test_character_identity_hashes_are_stable():
    a1 = new_character(ADA, "s")
    a2 = new_character(copy.deepcopy(ADA), "s")
    assert a1["design_hash"] == a2["design_hash"] == design_hash(ADA["design"])
    assert a1["voice_hash"] == voice_hash(ADA["voice"])
    changed = copy.deepcopy(ADA)
    changed["design"]["hair"]["color"] = "#000000"
    assert design_hash(changed["design"]) != a1["design_hash"]


def test_timeline_hits_30_seconds():
    durs = {i: 2.5 for i, b in enumerate(EP1["beats"]) if b["type"] == "line"}
    timed = time_beats(EP1["beats"], durs, 30.0)
    assert abs(timed[-1].end + 1.4 - 30.0) < 0.05
    assert all(t.end > t.start for t in timed)
    # dialogue is never stretched
    for t in timed:
        if t.type == "line":
            assert abs((t.end - t.start) - 2.5) < 1e-6


def test_continuity_ep1_ok_and_ep2_requires_ep1():
    s, chars, locs = world()
    assert check_script(EP1, s, chars, locs)["ok"]
    rep = check_script(EP2, s, chars, locs)
    assert not rep["ok"]  # continues_from=1 not produced yet + facts unknown
    s2 = apply_episode(s, {**EP1, "id": "e1"}, {"blocking": {"chr_ada": {"x": 880, "prop": "shell", "dir": 1}}, "env": {}})
    rep2 = check_script(EP2, s2, chars, locs)
    assert rep2["ok"], rep2
    blocking, _ = resolve_blocking(EP2, s2, chars)
    assert blocking["chr_ada"]["x"] == 880 and blocking["chr_ada"]["prop"] == "shell"


def test_knowledge_violation_detected():
    s, chars, locs = world()
    bad = copy.deepcopy(EP1)
    bad["beats"][1]["uses_facts"] = ["f_light_shell_legend"]
    bad["beats"][1]["speaker"] = "chr_ada"  # Ada does not know the legend yet in ep1
    rep = check_script(bad, s, chars, locs)
    assert any("bilmiyor" in e for e in rep["errors"])


def test_teaching_updates_knowledge():
    s, chars, locs = world()
    s2 = apply_episode(s, {**EP1, "id": "e1"}, {"blocking": {}, "env": {}})
    k = knowledge(s2)
    assert "f_light_shell_legend" in k["chr_ada"]
    assert {t["id"] for t in s2["threads"]} >= {"t_lamp_out", "t_signal"}


def test_unapproved_or_modified_character_blocks_production():
    s, chars, locs = world()
    chars["chr_ada"]["design"]["height"] = 0.9   # silently regenerated character
    rep = check_script(EP1, s, chars, locs)
    assert any("design_hash" in e for e in rep["errors"])


def test_store_roundtrip(tmp_path):
    st = LocalStore(tmp_path)
    st.put("series", "x", {"title": "t"})
    assert st.get("series", "x")["title"] == "t"
    f = tmp_path / "a.txt"
    f.write_text("hi")
    st.upload(f, "k/a.txt")
    assert st.exists("k/a.txt")


def test_audio_synthesis_shapes():
    m = audio.music(3.0, "mystery", "s")
    assert len(m) == 3 * audio.SR and abs(m).max() <= 1.0
    for name in audio.SFX_NAMES:
        x = audio.sfx(name, 1.0)
        assert len(x) > 0 and abs(x).max() <= 1.0


def test_cost_estimate_free_by_default():
    from studio.cost import estimate
    e = estimate("economic")
    assert e["total_usd"] == 0 and not e["requires_paid_approval"]
    g = estimate("cinematic")
    assert g["requires_paid_approval"]
