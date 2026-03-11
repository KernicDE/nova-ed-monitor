from __future__ import annotations

import queue
import re
from typing import Optional

from .state import AppState, BioScan, BodyInfo, EventCategory, LogEvent, MissionInfo
from .tts import TtsMsg


# ── Helpers ────────────────────────────────────────────────────────────────────

def _s(ev: dict, key: str) -> str:
    v = ev.get(key)
    return v if isinstance(v, str) else ""


def _loc(ev: dict, key: str) -> str:
    loc_key = f"{key}_Localised"
    v = ev.get(loc_key) or ev.get(key)
    return v if isinstance(v, str) else ""


def _f(ev: dict, key: str, default: float = 0.0) -> float:
    v = ev.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    return default


def _u(ev: dict, key: str) -> int:
    v = ev.get(key)
    if isinstance(v, int):
        return max(0, v)
    if isinstance(v, float):
        return max(0, int(v))
    return 0


def _b(ev: dict, key: str) -> bool:
    return bool(ev.get(key, False))


def _b_absent_true(ev: dict, key: str) -> bool:
    v = ev.get(key)
    if v is None:
        return True
    return bool(v)


def _strip_economy(s: str) -> str:
    return s.lstrip("$").rstrip(";").strip()


def _fmt_credits(n: int) -> str:
    s = str(n)
    out = []
    for i, c in enumerate(reversed(s)):
        if i > 0 and i % 3 == 0:
            out.append(",")
        out.append(c)
    return "".join(reversed(out)) + " Cr"


# ── Bio species value lookup ──────────────────────────────────────────────────
# Pre-populated from community data; confirmed by game's Analyse event on completion.
# Keyed by English species localised name.
_BIO_SPECIES_VALUES: dict[str, int] = {
    # Aleoida
    "Aleoida Arcus":            7_252_500,
    "Aleoida Coronamus":        6_284_600,
    "Aleoida Gravis":          12_934_900,
    "Aleoida Laminiae":         3_385_200,
    "Aleoida Spica":            3_385_200,
    # Bacterium
    "Bacterium Aurasus":        1_000_600,
    "Bacterium Nebulus":        5_289_900,
    "Bacterium Scopulum":       4_638_000,
    "Bacterium Acies":          1_000_600,
    "Bacterium Vesicula":       1_000_600,
    "Bacterium Alcyoneum":      1_644_500,
    "Bacterium Tela":           1_949_000,
    "Bacterium Informem":       8_418_000,
    "Bacterium Volu":           7_774_000,
    "Bacterium Bullaris":       1_152_500,
    "Bacterium Omentum":        4_638_000,
    "Bacterium Verrata":        3_897_000,
    "Bacterium Caulini":        1_000_600,
    # Cactoida
    "Cactoida Cortexum":        3_667_600,
    "Cactoida Lapis":           2_483_600,
    "Cactoida Peperatis":       2_483_600,
    "Cactoida Pullulanta":      3_667_600,
    "Cactoida Vermis":         16_202_800,
    # Clypeus
    "Clypeus Lacrimam":         8_418_000,
    "Clypeus Margaritus":      11_873_200,
    "Clypeus Speculum":        16_202_800,
    # Concha
    "Concha Aureolas":          7_774_000,
    "Concha Biconcavis":       19_010_800,
    "Concha Labiata":           2_352_400,
    "Concha Renibus":           4_572_400,
    # Electricae
    "Electricae Pluma":         6_284_600,
    "Electricae Radialem":      6_284_600,
    # Fonticulus
    "Fonticulus Campestris":    1_000_600,
    "Fonticulus Digitos":       1_804_900,
    "Fonticulus Fluctus":      20_000_200,
    "Fonticulus Lapida":        3_111_600,
    "Fonticulus Segmentatus":  19_010_800,
    "Fonticulus Upsilon":       5_727_600,
    # Frutexa
    "Frutexa Acus":             7_774_000,
    "Frutexa Collum":           1_639_800,
    "Frutexa Erigia":           1_639_800,
    "Frutexa Flabellum":        1_639_800,
    "Frutexa Flammasis":       10_326_000,
    "Frutexa Metallicum":       1_632_400,
    "Frutexa Sponsae":          6_284_600,
    # Fumerola
    "Fumerola Aquatis":         6_284_600,
    "Fumerola Carbosis":        6_284_600,
    "Fumerola Extremus":       16_202_800,
    "Fumerola Nitris":          7_500_900,
    # Fungoida
    "Fungoida Bullarum":        3_703_200,
    "Fungoida Gelata":          3_330_300,
    "Fungoida Setulus":         1_000_600,
    "Fungoida Stabitis":        2_680_300,
    # Osseus
    "Osseus Cornibus":          1_483_000,
    "Osseus Discus":           12_934_900,
    "Osseus Fractus":           4_027_200,
    "Osseus Pellebantus":       9_739_300,
    "Osseus Pumice":            3_156_300,
    "Osseus Spiralis":          2_404_800,
    # Recepta
    "Recepta Conditivus":      14_313_700,
    "Recepta Deltahedronix":   16_202_800,
    "Recepta Umbrux":          12_934_900,
    # Stratum
    "Stratum Araneamus":        2_448_900,
    "Stratum Cucumisis":       16_202_800,
    "Stratum Excutitus":        2_448_900,
    "Stratum Frigus":           2_637_500,
    "Stratum Laminamus":        2_788_300,
    "Stratum Limaxus":          2_637_500,
    "Stratum Paleas":           1_362_000,
    "Stratum Tectonicas":      19_010_800,
    # Tubus
    "Tubus Cavas":             11_873_200,
    "Tubus Compagibus":         7_774_000,
    "Tubus Conifer":            2_415_500,
    "Tubus Rosarium":           2_637_500,
    "Tubus Sororibus":          5_853_800,
    # Tussock
    "Tussock Albata":           3_252_500,
    "Tussock Capillum":         7_025_800,
    "Tussock Caputus":          3_472_400,
    "Tussock Catena":           1_766_600,
    "Tussock Cultro":           1_766_600,
    "Tussock Divisa":           1_766_600,
    "Tussock Ignis":            1_849_000,
    "Tussock Pennata":          1_000_600,
    "Tussock Pennatis":         1_000_600,
    "Tussock Propagito":        1_000_600,
    "Tussock Serrati":          4_447_100,
    "Tussock Stigmasis":       19_010_800,
    "Tussock Triticum":         7_774_000,
    "Tussock Ventusa":          3_227_700,
    "Tussock Virgam":           1_849_000,
}

# Lowercase-keyed alias for case-insensitive fallback lookups
_BIO_SPECIES_VALUES_LC: dict[str, int] = {k.lower(): v for k, v in _BIO_SPECIES_VALUES.items()}


def _bio_value_lookup(species_loc: str) -> int:
    """Return species value, tolerating case/whitespace mismatches and internal IDs."""
    v = _BIO_SPECIES_VALUES.get(species_loc, 0)
    if v == 0:
        v = _BIO_SPECIES_VALUES_LC.get(species_loc.strip().lower(), 0)
    return v


# Default voices per language — overridable via set_voices()
_LANG_VOICES: dict[str, str] = {
    "en": "en-GB-SoniaNeural",
    "de": "de-DE-KatjaNeural",
    "fr": "fr-FR-DeniseNeural",
    "it": "it-IT-ElsaNeural",
    "es": "es-ES-ElviraNeural",
    "pt": "pt-PT-RaquelNeural",
    "ru": "ru-RU-SvetlanaNeural",
}

_LANG_VERBS: dict[str, str] = {
    "en": "says",
    "de": "sagt",
    "fr": "dit",
    "it": "dice",
    "es": "dice",
    "pt": "diz",
    "ru": "говорит",
}

# Language detection character sets
_CYRILLIC = frozenset("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
_DE_CHARS  = frozenset("äöüßÄÖÜ")
_ES_CHARS  = frozenset("ñÑ¿¡")
_PT_CHARS  = frozenset("ãõÃÕ")

_DE_WORDS = frozenset({
    "und", "ich", "ist", "das", "die", "der", "ein", "eine", "nicht",
    "auf", "du", "wir", "hier", "ja", "nein", "wie", "was", "aber",
    "auch", "noch", "dann", "wenn", "mit", "von", "zu", "an", "im",
    "es", "er", "sie", "ihr", "bitte", "danke", "hallo",
})
_FR_WORDS = frozenset({
    "je", "tu", "il", "nous", "vous", "les", "des", "une", "que",
    "pas", "bonjour", "merci", "oui", "non", "mais", "avec", "sur",
    "dans", "pour", "par", "est", "sont", "salut", "moi", "toi",
})
_IT_WORDS = frozenset({
    "ciao", "grazie", "sono", "che", "non", "una", "come", "per",
    "del", "della", "con", "hai", "lei", "lui", "noi", "voi",
    "bene", "anche", "questo", "prego", "sì", "dio",
})
_ES_WORDS = frozenset({
    "hola", "gracias", "que", "los", "una", "como", "para", "del",
    "con", "por", "pero", "este", "ese", "hay", "está", "son",
    "buenas", "sí", "adios", "tengo", "quiero",
})
_PT_WORDS = frozenset({
    "obrigado", "obrigada", "sim", "não", "para", "como", "uma",
    "com", "por", "mas", "você", "olá", "oi", "bom", "boa",
    "tudo", "bem", "aqui", "isso",
})


def set_voices(voices: dict[str, str]) -> None:
    """Override default TTS voices from config."""
    _LANG_VOICES.update(voices)


def _phonetic_sub(text: str) -> str:
    """Apply phonetic substitutions for TTS pronunciation."""
    text = re.sub(r"\bkernic(?:de)?\b", "Kernik", text, flags=re.IGNORECASE)
    text = re.sub(r"\bly\b", "light years", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcr\b", "credits", text, flags=re.IGNORECASE)
    return text


def _detect_lang(text: str) -> str:
    """Return language code for the detected language of the given text."""
    # Cyrillic is unambiguous
    if any(c in _CYRILLIC for c in text):
        return "ru"
    # ñ/¿/¡ are Spanish-specific
    if any(c in _ES_CHARS for c in text):
        return "es"
    # ã/õ are strongly Portuguese
    if any(c in _PT_CHARS for c in text):
        return "pt"
    # German umlauts / ß
    if any(c in _DE_CHARS for c in text):
        return "de"

    # Score by word list matches
    words = frozenset(re.sub(r"[^\w\s]", "", text.lower()).split())
    scores = {
        "de": len(words & _DE_WORDS),
        "fr": len(words & _FR_WORDS),
        "it": len(words & _IT_WORDS),
        "es": len(words & _ES_WORDS),
        "pt": len(words & _PT_WORDS),
    }
    best_lang, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score > 0:
        return best_lang
    return "en"


def _speak(tts_q: queue.Queue, text: str, priority: bool) -> None:
    try:
        tts_q.put_nowait(TtsMsg(text=_phonetic_sub(text), priority=priority))
    except Exception:
        pass


def _speak_chat(tts_q: queue.Queue, user: str, msg: str, source: str = "") -> None:
    """Speak chat text with language detection. source='Twitch' adds Twitch prefix."""
    try:
        lang  = _detect_lang(msg)
        voice = _LANG_VOICES.get(lang, _LANG_VOICES["en"])
        verb  = _LANG_VERBS.get(lang, "says")
        prefix = f"{source} " if source else ""
        text = f"{prefix}{user} {verb}: {msg}"
        tts_q.put_nowait(TtsMsg(text=_phonetic_sub(text), priority=False, voice=voice))
    except Exception:
        pass


def _tts_cr(n: int) -> str:
    """Format credits for speech (spoken naturally)."""
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f} billion credits"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f} million credits"
    if n >= 1_000:
        return f"{n/1_000:.0f} thousand credits"
    return f"{n} credits"


def _tts_ly(ly: float) -> str:
    """Format light years for speech."""
    if abs(ly - 1.0) < 0.05:
        return "1 light year"
    return f"{ly:.1f} light years"


def _short_body(body_name: str, system: str) -> str:
    if body_name.lower().startswith(system.lower()):
        short = body_name[len(system):].strip()
        if short:
            return short
    return body_name


def _parse_level(ev: dict, is_star: bool) -> int:
    if is_star:
        return 0
    parents = ev.get("Parents")
    if isinstance(parents, list) and parents:
        first = parents[0]
        if isinstance(first, dict):
            key = next(iter(first), "")
            if key == "Planet":
                return 2
    return 1


def is_scoopable(star_class: str) -> bool:
    return star_class in ("O", "B", "A", "F", "G", "K", "M")


def genus_min_dist(genus: str) -> float:
    g = genus.lower()
    if "aleoida"    in g: return 150.0
    if "bacterium"  in g: return 500.0
    if "cactoida"   in g: return 300.0
    if "clypeus"    in g: return 150.0
    if "concha"     in g: return 150.0
    if "electricae" in g: return 1000.0
    if "fonticulua" in g: return 500.0
    if "frutexa"    in g: return 150.0
    if "fumerola"   in g: return 100.0
    if "fungoida"   in g: return 300.0
    if "osseus"     in g: return 800.0
    if "recepta"    in g: return 150.0
    if "stratum"    in g: return 500.0
    if "tubus"      in g: return 800.0
    if "tussock"    in g: return 200.0
    if "brain"      in g: return 100.0
    if "sinuous"    in g: return 100.0
    if "crystall"   in g: return 0.0
    return 500.0


_SHIP_NAMES: dict[str, str] = {
    "sidewinder":                "Sidewinder",
    "eagle":                     "Eagle",
    "hauler":                    "Hauler",
    "adder":                     "Adder",
    "viper":                     "Viper MkIII",
    "viper_mkiv":                "Viper MkIV",
    "cobramkiii":                "Cobra MkIII",
    "cobramkiv":                 "Cobra MkIV",
    "type6":                     "Type-6 Transporter",
    "type7":                     "Type-7 Transporter",
    "type8":                     "Type-8 Transporter",
    "type9":                     "Type-9 Heavy",
    "type9_military":            "Type-10 Defender",
    "asp":                       "Asp Explorer",
    "asp_scout":                 "Asp Scout",
    "vulture":                   "Vulture",
    "empire_eagle":              "Imperial Eagle",
    "empire_courier":            "Imperial Courier",
    "empire_clipper":            "Imperial Clipper",
    "empire_trader":             "Imperial Cutter",
    "federation_gunship":        "Federal Gunship",
    "federation_dropship":       "Federal Dropship",
    "federation_dropship_mkii":  "Federal Assault Ship",
    "federation_corvette":       "Federal Corvette",
    "independant_trader":        "Keelback",
    "ferdelance":                "Fer-de-Lance",
    "anaconda":                  "Anaconda",
    "python":                    "Python",
    "python_nx":                 "Python MkII",
    "orca":                      "Orca",
    "belugaliner":               "Beluga Liner",
    "diamondback":               "Diamondback Scout",
    "diamondbackxl":             "Diamondback Explorer",
    "dolphin":                   "Dolphin",
    "krait_mkii":                "Krait MkII",
    "krait_light":               "Krait Phantom",
    "mamba":                     "Mamba",
    "corsair":                   "Corsair",
    "mandalay":                  "Mandalay",
}


def _fmt_ship_type(raw: str) -> str:
    key = raw.lower().strip()
    if key in _SHIP_NAMES:
        return _SHIP_NAMES[key]
    return " ".join(w.capitalize() for w in raw.split("_") if w)


def _fmt_pop(n: int) -> str:
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
    if n >= 1_000:         return f"{n/1_000:.1f}K"
    return str(n)


def _placeholder_body(name: str, body_id: int) -> BodyInfo:
    return BodyInfo(
        name=name, body_id=body_id, level=1,
        planet_class="", star_type="", atmosphere="",
        terraform=False, landable=False,
        bio_signals=0, geo_signals=0, bio_genuses=[],
        dist_ls=0.0, value=0,
        first_discovered=False, first_mapped=False,
        mapped=False, fss_scanned=False,
        radius=3_000_000.0,
    )


def natural_key(s: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ── Main event handler ─────────────────────────────────────────────────────────

def handle(ev: dict, state: AppState, tts_q: queue.Queue) -> Optional[LogEvent]:
    event = _s(ev, "event")

    match event:

        # ── Navigation ───────────────────────────────────────────────────────

        case "FSDJump" | "CarrierJump":
            system     = _s(ev, "StarSystem")
            dist       = _f(ev, "JumpDist")
            fuel       = _f(ev, "FuelLevel")
            pop        = _u(ev, "Population")
            economy    = _loc(ev, "SystemEconomy")
            security   = _loc(ev, "SystemSecurity")
            gov        = _loc(ev, "SystemGovernment")
            allegiance = _s(ev, "SystemAllegiance")
            star_class = _s(ev, "StarClass")
            scoopable  = is_scoopable(star_class)

            state.system     = system
            state.population = pop
            state.economy    = _strip_economy(economy)
            state.security   = _strip_economy(security)
            state.government = gov
            state.allegiance = allegiance
            state.jump_dist  = dist
            state.jump_dist_total = getattr(state, 'jump_dist_total', 0.0) + dist
            state.fuel       = fuel
            state.fuel_announced = False
            state.discovery_announced = False
            state.hull       = _f(ev, "Health") if "Health" in ev else state.hull
            state.lat        = None
            state.lon        = None
            state.station    = ""
            state.bodies.clear()
            state.bio_scans.clear()
            state.nearest_body        = ""
            state.approach_body       = ""
            state.first_footfall_body = ""
            star_pos = ev.get("StarPos")
            if isinstance(star_pos, list) and len(star_pos) == 3:
                state.star_pos = tuple(star_pos)
            else:
                state.star_pos = None
            state.station_count  = 0
            state.fss_body_count = 0
            _parse_factions(ev, state)
            if state.route_hops > 0:
                state.route_hops -= 1
                if isinstance(state.route_list, list) and len(state.route_list) > 1:
                    # Remove current system from the start of the list
                    state.route_list.pop(0)
                    if len(state.route_list) > 1:
                        # Re-calculate distance to the now-become-first jump
                        p1 = state.route_list[0].get("StarPos")
                        p2 = state.route_list[1].get("StarPos")
                        if isinstance(p1, list) and isinstance(p2, list):
                            state.route_next_dist = ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)**0.5
                        else:
                            state.route_next_dist = 0.0
                    else:
                        state.route_next_dist = 0.0

            if state.route_hops == 0:
                state.route_destination    = ""
                state.route_next           = ""
                state.route_next_star      = ""
                state.route_next_scoopable = False
                state.route_next_dist      = 0.0
                state.route_list           = []

            hops = state.route_hops
            msg  = f"Arrived in {system}. Jump {dist:.1f} light years."
            if star_class:
                scoop_txt = "scoopable" if scoopable else "not scoopable"
                msg += f" Star {star_class}, {scoop_txt}."
            if hops > 0:
                word = "jump" if hops == 1 else "jumps"
                msg += f" {hops} {word} remaining."
            if pop > 0:
                msg += f" Pop: {_fmt_pop(pop)}."
            tts_msg = f"Arrived in {system}. Jump {_tts_ly(dist)}."
            if star_class:
                scoop_txt = "scoopable" if scoopable else "not scoopable"
                tts_msg += f" Star {star_class}, {scoop_txt}."
            if hops > 0:
                word = "jump" if hops == 1 else "jumps"
                tts_msg += f" {hops} {word} remaining."
            if pop > 0:
                tts_msg += f" Pop: {_fmt_pop(pop)}."
            _speak(tts_q, tts_msg, False)
            return LogEvent.new(EventCategory.Nav, msg)

        case "Location":
            state.system     = _s(ev, "StarSystem")
            state.population = _u(ev, "Population")
            state.economy    = _strip_economy(_loc(ev, "SystemEconomy"))
            state.security   = _strip_economy(_loc(ev, "SystemSecurity"))
            state.government = _loc(ev, "SystemGovernment")
            state.allegiance = _s(ev, "SystemAllegiance")
            state.hull       = _f(ev, "Health") if "Health" in ev else state.hull
            _parse_factions(ev, state)
            return LogEvent.new(EventCategory.System, f"Location: {state.system}.")

        case "NavRoute":
            route = ev.get("Route")
            if not isinstance(route, list) or len(route) < 2:
                return None
            dest      = _s(route[-1], "StarSystem")
            hops      = len(route) - 1
            next_sys  = _s(route[1], "StarSystem")
            next_star = _s(route[1], "StarClass")
            state.route_destination    = dest
            state.route_hops           = hops
            state.route_next           = next_sys
            state.route_next_star      = next_star
            state.route_next_scoopable = is_scoopable(next_star)

            # Calculate total distance and store full route
            def _pdist(p1, p2):
                if not isinstance(p1, list) or not isinstance(p2, list): return 0.0
                return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)**0.5
            
            tdist = 0.0
            for i in range(len(route)-1):
                tdist += _pdist(route[i].get("StarPos"), route[i+1].get("StarPos"))
            
            state.route_dist      = tdist
            state.route_next_dist = _pdist(route[0].get("StarPos"), route[1].get("StarPos"))
            state.route_list      = route

            word = "jump" if hops == 1 else "jumps"
            msg  = f"Route set. Destination: {dest}. {hops} {word} ({tdist:.1f} ly)."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Nav, msg)

        case "NavRouteClear":
            state.route_destination    = ""
            state.route_hops           = 0
            state.route_next           = ""
            state.route_next_star      = ""
            state.route_next_scoopable = False
            _speak(tts_q, "Route cleared.", False)
            return LogEvent.new(EventCategory.Nav, "Route cleared.")

        case "SupercruiseEntry":
            state.approach_body = ""
            state.hull = _f(ev, "Health") if "Health" in ev else state.hull
            return LogEvent.new(EventCategory.Nav, "Supercruise engaged.")

        case "SupercruiseExit":
            body = _s(ev, "Body")
            msg  = f"Supercruise disengaged near {_short_body(body, state.system)}." if body else "Supercruise disengaged."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Nav, msg)

        case "ApproachBody":
            state.approach_body = _s(ev, "Body")
            return None

        case "LeaveBody":
            state.approach_body = ""
            return None

        case "Docked":
            station      = _s(ev, "StationName")
            state.station          = station
            state.docked           = True
            state.station_type     = _s(ev, "StationType")
            state.station_economy  = _loc(ev, "StationEconomy")
            state.station_allegiance = _s(ev, "StationAllegiance")
            state.station_services = ev.get("StationServices") or []
            state.station_dist_ls  = _f(ev, "DistFromStarLS")
            msg = f"Docked at {station}."
            _speak(tts_q, msg, True)
            return LogEvent.new(EventCategory.Nav, msg)

        case "Undocked":
            station      = state.station
            state.station          = ""
            state.docked           = False
            state.station_type     = ""
            state.station_economy  = ""
            state.station_allegiance = ""
            state.station_services = []
            state.station_dist_ls  = 0.0
            msg = f"Undocked from {station}." if station else "Undocked."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Nav, msg)

        case "Touchdown":
            lat            = _f(ev, "Latitude")
            lon            = _f(ev, "Longitude")
            body           = _s(ev, "Body")
            first_footfall = _b(ev, "FirstFootfall")
            state.lat    = lat
            state.lon    = lon
            state.landed = True
            if first_footfall and body:
                state.first_footfall_body = body
                # Mark any bio scans already recorded on this body
                for sc in state.bio_scans:
                    if sc.body == body:
                        sc.first_footfall = True
                _speak(tts_q, "First footfall on this world!", True)
                msg = f"FIRST FOOTFALL! Touchdown at {lat:.2f}, {lon:.2f}."
                return LogEvent.new(EventCategory.Explore, msg)
            msg = f"Touchdown at {lat:.2f}, {lon:.2f}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Nav, msg)

        case "Liftoff":
            state.landed = False
            _speak(tts_q, "Liftoff.", False)
            return LogEvent.new(EventCategory.Nav, "Liftoff.")

        # ── Combat ───────────────────────────────────────────────────────────

        case "UnderAttack":
            target = _s(ev, "Target")
            msg    = f"Warning! Under attack! Target: {target}." if target else "Warning! Under attack!"
            _speak(tts_q, msg, True)
            return LogEvent.new(EventCategory.Warn, msg)

        case "ShieldState":
            up = ev.get("ShieldsUp")
            up = bool(up) if up is not None else True
            state.shields_up = up
            if not up:
                _speak(tts_q, "Warning! Shields offline!", True)
                return LogEvent.new(EventCategory.Warn, "Shields offline!")
            else:
                _speak(tts_q, "Shields restored.", False)
                return LogEvent.new(EventCategory.Combat, "Shields restored.")

        case "HullDamage":
            health     = _f(ev, "Health")
            state.hull = health
            pct        = round(health * 100.0)
            if pct <= 50.0:
                msg = f"Critical! Hull at {int(pct)}%!"
                _speak(tts_q, f"Critical! Hull at {int(pct)} percent!", True)
                return LogEvent.new(EventCategory.Warn, msg)
            elif pct <= 75.0:
                msg = f"Hull damage: {int(pct)}%."
                _speak(tts_q, f"Hull damage: {int(pct)} percent.", False)
                return LogEvent.new(EventCategory.Combat, msg)
            else:
                return LogEvent.new(EventCategory.Combat, f"Hull at {int(pct)}%.")

        case "Died":
            state.hull = 0.0
            killers = ev.get("Killers")
            if isinstance(killers, list):
                names = [_s(k, "Name") for k in killers]
                msg   = f"Destroyed by: {', '.join(names)}."
            else:
                msg = "You have been destroyed."
            _speak(tts_q, msg, True)
            return LogEvent.new(EventCategory.Warn, msg)

        case "Bounty":
            reward = (ev.get("TotalReward") or ev.get("Reward") or 0)
            if isinstance(reward, float): reward = int(reward)
            victim = _s(ev, "Target")
            suffix = f" Target: {victim}" if victim else ""
            msg    = f"Bounty: {_fmt_credits(reward)}{suffix}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Combat, msg)

        case "FactionKillBond":
            reward = _u(ev, "Reward")
            msg    = f"Combat bond: {_fmt_credits(reward)}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Combat, msg)

        # ── Exploration ──────────────────────────────────────────────────────

        case "Scan":
            scan_type    = _s(ev, "ScanType")
            body_name    = _s(ev, "BodyName")
            planet_class = _loc(ev, "PlanetClass")
            star_type    = _s(ev, "StarType")
            terraform    = _s(ev, "TerraformState")
            landable     = _b(ev, "Landable")
            atmosphere   = _loc(ev, "AtmosphereType")
            dist_ls      = _f(ev, "DistFromArrivalLS") or _f(ev, "DistanceFromArrivalLS")
            value        = _u(ev, "EstimatedValue")
            radius       = _f(ev, "Radius")
            body_id      = _u(ev, "BodyID")
            terraformable = terraform in ("Terraformable", "Terraforming")
            is_star      = bool(star_type)
            level        = _parse_level(ev, is_star)
            short        = _short_body(body_name, state.system)

            just_dss_scanned = body_name in state.dss_recently_completed
            if just_dss_scanned:
                state.dss_recently_completed.discard(body_name)

            if body_name:
                state.upsert_body(BodyInfo(
                    name=body_name, body_id=body_id, level=level,
                    planet_class=planet_class, star_type=star_type, atmosphere=atmosphere,
                    terraform=terraformable, landable=landable,
                    bio_signals=0, geo_signals=0, bio_genuses=[],
                    dist_ls=dist_ls, value=value,
                    first_discovered=not _b(ev, "WasDiscovered"),
                    first_mapped=not _b(ev, "WasMapped"),
                    mapped=False, fss_scanned=scan_type == "Detailed",
                    radius=radius,
                ))

            if scan_type not in ("Detailed", "AutoScan"):
                return None

            if scan_type == "AutoScan" and is_star and not _b(ev, "WasDiscovered"):
                if not state.discovery_announced:
                    state.discovery_announced = True
                    _speak(tts_q, "Undiscovered system.", False)

            if just_dss_scanned:
                return None

            bio_count = next((b.bio_signals for b in state.bodies if b.name == body_name), 0)
            geo_count = next((b.geo_signals for b in state.bodies if b.name == body_name), 0)

            valuable   = planet_class in ("Earthlike body", "Water world", "Ammonia world", "Metal rich body")
            rare_star  = star_type in ("N", "H", "D")
            high_value = value > 500_000 and not is_star

            sig_parts = []
            if bio_count > 0:
                sig_parts.append(f"{bio_count} bio signal{'s' if bio_count != 1 else ''}")
            if geo_count > 0:
                sig_parts.append(f"{geo_count} geo signal{'s' if geo_count != 1 else ''}")

            if valuable or terraformable or rare_star or high_value:
                parts = []
                if planet_class: parts.append(planet_class)
                match star_type:
                    case "N": parts.append("Neutron star!")
                    case "H": parts.append("Black hole!")
                    case "D": parts.append("White dwarf.")
                if terraformable: parts.append("Terraformable.")
                if landable:      parts.append("Landable.")
                parts.extend(sig_parts)
                detail = " ".join(parts)
                msg    = f"Notable: {short}. {detail}"
                _speak(tts_q, msg, valuable or star_type in ("N", "H"))
                return LogEvent.new(EventCategory.Explore, msg)
            elif scan_type == "Detailed":
                parts = []
                if planet_class: parts.append(planet_class)
                if landable:     parts.append("Landable.")
                parts.extend(sig_parts)
                detail = " ".join(parts)
                msg    = f"Scan: {short}. {detail}"
                _speak(tts_q, msg, False)
                return LogEvent.new(EventCategory.Explore, msg)
            else:
                return None

        case "SAAScanComplete":
            body_name = _s(ev, "BodyName")
            short     = _short_body(body_name, state.system)
            bio_count = 0
            geo_count = 0
            for b in state.bodies:
                if b.name == body_name:
                    b.mapped  = True
                    bio_count = b.bio_signals
                    geo_count = b.geo_signals
                    break
            state.dss_recently_completed.add(body_name)

            sig_parts = []
            if bio_count > 0:
                sig_parts.append(f"{bio_count} bio")
            if geo_count > 0:
                sig_parts.append(f"{geo_count} geo")
            msg = f"Mapped: {short}."
            if sig_parts:
                msg += f" Signals: {', '.join(sig_parts)}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Explore, msg)

        case "FSSDiscoveryScan":
            total = _u(ev, "BodyCount")
            state.fss_body_count = total
            msg   = f"Honk complete. {total} bodies detected."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Explore, msg)

        case "FSSBodySignals":
            body_name = _s(ev, "BodyName")
            body_id   = _u(ev, "BodyID")
            short     = _short_body(body_name, state.system)

            if not any(b.name == body_name for b in state.bodies):
                state.upsert_body(_placeholder_body(body_name, body_id))

            bio_count = 0
            geo_count = 0
            sigs = ev.get("Signals")
            if isinstance(sigs, list):
                for sig in sigs:
                    sig_type = _loc(sig, "Type")
                    count    = _u(sig, "Count")
                    for b in state.bodies:
                        if b.name == body_name:
                            if "Biological"   in sig_type: b.bio_signals = count; bio_count = count
                            elif "Geological" in sig_type: b.geo_signals = count; geo_count = count

            parts = []
            if bio_count > 0:
                s = "biological signal" if bio_count == 1 else "biological signals"
                parts.append(f"{bio_count} {s}")
            if geo_count > 0:
                s = "geological signal" if geo_count == 1 else "geological signals"
                parts.append(f"{geo_count} {s}")

            if parts:
                msg = f"{short}: {', '.join(parts)}."
                return LogEvent.new(EventCategory.Explore, msg)
            return None

        case "FSSSignalDiscovered":
            sig = _loc(ev, "SignalName")
            if any(k in sig for k in ("Guardian", "Thargoid", "Unknown", "Encoded")):
                msg = f"Signal detected: {sig}!"
                _speak(tts_q, msg, True)
                return LogEvent.new(EventCategory.Explore, msg)
            return None

        case "CodexEntry":
            name = _loc(ev, "Name")
            cat  = _loc(ev, "Category")
            if not name:
                return None
            msg = f"Codex: {name}."
            # Don't double-announce bio entries — ScanOrganic/Log already speaks them
            if "iol" not in cat.lower():  # "biology" / "biologie"
                _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Explore, msg)

        case "SAASignalsFound":
            body_name = _s(ev, "BodyName")
            body_id   = _u(ev, "BodyID")
            signals   = ev.get("Signals") or []
            genuses   = ev.get("Genuses") or []

            if not any(b.name == body_name for b in state.bodies):
                state.upsert_body(_placeholder_body(body_name, body_id))

            for b in state.bodies:
                if b.name == body_name:
                    for sig in signals:
                        sig_type = _loc(sig, "Type")
                        count    = _u(sig, "Count")
                        if "Biological"   in sig_type: b.bio_signals = count
                        elif "Geological" in sig_type: b.geo_signals = count
                    b.bio_genuses = [n for n in (_loc(g, "Genus") for g in genuses) if n]
                    break
            return None

        case "ScanOrganic":
            scan_type   = _s(ev, "ScanType")
            species     = _s(ev, "Species")
            species_loc = _loc(ev, "Species")
            genus_loc   = _loc(ev, "Genus")
            body_id     = _u(ev, "Body")

            body_name = next((b.name for b in state.bodies if b.body_id == body_id), "Unknown")
            if body_name == "Unknown":
                body_name = state.nearest_body or state.system or "Unknown"

            body_radius = next(
                (b.radius for b in state.bodies if b.name == body_name),
                3_000_000.0
            )

            match scan_type:
                case "Log":
                    first_disc = _b_absent_true(ev, "WasDiscovered") is False
                    first_logged = _b_absent_true(ev, "WasLogged") is False
                    
                    if not any(sc.species == species for sc in state.bio_scans):
                        base_val = _bio_value_lookup(species_loc)
                        if first_disc or first_logged:
                            base_val *= 5

                        is_first_footfall = (
                            bool(state.first_footfall_body) and
                            body_name == state.first_footfall_body
                        )
                        state.bio_scans.append(BioScan(
                            species=species, species_localised=species_loc,
                            genus_localised=genus_loc, body=body_name,
                            samples=1, min_dist=genus_min_dist(genus_loc),
                            last_lat=state.lat, last_lon=state.lon,
                            body_radius=body_radius, current_dist=None,
                            value=base_val,
                            alerted=False, complete=False,
                            first_discovered=first_disc or first_logged,
                            first_footfall=is_first_footfall,
                        ))
                    tag     = " — new species!" if first_logged else ""
                    tts_tag = " New species!" if first_logged else ""
                    _speak(tts_q, f"Biological: {species_loc}.{tts_tag}", False)
                    return LogEvent.new(EventCategory.Explore, f"Bio{tag}: {species_loc} [{genus_loc}]")

                case "Sample":
                    lat, lon = state.lat, state.lon
                    count = 2
                    for sc in state.bio_scans:
                        if sc.species == species:
                            sc.samples = sc.samples + 1
                            if lat is not None and lon is not None:
                                sc.sample_lats.append(lat)
                                sc.sample_lons.append(lon)
                            sc.last_lat    = lat
                            sc.last_lon    = lon
                            sc.alerted     = False
                            sc.current_dist = None
                            count = sc.samples
                            break
                            
                    if count == 2:
                        msg = f"Bio sample {count}/3: {species_loc}."
                        _speak(tts_q, msg, False)
                        return LogEvent.new(EventCategory.Explore, msg)
                    return None

                case "Analyse":
                    value = _u(ev, "Value")
                    for sc in state.bio_scans:
                        if sc.species == species:
                            sc.samples  = 3
                            if value > 0:
                                sc.value = value   # keep lookup-table value if game gives 0
                            sc.complete = True
                            break
                    val_str = _tts_cr(value) if value > 0 else "unknown"
                    msg_tts = f"Bio complete: {species_loc}. Value: {val_str}."
                    msg_log = f"Bio complete: {species_loc}. Value: {_fmt_credits(value) if value > 0 else '?'}."
                    _speak(tts_q, msg_tts, False)
                    return LogEvent.new(EventCategory.Explore, msg_log)

                case _:
                    return None

        # ── Missions ─────────────────────────────────────────────────────────

        case "MissionAccepted":
            mid      = _u(ev, "MissionID")
            name     = _loc(ev, "LocalisedName") or _s(ev, "Name")
            dest_sys = _s(ev, "DestinationSystem")
            dest_stn = _s(ev, "DestinationStation")
            dest     = f"{dest_sys} / {dest_stn}" if dest_stn else dest_sys
            expiry   = _s(ev, "Expiry")
            state.missions.append(MissionInfo(
                mission_id=mid, name=name, destination=dest, expiry=expiry,
            ))
            return None

        case "MissionCompleted":
            mid    = _u(ev, "MissionID")
            reward = _u(ev, "Reward")
            name   = _loc(ev, "LocalisedName") or _s(ev, "Name")
            state.remove_mission(mid)
            msg = f"Mission complete: {name}. Reward: {_fmt_credits(reward)}."
            _speak(tts_q, f"Mission complete: {name}. Reward: {_tts_cr(reward)}.", False)
            return LogEvent.new(EventCategory.Mission, msg)

        case "MissionFailed":
            mid  = _u(ev, "MissionID")
            name = _loc(ev, "LocalisedName") or _s(ev, "Name")
            state.remove_mission(mid)
            msg  = f"Mission failed: {name}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Mission, msg)

        case "MissionAbandoned":
            mid = _u(ev, "MissionID")
            state.remove_mission(mid)
            return None

        case "MissionRedirected":
            mid     = _u(ev, "MissionID")
            new_sys = _s(ev, "NewDestinationSystem")
            new_stn = _s(ev, "NewDestinationStation")
            for m in state.missions:
                if m.mission_id == mid:
                    m.destination = f"{new_sys} / {new_stn}" if new_stn else new_sys
                    break
            return None

        # ── Economy & Trade ──────────────────────────────────────────────────

        case "MarketSell":
            commodity = _loc(ev, "Type")
            count     = _u(ev, "Count")
            total     = _u(ev, "TotalSale")
            profit    = _u(ev, "TotalProfit")
            msg = f"Sold: {count}x {commodity} for {_fmt_credits(total)}."
            if profit > 0:
                msg += f" Profit: {_fmt_credits(profit)}."
            tts_sell = f"Sold: {count}x {commodity} for {_tts_cr(total)}."
            if profit > 0:
                tts_sell += f" Profit: {_tts_cr(profit)}."
            _speak(tts_q, tts_sell, False)
            return LogEvent.new(EventCategory.Trade, msg)

        case "Materials":
            # Full material list from journal (fired on login/session start)
            def _mat_dict(items) -> dict:
                result = {}
                for m in (items or []):
                    if not isinstance(m, dict): continue
                    loc  = m.get("Name_Localised") or m.get("Name", "")
                    cnt  = int(m.get("Count", 0))
                    if loc: result[loc] = cnt
                return result
            state.materials_raw = _mat_dict(ev.get("Raw"))
            state.materials_mfg = _mat_dict(ev.get("Manufactured"))
            state.materials_enc = _mat_dict(ev.get("Encoded"))
            return None

        case "MaterialCollected":
            cat = _s(ev, "Category").lower()
            loc = _s(ev, "Name_Localised") or _s(ev, "Name")
            cnt = _u(ev, "Count")
            if "raw"           in cat: state.materials_raw[loc] = state.materials_raw.get(loc, 0) + cnt
            elif "manufactured" in cat: state.materials_mfg[loc] = state.materials_mfg.get(loc, 0) + cnt
            elif "encoded"      in cat: state.materials_enc[loc] = state.materials_enc.get(loc, 0) + cnt
            return None

        case "MaterialDiscarded":
            cat = _s(ev, "Category").lower()
            loc = _s(ev, "Name_Localised") or _s(ev, "Name")
            cnt = _u(ev, "Count")
            if "raw"           in cat: state.materials_raw[loc] = max(0, state.materials_raw.get(loc, 0) - cnt)
            elif "manufactured" in cat: state.materials_mfg[loc] = max(0, state.materials_mfg.get(loc, 0) - cnt)
            elif "encoded"      in cat: state.materials_enc[loc] = max(0, state.materials_enc.get(loc, 0) - cnt)
            return None

        # ── Engineers ────────────────────────────────────────────────────────

        case "EngineerProgress":
            # Bulk event at session start: {"Engineers": [...]}
            bulk = ev.get("Engineers")
            if isinstance(bulk, list):
                for entry in bulk:
                    if not isinstance(entry, dict):
                        continue
                    n = entry.get("Engineer", "")
                    p = entry.get("Progress", "")
                    r = int(entry.get("Rank", 0))
                    if n and p:
                        state.engineers[n] = (r, p)
                return None
            # Individual event
            engineer = _s(ev, "Engineer")
            progress = _s(ev, "Progress")
            rank     = _u(ev, "Rank")
            if engineer:
                state.engineers[engineer] = (rank, progress)
            if progress == "Unlocked":
                msg = f"Engineer unlocked: {engineer}!"
                _speak(tts_q, msg, True)
                return LogEvent.new(EventCategory.Mission, msg)
            elif rank > 0:
                msg = f"Engineer {engineer}: rank {rank}."
                _speak(tts_q, msg, False)
                return LogEvent.new(EventCategory.Mission, msg)
            return None

        # ── Loadout / Session init ───────────────────────────────────────────

        case "Fileheader":
            return None  # Journal session start marker, no state to update

        case "LoadGame":
            state.commander  = _s(ev, "Commander")
            state.ship_type  = _fmt_ship_type(_s(ev, "Ship"))
            state.ship_name  = _s(ev, "ShipName")
            state.ship_ident = _s(ev, "ShipIdent")
            state.fuel       = _f(ev, "FuelLevel")
            state.fuel_max   = _f(ev, "FuelCapacity")
            # Grab health from login if present
            state.hull       = _f(ev, "HullHealth", 1.0)
            msg = f"CMDR {state.commander} online."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.System, msg)

        case "Shutdown":
            msg = "Systems powering down. Farewell, Commander."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.System, "Game shutdown detected.")

        case "Loadout":
            fuel_cap = ev.get("FuelCapacity")
            if isinstance(fuel_cap, dict):
                state.fuel_max = _f(fuel_cap, "Main")
            state.cargo_capacity = _u(ev, "CargoCapacity")
            state.ship_type  = _fmt_ship_type(_s(ev, "Ship"))
            state.ship_name  = _s(ev, "ShipName")
            state.ship_ident = _s(ev, "ShipIdent")
            # Correct hull health from loadout
            state.hull = _f(ev, "HullHealth", 1.0)
            return None

        case "Repair":
            item = _s(ev, "Item")
            if item == "Wear" or "hull" in item.lower():
                state.hull = 1.0
                return LogEvent.new(EventCategory.Status, "Hull repaired.")
            return None

        case "RepairAll":
            state.hull = 1.0
            return LogEvent.new(EventCategory.Status, "Full repair complete.")

        case "Resurrect":
            state.hull       = 1.0
            state.shields_up = True
            return LogEvent.new(EventCategory.Status, "Respawned at station.")

        # ── Status / Misc ────────────────────────────────────────────────────

        case "FuelScoop":
            total      = _f(ev, "Total")
            state.fuel = total
            # Use stricter threshold and check flag to avoid double messages
            is_full    = state.fuel_max > 0.0 and total >= (state.fuel_max - 0.05)
            if is_full and not state.fuel_announced:
                state.fuel_announced = True
                _speak(tts_q, "Fuel tank full.", False)
            return LogEvent.new(EventCategory.Status, f"Fuel: {total:.1f}/{state.fuel_max:.0f}t.")

        case "Interdicted":
            submitted   = _b(ev, "Submitted")
            interdictor = _s(ev, "Interdictor")
            if submitted:
                msg = f"Interdiction submitted to {interdictor}." if interdictor else "Interdiction submitted."
            else:
                msg = f"Interdiction escaped from {interdictor}!" if interdictor else "Interdiction escaped!"
            _speak(tts_q, msg, not submitted)
            cat = EventCategory.Combat if submitted else EventCategory.Warn
            return LogEvent.new(cat, msg)

        case "Interdiction":
            success = _b(ev, "Success")
            victim  = _s(ev, "Interdicted")
            if success:
                msg = f"Interdiction successful: {victim}." if victim else "Interdiction successful."
            else:
                msg = "Interdiction failed."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Combat, msg)

        case "ReceiveText":
            channel = _s(ev, "Channel")
            sender  = _s(ev, "From")
            text    = _loc(ev, "Message")
            if not text or text.startswith("$"):
                return None

            match channel:
                case "player":
                    msg = f"{sender}: {text}"
                    _speak_chat(tts_q, f"Message from {sender}", text)
                    return LogEvent.new(EventCategory.Chat, msg)
                case "wing":
                    msg = f"[Wing] {sender}: {text}"
                    _speak_chat(tts_q, f"Wing message from {sender}", text)
                    return LogEvent.new(EventCategory.Chat, msg)
                case "local":
                    msg = f"[Local] {sender}: {text}"
                    _speak_chat(tts_q, f"Local {sender}", text)
                    return LogEvent.new(EventCategory.Chat, msg)
                case "squadron":
                    msg = f"[Sqn] {sender}: {text}"
                    _speak_chat(tts_q, f"Squadron {sender}", text)
                    return LogEvent.new(EventCategory.Chat, msg)
                case "starsystem":
                    msg = f"[System] {sender}: {text}"
                    return LogEvent.new(EventCategory.Chat, msg)
                case "friend":
                    msg = f"[Friend] {sender}: {text}"
                    return LogEvent.new(EventCategory.Chat, msg)
                case _:
                    return None

        case "DockingGranted":
            stn  = _s(ev, "StationName")
            pad  = _u(ev, "LandingPad")
            msg  = f"Docking request granted. Proceed to pad {pad}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Nav, f"Docking at {stn} (Pad {pad}).")

        case "DockingDenied":
            reason = _s(ev, "Reason")
            msg    = f"Docking request denied. Reason: {reason}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Warn, msg)

        case "DockingCancelled" | "DockingTimeout":
            _speak(tts_q, "Docking aborted.", False)
            return LogEvent.new(EventCategory.Nav, "Docking aborted.")

        case "StartJump":
            j_type = _s(ev, "JumpType")
            dest   = _s(ev, "StarSystem")
            if j_type == "Hyperspace":
                msg = f"Engaging hyperspace."
                _speak(tts_q, msg, False)
                return LogEvent.new(EventCategory.Nav, f"Jumping to {dest}.")
            else:
                _speak(tts_q, "Entering supercruise.", False)
                return None

        case "FSSAllBodiesFound":
            system = _s(ev, "SystemName")
            msg    = f"System scan complete. All signals accounted for in {system}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Explore, f"System scan complete: {system}")

        case "Scanned":
            scan_type = _s(ev, "ScanType")
            msg = f"Warning: {scan_type} scan detected!"
            _speak(tts_q, msg, True)
            return LogEvent.new(EventCategory.Warn, msg)

        case "HeatWarning" | "HeatDamage":
            _speak(tts_q, "Warning: Heat critical!", True)
            return LogEvent.new(EventCategory.Warn, "Heat critical!")

        case "HyperdictInterdict":
            msg = "Thargoid interdiction! Hyperdrive interrupted!"
            _speak(tts_q, msg, True)
            return LogEvent.new(EventCategory.Warn, msg)

        case "EjectCargo":
            cargo = _loc(ev, "Type")
            msg   = f"Cargo ejected: {cargo}."
            _speak(tts_q, msg, False)
            return LogEvent.new(EventCategory.Status, msg)

        case _:
            return None


# ── BGS faction parsing ────────────────────────────────────────────────────────

def _parse_factions(ev: dict, state: AppState) -> None:
    faction_info = ev.get("SystemFaction") or {}
    state.controlling_faction = faction_info.get("Name", "") if isinstance(faction_info, dict) else ""
    state.controlling_state   = faction_info.get("FactionState", "") if isinstance(faction_info, dict) else ""

    state.factions.clear()
    factions_raw = ev.get("Factions")
    if isinstance(factions_raw, list):
        factions = []
        for f in factions_raw:
            if not isinstance(f, dict):
                continue
            name   = f.get("Name", "")
            inf    = f.get("Influence", 0.0)
            fstate = f.get("FactionState", "None")
            if name:
                factions.append((name, fstate, float(inf)))
        factions.sort(key=lambda x: x[2], reverse=True)
        state.factions = factions
