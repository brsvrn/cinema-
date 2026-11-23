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
              "azure_voice": "tr-TR-EmelNeural", "azure_pitch": "+18%", "azure_rate": "+6%",
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
              "azure_voice": "tr-TR-AhmetNeural", "azure_pitch": "-10%", "azure_rate": "-8%",
              "description": "Yaşlı, tok, sakin erkek sesi"},
}

NEHIR = {
    "id": "chr_nehir",
    "name": "Kaptan Nehir",
    "role": "mystery",
    "age": 66,
    "personality": "Gizemli, sakin ve esprili yaşlı bir kadın kaptan. Az konuşur ama her sözü bir bilmece gibidir. Denizi ve yıldızları çok iyi tanır.",
    "personality_en": "Mysterious, calm and witty old sea captain. Speaks little, and every word sounds like a riddle. Knows the sea and the stars.",
    "backstory": "Gençliğinde Büyükanne Leyla'nın en yakın arkadaşı ve tekne ortağıydı. Kırk yıldır kırmızı yelkenli Yakamoz ile denizlerde dolaşıyor.",
    "design": {
        "name": "Kaptan Nehir",
        "height": 0.94, "head_ratio": 0.215, "head_width": 0.95, "torso_ratio": 0.3, "build": 1.0, "jaw": 0.95,
        "skin": "#c98e62", "outline": "#2a1d1a", "blush": 0.15, "lashes": True,
        "eye_color": "#3d2a1d", "eye_size": 0.9, "brow_color": "#d9d4cc", "brow_thickness": 1.2, "nose": 1.2,
        "hair": {"style": "curly_bob", "color": "#d9d4cc"},
        "hat": {"color": "#7a1f1a", "band": "#3a0f0c", "emblem": "#e2b341"},
        "outfit": {"top": "raincoat", "top_color": "#1f3a5a", "collar_color": "#14283f", "sleeves": "long",
                   "hem": 0.2, "flare": 1.2, "bottom": "pants", "bottom_color": "#4a3a2a", "shoes": "#2a1c14",
                   "scarf": "#b8322a"},
    },
    "voice": {"engine": "piper", "model": "tr_TR-dfki-medium", "pitch_semitones": 2.0, "speed": 0.92,
              "noise_scale": 0.5, "elevenlabs_voice_id": None,
              "azure_voice": "tr-TR-EmelNeural", "azure_pitch": "-14%", "azure_rate": "-10%",
              "description": "Olgun, sakin, hafif boğuk kadın sesi"},
}

LIGHTHOUSE_ROOM = {
    "id": "loc_fener_odasi",
    "name": "Fener Odası",
    "kind": "lighthouse_room",
    "description": "Fenerin içindeki bekçi odası: beyaz badanalı taş duvarlar, iki pirinç lomboz pencere, harita masası, Büyükanne Leyla'nın fotoğrafı, gemi dümeni, gaz lambası ve yukarı çıkan demir döner merdiven.",
    "description_en": "The keeper's room inside the lighthouse: whitewashed stone walls, brass portholes, a map table, Grandma Leyla's photo, a ship's wheel, an oil lamp and an iron spiral staircase.",
    "palette": {"wall": "#efe4d0", "wood": "#7a4f30"},
    "spots": {"table": 1450, "window": 700, "photo": 1080, "stairs": 2700, "chest": 2350, "center": 1500},
}

HARBOR = {
    "id": "loc_marti_limani",
    "name": "Martı Limanı",
    "kind": "harbor",
    "description": "Martı köyünün küçük limanı: taş iskele, demirli balıkçı tekneleri, mavi panjurlu beyaz evler, uzaktaki burunda fener ve kırmızı yelkenli Yakamoz.",
    "description_en": "Martı village harbor: stone pier, moored fishing boats, white houses with blue shutters, the lighthouse on the far cape and the red-sailed Yakamoz.",
    "palette": {"grass": "#6a9a4f", "stone": "#9a9086"},
    "spots": {"pier_left": 600, "nets": 1100, "center": 1500, "yakamoz": 2250, "pier_right": 2700},
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
