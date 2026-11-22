"""Acceptance-test cast: two original characters + one fixed location."""

ADA = {
    "id": "chr_ada",
    "name": "Ada",
    "role": "protagonist",
    "age": 10,
    "personality": "Meraklı, cesur, hızlı konuşan, soru sormayı seven bir kız. Deniz kabuğu toplar.",
    "personality_en": "Curious, brave, talks fast, loves asking questions. Collects sea shells.",
    "backstory": "Yaz tatilini Martı Burnu Feneri'nde dedesi Tomo'nun yanında geçiriyor.",
    "design": {
        "name": "Ada",
        "height": 0.66, "head_ratio": 0.30, "head_width": 0.95, "torso_ratio": 0.26, "build": 0.95,
        "skin": "#f3c9a2", "outline": "#2a1d1a", "blush": 0.25, "freckles": True, "lashes": True,
        "eye_color": "#2f9c63", "eye_size": 1.15, "brow_color": "#8a2f1b",
        "hair": {"style": "curly_bob", "color": "#c9452a"},
        "outfit": {"top": "raincoat", "top_color": "#f4c430", "collar_color": "#e0a91a", "sleeves": "long",
                   "hem": 0.16, "flare": 1.3,
                   "bottom": "shorts", "bottom_color": "#2f5d8a", "shoes": "#1f8a8a", "scarf": "#d8423a"},
    },
    "voice": {"engine": "piper", "model": "tr_TR-dfki-medium", "pitch_semitones": 5.0, "speed": 1.06,
              "noise_scale": 0.6, "elevenlabs_voice_id": None,
              "description": "Genç, enerjik, parlak kız sesi"},
}

TOMO = {
    "id": "chr_tomo",
    "name": "Tomo Dede",
    "role": "mentor",
    "age": 68,
    "personality": "Sakin, bilge, biraz huysuz ama çok sevecen eski bir kaptan. Yavaş ve tok konuşur, deniz hikâyeleri anlatır.",
    "personality_en": "Calm, wise, a bit grumpy but very loving retired sea captain. Speaks slowly, tells sea stories.",
    "backstory": "40 yıl balıkçı teknesinde kaptanlık yaptı, 20 yıldır Martı Burnu Feneri'nin bekçisi.",
    "design": {
        "name": "Tomo Dede",
        "height": 1.0, "head_ratio": 0.21, "head_width": 1.0, "torso_ratio": 0.31, "build": 1.18, "jaw": 1.05,
        "skin": "#e4b48e", "outline": "#2a1d1a", "blush": 0.2,
        "eye_color": "#4a6fa5", "eye_size": 0.85, "brow_color": "#f2f2f2", "brow_thickness": 1.8, "nose": 1.5,
        "hair": {"style": "short_white", "color": "#eeeeee"},
        "beard": "#f1f1ef", "mustache": "#f7f7f5", "mouth_width": 0.9,
        "glasses": True, "glasses_color": "#5a3a22",
        "hat": {"color": "#1f3554", "band": "#121e30", "emblem": "#e2b341"},
        "outfit": {"top": "sweater", "top_color": "#2b4c7e", "emblem": "#e2b341", "sleeves": "long",
                   "hem": 0.04, "flare": 1.05,
                   "bottom": "pants", "bottom_color": "#3b3631", "shoes": "#2a1c14"},
    },
    "voice": {"engine": "piper", "model": "tr_TR-dfki-medium", "pitch_semitones": -2.5, "speed": 0.9,
              "noise_scale": 0.55, "elevenlabs_voice_id": None,
              "description": "Yaşlı, tok, sakin erkek sesi"},
}

LIGHTHOUSE = {
    "id": "loc_marti_burnu",
    "name": "Martı Burnu Feneri",
    "kind": "lighthouse_cliff",
    "description": "Ege kıyısında kırmızı-beyaz çizgili eski bir deniz feneri, önünde çimenli bir yamaç, ahşap çit, bank ve fener direği. Arkada deniz ve uzak adalar.",
    "description_en": "An old red-and-white striped lighthouse on an Aegean cliff with a grassy slope, wooden fence, bench and lamp post. Sea and distant islands behind.",
    "palette": {"tower_a": "#f4f1ea", "tower_b": "#c8382f", "grass": "#5f9a4a", "rock": "#7d7468"},
    "spots": {"door": 2350, "bench": 1100, "fence": 600, "edge": 300, "center": 1600},
}
