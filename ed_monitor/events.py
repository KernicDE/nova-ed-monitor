from __future__ import annotations

import queue
import re
import threading
import time
from typing import Optional

from .state import AppState, BioScan, BodyInfo, EngineerInfo, EventCategory, LogEvent, MissionInfo
from .tts import TtsMsg
from . import voicelines as _vl


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
    return f"{n:,} Cr"


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
    "Bacterium Cerbrus":        1_689_800,
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
    # Fonticulua
    "Fonticulua Campestris":    1_000_600,
    "Fonticulua Digitos":       1_804_900,
    "Fonticulua Fluctus":      20_000_200,
    "Fonticulua Lapida":        3_111_600,
    "Fonticulua Segmentatus":  19_010_800,
    "Fonticulua Upsilon":       5_727_600,
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

# Min/max value range per genus (first word of genus localised name, lowercase)
_BIO_GENUS_VALUE_RANGE: dict[str, tuple[int, int]] = {
    "aleoida":    (3_385_200,  12_934_900),
    "bacterium":  (1_000_600,   8_418_000),
    "cactoida":   (2_483_600,  16_202_800),
    "clypeus":    (8_418_000,  16_202_800),
    "concha":     (2_352_400,  19_010_800),
    "electricae": (6_284_600,   6_284_600),
    "fonticulua": (1_000_600,  20_000_200),
    "frutexa":    (1_632_400,  10_326_000),
    "fumerola":   (6_284_600,  16_202_800),
    "fungoida":   (1_000_600,   3_703_200),
    "osseus":     (1_483_000,  12_934_900),
    "recepta":    (12_934_900, 16_202_800),
    "stratum":    (1_362_000,  19_010_800),
    "tubus":      (2_415_500,  11_873_200),
    "tussock":    (1_000_600,  19_010_800),
}


def _bio_value_lookup(species_loc: str) -> int:
    """Return species value, tolerating case/whitespace mismatches and internal IDs."""
    v = _BIO_SPECIES_VALUES.get(species_loc, 0)
    if v == 0:
        v = _BIO_SPECIES_VALUES_LC.get(species_loc.strip().lower(), 0)
    return v


def predict_bio_genera(planet_class: str, atmosphere: str, surface_temp: float,
                       surface_gravity: float, volcanism: str,
                       primary_star_type: str = "") -> list[str]:
    """Predict possible biological genera from planet FSS conditions.

    Returns deduplicated list of genus names (title-case, matching _BIO_GENUS_VALUE_RANGE keys).
    Only makes predictions for landable bodies with atmospheres; returns [] if conditions unknown.
    """
    if not planet_class and not atmosphere:
        return []

    atm = (atmosphere or "").lower()
    pc  = (planet_class or "").lower()
    g   = surface_gravity / 9.80665 if surface_gravity > 0 else 999.0
    t   = surface_temp
    vol = (volcanism or "").lower()

    pst = (primary_star_type or "").upper()
    # Electricae pluma requires type A (main sequence) or hotter
    _a_or_hotter = pst in ("O", "B", "A") or pst.startswith(("O", "B", "A"))

    predicted: list[str] = []

    # ── Volcanism-dependent (Fumerola) ─────────────────────────────────────────
    if vol and "no volcanism" not in vol and g < 0.27:
        predicted.append("Fumerola")

    # ── Helium ────────────────────────────────────────────────────────────────
    if "helium" in atm:
        predicted.append("Bacterium")

    # ── Neon / Neon-rich ──────────────────────────────────────────────────────
    if "neon" in atm:
        predicted.append("Bacterium")
        predicted.append("Fonticulua")
        if _a_or_hotter:
            predicted.append("Electricae")

    # ── Argon / Argon-rich ────────────────────────────────────────────────────
    if "argon" in atm:
        predicted.append("Bacterium")
        if "icy" in pc or "rocky ice" in pc:
            predicted.append("Fonticulua")
        if "rocky" in pc and "icy" not in pc:
            predicted.append("Fungoida")
            predicted.append("Osseus")
            predicted.append("Tussock")
        if _a_or_hotter:
            predicted.append("Electricae")

    # ── Methane / Methane-rich ────────────────────────────────────────────────
    if "methane" in atm:
        predicted.append("Bacterium")
        predicted.append("Fungoida")
        predicted.append("Osseus")
        if "rocky" in pc and "icy" not in pc:
            predicted.append("Tussock")
        if "icy" in pc or "rocky ice" in pc:
            predicted.append("Fonticulua")

    # ── Nitrogen ──────────────────────────────────────────────────────────────
    if "nitrogen" in atm and "sulphur" not in atm and "sulfur" not in atm:
        predicted.append("Bacterium")
        predicted.append("Concha")
        if "icy" in pc or "rocky ice" in pc:
            predicted.append("Fonticulua")

    # ── Oxygen ────────────────────────────────────────────────────────────────
    if "oxygen" in atm:
        predicted.append("Bacterium")
        if "icy" in pc or "rocky ice" in pc:
            predicted.append("Fonticulua")
        if "high metal content" in pc:
            predicted.append("Stratum")

    # ── Ammonia ───────────────────────────────────────────────────────────────
    if "ammonia" in atm:
        predicted.append("Bacterium")
        predicted.append("Aleoida")
        predicted.append("Cactoida")
        predicted.append("Concha")
        predicted.append("Frutexa")
        predicted.append("Fungoida")
        predicted.append("Osseus")
        predicted.append("Tussock")
        if g < 0.15:
            predicted.append("Tubus")
        if t > 165:
            predicted.append("Stratum")

    # ── Carbon dioxide / CO2-rich ─────────────────────────────────────────────
    if "carbon dioxide" in atm:
        predicted.append("Bacterium")
        predicted.append("Concha")
        predicted.append("Frutexa")
        predicted.append("Fungoida")
        predicted.append("Osseus")
        predicted.append("Tussock")
        if t > 190:
            predicted.append("Clypeus")
        if g < 0.15:
            predicted.append("Tubus")
        if t > 165:
            predicted.append("Stratum")
        if "high metal content" in pc:
            predicted.append("Aleoida")
            predicted.append("Cactoida")

    # ── Water / Water-rich ────────────────────────────────────────────────────
    if "water" in atm and "sulphur" not in atm and "sulfur" not in atm:
        predicted.append("Bacterium")
        predicted.append("Cactoida")
        predicted.append("Clypeus")
        predicted.append("Concha")
        predicted.append("Fungoida")
        predicted.append("Osseus")
        if "rocky" in pc and "icy" not in pc:
            predicted.append("Frutexa")
            predicted.append("Tussock")
        if t > 165:
            predicted.append("Stratum")
        if "icy" in pc or "rocky ice" in pc:
            predicted.append("Fonticulua")

    # ── Sulphur dioxide ───────────────────────────────────────────────────────
    if "sulphur dioxide" in atm or "sulfur dioxide" in atm:
        predicted.append("Bacterium")
        predicted.append("Recepta")
        if "rocky" in pc and "icy" not in pc:
            predicted.append("Frutexa")
            predicted.append("Tussock")
            predicted.append("Stratum")
        if ("icy" in pc or "rocky ice" in pc) and t > 165:
            predicted.append("Stratum")

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for genus in predicted:
        if genus not in seen:
            seen.add(genus)
            result.append(genus)
    return result


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

_LANG_ON: dict[str, str] = {
    "en": "on",
    "de": "auf",
    "fr": "sur",
    "it": "su",
    "es": "en",
    "pt": "no",
    "ru": "на",
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
    "esto", "eso", "esa", "ellos", "ella", "nosotros", "prueba",
    "es", "una", "también", "todo", "muy", "bien",
})
_PT_WORDS = frozenset({
    "obrigado", "obrigada", "sim", "não", "para", "como", "uma",
    "com", "por", "mas", "você", "olá", "oi", "bom", "boa",
    "tudo", "bem", "aqui", "isso",
})


_TTS_LANG:  str = "en"
_CHAT_LANG: str = ""   # fallback for chat TTS; empty = rely on auto-detection only


def set_voices(voices: dict[str, str]) -> None:
    """Override default TTS voices from config."""
    _LANG_VOICES.update(voices)


def set_tts_lang(lang: str) -> None:
    """Set NOVA's own voiceover language (used for voiceline lookup and voice selection)."""
    global _TTS_LANG
    _TTS_LANG = lang


def set_chat_lang(lang: str) -> None:
    """Set fallback language for chat TTS when auto-detection returns English."""
    global _CHAT_LANG
    _CHAT_LANG = lang


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

    # Score by word list matches — split on non-word chars so contractions
    # like "c'est" yield both "c" and "est" rather than collapsing to "cest"
    words = frozenset(w for w in re.split(r"[^\w]+", text.lower()) if w)
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


def _speak(tts_q: queue.Queue, text: str, priority: bool, cacheable: bool = True) -> None:
    # Use configured language voice; None means TTS worker uses its default (en)
    voice = _LANG_VOICES.get(_TTS_LANG) if _TTS_LANG != "en" else None
    try:
        tts_q.put_nowait(TtsMsg(
            text=_phonetic_sub(text), priority=priority, voice=voice, cacheable=cacheable,
        ))
    except Exception:
        pass


def _say(
    tts_q: queue.Queue, key: str, priority: bool, fallback: str = "",
    *, cacheable: bool = True, **kwargs,
) -> None:
    """Pick a voiceline variant and speak it; falls back to *fallback* string."""
    text = _vl.pick(key, lang=_TTS_LANG, **kwargs) or fallback
    if text:
        _speak(tts_q, text, priority, cacheable=cacheable)


def _speak_chat(tts_q: queue.Queue, user: str, msg: str, source: str = "") -> None:
    """Speak chat text with language detection. source='Twitch' adds Twitch prefix."""
    try:
        lang = _detect_lang(msg)
        # If detection falls back to English and a chat language is configured, use it
        if lang == "en" and _CHAT_LANG:
            lang = _CHAT_LANG
        voice = _LANG_VOICES.get(lang, _LANG_VOICES["en"])
        verb  = _LANG_VERBS.get(lang, "says")
        on    = _LANG_ON.get(lang, "on")
        if source:
            text = f"{user} {on} {source} {verb}: {msg}"
        else:
            text = f"{user} {verb}: {msg}"
        # Chat is unique per message — never cache
        tts_q.put_nowait(TtsMsg(
            text=_phonetic_sub(text), priority=False, voice=voice, cacheable=False,
        ))
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


# ── Jumponium material sets ───────────────────────────────────────────────────
_JUMP_BASIC    = {"sulphur", "carbon", "phosphorus"}
_JUMP_STANDARD = _JUMP_BASIC    | {"manganese", "arsenic"}
_JUMP_PREMIUM  = _JUMP_STANDARD | {"niobium", "yttrium", "polonium"}

def _jumponium_tier(materials: dict) -> str:
    """Return 'Premium', 'Standard', 'Basic' or '' for a body's material set."""
    mats = {k.lower() for k in materials}
    if _JUMP_PREMIUM.issubset(mats):  return "Premium"
    if _JUMP_STANDARD.issubset(mats): return "Standard"
    if _JUMP_BASIC.issubset(mats):    return "Basic"
    return ""


# ── BGS activity helpers ──────────────────────────────────────────────────────
def _bgs_tick(state: AppState) -> None:
    """Reset BGS log if the UTC date has rolled over (approximate tick boundary)."""
    from datetime import date as _date, timezone as _tz
    today = _date.today().isoformat()
    if state.bgs_log_date != today:
        state.bgs_log      = {}
        state.bgs_log_date = today


def _bgs_add(state: AppState, faction: str, activity: str, count: int = 1) -> None:
    """Record BGS activity for the current system's faction."""
    if not faction or not state.system:
        return
    _bgs_tick(state)
    sys_log = state.bgs_log.setdefault(state.system, {})
    fac_log = sys_log.setdefault(faction, {})
    fac_log[activity] = fac_log.get(activity, 0) + count


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
    if "fonticulus" in g: return 500.0
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

def handle(ev: dict, state: AppState, tts_q: queue.Queue, live: bool = True) -> Optional[LogEvent]:
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
            state.fuel       = fuel
            if dist > 0.0:
                state.jump_range_last = dist  # actual laden range for this jump
            state.fuel_announced = False
            state.discovery_announced = False
            state.hull       = _f(ev, "Health") if "Health" in ev else state.hull
            state.lat        = None
            state.lon        = None
            state.station    = ""
            state.clear_bodies()
            state.bio_scans.clear()
            state.nearest_body        = ""
            state.approach_body       = ""
            state.first_footfall_body    = ""
            state.first_footfall_body_id = -1
            state.first_footfall_bodies.clear()
            state.orbital_cruise         = False
            state.docked_pad          = 0
            state.docked_station_name = ""
            state.docked_station_type = ""
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
                        # Update route_next to reflect the new next waypoint
                        next_entry = state.route_list[1]
                        state.route_next           = next_entry.get("StarSystem", "")
                        state.route_next_star      = next_entry.get("StarClass", "")
                        state.route_next_scoopable = is_scoopable(state.route_next_star)
                        # Re-calculate distance to the now-become-first jump
                        p1 = state.route_list[0].get("StarPos")
                        p2 = state.route_list[1].get("StarPos")
                        if isinstance(p1, list) and isinstance(p2, list):
                            state.route_next_dist = ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)**0.5
                        else:
                            state.route_next_dist = 0.0
                    else:
                        # Last hop: arrived at destination
                        state.route_next           = ""
                        state.route_next_star      = ""
                        state.route_next_scoopable = False
                        state.route_next_dist      = 0.0

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
            # Build optional suffix parts for voiceline templates
            dist_ly_str = _tts_ly(dist)
            tts_suffix = ""
            if star_class:
                scoop_txt = "scoopable" if scoopable else "not scoopable"
                tts_suffix += f" Star {star_class}, {scoop_txt}."
            if hops > 0:
                hops_word = "jump" if hops == 1 else "jumps"
                tts_suffix += f" {hops} {hops_word} remaining."
            if pop > 0:
                tts_suffix += f" Pop: {_fmt_pop(pop)}."
            if live:
                state.last_jump_at = time.time()
            _say(tts_q, "FSDJump", False,
                 fallback=f"Arrived in {system}. Jump {dist_ly_str}.{tts_suffix}",
                 cacheable=False,
                 system=system, dist_ly=dist_ly_str, suffix=tts_suffix)
            return LogEvent.new(EventCategory.Nav, msg)

        case "Location":
            state.client_online = True
            state.client_shutdown_pending = False
            state.system     = _s(ev, "StarSystem")
            state.population = _u(ev, "Population")
            state.economy    = _strip_economy(_loc(ev, "SystemEconomy"))
            state.security   = _strip_economy(_loc(ev, "SystemSecurity"))
            state.government = _loc(ev, "SystemGovernment")
            state.allegiance = _s(ev, "SystemAllegiance")
            state.hull       = _f(ev, "Health") if "Health" in ev else state.hull
            star_pos = ev.get("StarPos")
            if isinstance(star_pos, list) and len(star_pos) == 3:
                state.star_pos = tuple(star_pos)
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

            hops_word = "jump" if hops == 1 else "jumps"
            msg  = f"Route set. Destination: {dest}. {hops} {hops_word} ({tdist:.1f} ly)."
            _say(tts_q, "NavRoute", False,
                 fallback=msg, cacheable=False,
                 dest=dest, hops=hops, hops_word=hops_word, dist_ly=f"{tdist:.1f} light years")
            return LogEvent.new(EventCategory.Nav, msg)

        case "NavRouteClear":
            state.route_destination    = ""
            state.route_hops           = 0
            state.route_next           = ""
            state.route_next_star      = ""
            state.route_next_scoopable = False
            state.route_list           = []
            state.route_list_edsm      = {}
            state.route_bodies_edsm    = {}
            _say(tts_q, "NavRouteClear", False, fallback="Route cleared.")
            return LogEvent.new(EventCategory.Nav, "Route cleared.")

        case "SupercruiseEntry":
            state.approach_body = ""
            state.high_g_extreme = False
            state.hull = _f(ev, "Health") if "Health" in ev else state.hull
            _say(tts_q, "SupercruiseEntry", False, fallback="Supercruise engaged.")
            return LogEvent.new(EventCategory.Nav, "Supercruise engaged.")

        case "SupercruiseExit":
            body = _s(ev, "Body")
            body_short = _short_body(body, state.system)
            msg  = f"Supercruise disengaged near {body_short}." if body else "Supercruise disengaged."
            if body:
                _say(tts_q, "SupercruiseExit", False,
                     fallback=msg, cacheable=False, body=body_short)
            else:
                _say(tts_q, "SupercruiseExit_nobdy", False, fallback=msg)
            return LogEvent.new(EventCategory.Nav, msg)

        case "ApproachBody":
            body_name = _s(ev, "Body")
            state.approach_body = body_name
            # High-G warning
            idx = state._bodies_by_name.get(body_name, -1)
            if 0 <= idx < len(state.bodies):
                sg = state.bodies[idx].surface_gravity
                if sg > 0.0:
                    g = sg / 9.80665
                    if g >= 3.0:
                        state.high_g_extreme = True
                        g_str = f"{g:.1f} G"
                        _say(tts_q, "HighGExtreme", True,
                             fallback=f"Extreme gravity warning: {g_str}!", g=g_str)
                        # Schedule 2 repeat warnings at 10 s and 20 s
                        for delay in (10, 20):
                            def _repeat(bname=body_name, gs=g_str):
                                if state.approach_body == bname and not state.landed and not state.in_srv:
                                    _say(tts_q, "HighGExtreme", True,
                                         fallback=f"Extreme gravity warning: {gs}!", g=gs)
                            threading.Timer(delay, _repeat).start()
                        return LogEvent.new(EventCategory.Warn,
                                            f"Extreme gravity: {g:.1f} G — {body_name}.")
                    elif g >= 1.5:
                        g_str = f"{g:.1f} G"
                        _say(tts_q, "HighGWarning", True,
                             fallback=f"High gravity: {g_str}.", g=g_str)
                        return LogEvent.new(EventCategory.Warn,
                                            f"High gravity: {g:.1f} G — {body_name}.")
            return None

        case "LeaveBody":
            state.approach_body = ""
            state.high_g_extreme = False
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
            _say(tts_q, "Docked", True, fallback=msg, cacheable=False, station=station)
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
            state.docked_pad          = 0
            state.docked_station_name = ""
            state.docked_station_type = ""
            msg = f"Undocked from {station}." if station else "Undocked."
            if station:
                _say(tts_q, "Undocked", False, fallback=msg, cacheable=False, station=station)
            else:
                _say(tts_q, "Undocked_nostation", False, fallback=msg)
            return LogEvent.new(EventCategory.Nav, msg)

        case "Touchdown":
            lat            = _f(ev, "Latitude")
            lon            = _f(ev, "Longitude")
            body           = _s(ev, "Body") or _s(ev, "BodyName")
            body_td_id     = _u(ev, "BodyID")
            first_footfall = _b(ev, "FirstFootfall")
            state.lat    = lat
            state.lon    = lon
            state.landed = True
            # Infer first footfall from first discovery when journal flag is absent.
            # Use case-insensitive + stripped comparison to handle barycentre body names.
            if not first_footfall and (body or body_td_id > 0):
                body_lower = body.strip().lower() if body else ""
                for b in state.bodies:
                    id_match   = body_td_id > 0 and b.body_id == body_td_id
                    name_match = bool(body_lower and b.name.strip().lower() == body_lower)
                    if (id_match or name_match) and b.first_discovered:
                        first_footfall = True
                        break
            if first_footfall and (body or body_td_id > 0):
                if body:
                    state.first_footfall_body = body
                if body_td_id > 0:
                    state.first_footfall_body_id = body_td_id
                # Mark any bio scans already recorded on this body
                for sc in state.bio_scans:
                    if (body and sc.body == body) or (body_td_id > 0 and sc.body and
                            state._bodies_by_name.get(sc.body, -1) >= 0 and
                            state.bodies[state._bodies_by_name[sc.body]].body_id == body_td_id):
                        sc.first_footfall = True
                # Don't announce here — wait for Disembark (player actually stepping out)
            msg = f"Touchdown at {lat:.2f}, {lon:.2f}."
            _say(tts_q, "Touchdown", False, fallback="Touchdown.")
            return LogEvent.new(EventCategory.Nav, msg)

        case "Liftoff":
            state.landed = False
            _say(tts_q, "Liftoff", False, fallback="Liftoff.")
            return LogEvent.new(EventCategory.Nav, "Liftoff.")

        case "Disembark":
            # Odyssey: player leaves ship/SRV on foot.
            # Handle FirstFootfall — announce here (not on Touchdown) so it fires
            # exactly when the player steps onto the surface.
            # Skip first-footfall detection when disembarking at a station/carrier.
            if _b(ev, "OnStation") or _b(ev, "SRV"):
                return None

            first_footfall = _b(ev, "FirstFootfall")
            body_dis       = _s(ev, "Body") or _s(ev, "BodyName")
            body_dis_id    = _u(ev, "BodyID")
            body_dis_lower = body_dis.strip().lower() if body_dis else ""

            # Inherit first footfall flag set by Touchdown for this body.
            # Use case-insensitive match to handle barycentre naming edge cases.
            if not first_footfall and (body_dis or body_dis_id > 0):
                id_match   = body_dis_id > 0 and state.first_footfall_body_id == body_dis_id
                name_match = bool(body_dis_lower and
                                  state.first_footfall_body.strip().lower() == body_dis_lower)
                if id_match or name_match:
                    first_footfall = True

            # Infer first footfall from first discovery when journal flag is absent
            if not first_footfall and (body_dis or body_dis_id > 0):
                _dis_b = None
                if body_dis_id > 0:
                    _di2 = state._bodies_by_id.get(body_dis_id, -1)
                    _dis_b = state.bodies[_di2] if 0 <= _di2 < len(state.bodies) else None
                if _dis_b is None and body_dis:
                    # Case-insensitive fallback
                    for _b_entry in state.bodies:
                        if _b_entry.name.strip().lower() == body_dis_lower:
                            _dis_b = _b_entry
                            break
                if _dis_b is not None and _dis_b.first_discovered:
                    first_footfall = True

            # Final fallback: Touchdown already flagged this body as first footfall
            # but Disembark journal entry omitted FirstFootfall or body fields.
            if not first_footfall and state.first_footfall_body:
                if not body_dis and not body_dis_id:
                    # No body info in Disembark — use whatever Touchdown set
                    body_dis    = state.first_footfall_body
                    body_dis_id = state.first_footfall_body_id
                    first_footfall = True
            if first_footfall:
                if body_dis:
                    state.first_footfall_body = body_dis
                if body_dis_id > 0:
                    state.first_footfall_body_id = body_dis_id
                for sc in state.bio_scans:
                    if body_dis and sc.body == body_dis:
                        sc.first_footfall = True
                # Only announce once per body per system visit
                key = body_dis or state.first_footfall_body
                already_spoke = bool(key and key in state.first_footfall_bodies) or \
                                (not body_dis and body_dis_id > 0 and
                                 any(b == state.first_footfall_body
                                     for b in state.first_footfall_bodies))
                if not already_spoke:
                    if key and live:
                        # Only track announced bodies in live mode — backlog replay
                        # must not poison the set and block future live TTS fires
                        state.first_footfall_bodies.add(key)
                    if live:
                        _say(tts_q, "FirstFootfall", True, fallback="First footfall on this world!")
                    return LogEvent.new(EventCategory.Explore, f"FIRST FOOTFALL! {body_dis or 'Unknown'}.")
            return None

        # ── Combat ───────────────────────────────────────────────────────────

        case "UnderAttack":
            target = _s(ev, "Target")
            msg    = f"Warning! Under attack! Target: {target}." if target else "Warning! Under attack!"
            if target:
                _say(tts_q, "UnderAttack_target", True, fallback=msg, target=target)
            else:
                _say(tts_q, "UnderAttack", True, fallback=msg)
            return LogEvent.new(EventCategory.Warn, msg)

        case "ShieldState":
            up = ev.get("ShieldsUp")
            up = bool(up) if up is not None else True
            state.shields_up = up
            if not up:
                _say(tts_q, "ShieldDown", True, fallback="Warning! Shields offline!")
                return LogEvent.new(EventCategory.Warn, "Shields offline!")
            else:
                _say(tts_q, "ShieldUp", False, fallback="Shields restored.")
                return LogEvent.new(EventCategory.Combat, "Shields restored.")

        case "HullDamage":
            health     = _f(ev, "Health")
            state.hull = health
            pct        = round(health * 100.0)
            if pct <= 50.0:
                msg = f"Critical! Hull at {int(pct)}%!"
                _say(tts_q, "HullDamage_Critical", True,
                     fallback=f"Critical! Hull at {int(pct)} percent!", pct=int(pct))
                return LogEvent.new(EventCategory.Warn, msg)
            elif pct <= 75.0:
                msg = f"Hull damage: {int(pct)}%."
                _say(tts_q, "HullDamage_Warning", False,
                     fallback=f"Hull damage: {int(pct)} percent.", pct=int(pct))
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
            _say(tts_q, "Died", True, fallback=msg, msg=msg)
            return LogEvent.new(EventCategory.Warn, msg)

        case "Bounty":
            reward = (ev.get("TotalReward") or ev.get("Reward") or 0)
            if isinstance(reward, float): reward = int(reward)
            victim        = _s(ev, "Target")
            victim_faction = _s(ev, "VictimFaction")
            suffix = f" Target: {victim}" if victim else ""
            msg    = f"Bounty: {_fmt_credits(reward)}{suffix}."
            reward_str = _tts_cr(reward)
            # Update massacre kill counters for matching factions
            if victim_faction:
                for mid_k, mk in state.massacre_kills.items():
                    if mk["faction"] == victim_faction:
                        mk["done"] = min(mk["done"] + 1, mk["needed"])
                _bgs_add(state, victim_faction, "bounty")
            if victim:
                _say(tts_q, "Bounty_target", False,
                     fallback=msg, reward=reward_str, victim=victim)
            else:
                _say(tts_q, "Bounty", False, fallback=msg, reward=reward_str)
            return LogEvent.new(EventCategory.Combat, msg)

        case "FactionKillBond":
            reward         = _u(ev, "Reward")
            victim_faction = _s(ev, "VictimFaction")
            msg    = f"Combat bond: {_fmt_credits(reward)}."
            if victim_faction:
                for mid_k, mk in state.massacre_kills.items():
                    if mk["faction"] == victim_faction:
                        mk["done"] = min(mk["done"] + 1, mk["needed"])
                _bgs_add(state, victim_faction, "combat bond")
            _say(tts_q, "FactionKillBond", False, fallback=msg, reward=_tts_cr(reward))
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
                # Parse surface materials from Scan event
                raw_mats = ev.get("Materials")
                body_materials: dict = {}
                if isinstance(raw_mats, list):
                    for m in raw_mats:
                        if not isinstance(m, dict):
                            continue
                        mname = (m.get("Name") or "").lower()
                        mpct  = float(m.get("Percent") or 0.0)
                        if mname:
                            body_materials[mname] = mpct

                # Detect unusual body properties
                orbital_period = _f(ev, "OrbitalPeriod")
                eccentricity   = _f(ev, "Eccentricity")
                unusual_flags  = []
                if landable and not is_star and radius > 0 and radius < 500_000:
                    km = int(radius / 1000)
                    unusual_flags.append(f"Tiny<{km}km")
                if not is_star and eccentricity > 0.8:
                    unusual_flags.append(f"Ecc {eccentricity:.2f}")
                if not is_star and 0 < orbital_period < 7_200:
                    mins = int(orbital_period / 60)
                    unusual_flags.append(f"Orb {mins}m")
                unusual_body = " · ".join(unusual_flags)

                state.upsert_body(BodyInfo(
                    name=body_name, body_id=body_id, level=level,
                    planet_class=planet_class, star_type=star_type, atmosphere=atmosphere,
                    terraform=terraformable, landable=landable,
                    bio_signals=0, geo_signals=0, bio_genuses=[],
                    dist_ls=dist_ls, value=value,
                    first_discovered=not _b(ev, "WasDiscovered"),
                    first_mapped=not _b(ev, "WasMapped"),
                    first_footfall="WasFootfalled" in ev and not ev["WasFootfalled"],
                    mapped=False, fss_scanned=scan_type == "Detailed",
                    radius=radius,
                    semi_major_axis=_f(ev, "SemiMajorAxis"),
                    orbital_period=orbital_period,
                    mean_anomaly=_f(ev, "MeanAnomaly"),
                    eccentricity=eccentricity,
                    orbital_inclination=_f(ev, "OrbitalInclination"),
                    surface_gravity=_f(ev, "SurfaceGravity"),
                    surface_temp=_f(ev, "SurfaceTemperature"),
                    volcanism=_s(ev, "Volcanism"),
                    materials=body_materials,
                    unusual_body=unusual_body,
                ))

            if scan_type not in ("Detailed", "AutoScan"):
                return None

            if scan_type == "AutoScan" and is_star and not _b(ev, "WasDiscovered"):
                if not state.discovery_announced:
                    state.discovery_announced = True
                    _say(tts_q, "Scan_Undiscovered", False, fallback="Undiscovered system.")

            if just_dss_scanned:
                return None

            _bidx      = state._bodies_by_name.get(body_name, -1)
            _body_info = state.bodies[_bidx] if 0 <= _bidx < len(state.bodies) else None
            bio_count  = _body_info.bio_signals if _body_info else 0
            geo_count  = _body_info.geo_signals if _body_info else 0

            # Run / refresh bio genus prediction now that we have planet details.
            # FSSBodySignals may have arrived before the Scan event (live play), so
            # prediction might not have been computed yet.  Also re-run if the body
            # gained a planet_class it lacked when FSSBodySignals first fired.
            if _body_info and bio_count > 0 and not _body_info.bio_genuses and planet_class:
                _pst2 = ""
                for _sb2 in state.bodies:
                    if _sb2.star_type and _sb2.level == 0:
                        _pst2 = _sb2.star_type
                        break
                _body_info.bio_genuses_predicted = predict_bio_genera(
                    planet_class, atmosphere,
                    _f(ev, "SurfaceTemperature"), _f(ev, "SurfaceGravity"),
                    _s(ev, "Volcanism"), _pst2,
                )

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
                _say(tts_q, "Scan_Notable", valuable or star_type in ("N", "H"),
                     fallback=msg, body_short=short, detail=detail)
                return LogEvent.new(EventCategory.Explore, msg)
            elif scan_type == "Detailed":
                parts = []
                if planet_class: parts.append(planet_class)
                if landable:     parts.append("Landable.")
                parts.extend(sig_parts)
                detail = " ".join(parts)
                msg    = f"Scan: {short}. {detail}"
                _say(tts_q, "Scan_Detailed", False,
                     fallback=msg, body_short=short, detail=detail)
                return LogEvent.new(EventCategory.Explore, msg)
            else:
                return None

        case "SAAScanComplete":
            body_name         = _s(ev, "BodyName")
            short             = _short_body(body_name, state.system)
            probes_used       = _u(ev, "ProbesUsed")
            efficiency_target = _u(ev, "EfficiencyTarget")
            bio_count = 0
            geo_count = 0
            _bidx2 = state._bodies_by_name.get(body_name, -1)
            if 0 <= _bidx2 < len(state.bodies):
                _bm = state.bodies[_bidx2]
                _bm.mapped = True
                bio_count  = _bm.bio_signals
                geo_count  = _bm.geo_signals
            state.dss_recently_completed.add(body_name)

            sig_parts = []
            if bio_count > 0:
                sig_parts.append(f"{bio_count} bio")
            if geo_count > 0:
                sig_parts.append(f"{geo_count} geo")
            msg = f"Mapped: {short}."
            sig_txt = ""
            eff_txt = ""
            if sig_parts:
                sig_txt = f" Signals: {', '.join(sig_parts)}."
                msg += sig_txt
            if efficiency_target > 0:
                if probes_used <= efficiency_target:
                    eff_txt = " Efficiency target reached."
                else:
                    eff_txt = f" Efficiency target missed: {probes_used} probes, target {efficiency_target}."
                msg += eff_txt
            _say(tts_q, "SAAScanComplete", False,
                 fallback=msg, body_short=short,
                 sig_txt=sig_txt, eff_txt=eff_txt)
            return LogEvent.new(EventCategory.Explore, msg)

        case "FSSDiscoveryScan":
            total = _u(ev, "BodyCount")
            state.fss_body_count = total
            msg   = f"Honk complete. {total} bodies detected."
            _say(tts_q, "FSSDiscoveryScan", False, fallback=msg, total=total)
            return LogEvent.new(EventCategory.Explore, msg)

        case "FSSBodySignals":
            body_name = _s(ev, "BodyName")
            body_id   = _u(ev, "BodyID")
            short     = _short_body(body_name, state.system)

            if body_name not in state._bodies_by_name:
                state.upsert_body(_placeholder_body(body_name, body_id))

            bio_count = 0
            geo_count = 0
            _fss_idx = state._bodies_by_name.get(body_name, -1)
            _fss_b   = state.bodies[_fss_idx] if 0 <= _fss_idx < len(state.bodies) else None
            sigs = ev.get("Signals")
            if isinstance(sigs, list) and _fss_b is not None:
                for sig in sigs:
                    sig_type = _loc(sig, "Type")
                    count    = _u(sig, "Count")
                    if "Biological"   in sig_type: _fss_b.bio_signals = count; bio_count = count
                    elif "Geological" in sig_type: _fss_b.geo_signals = count; geo_count = count
                # Run bio genus prediction if we now have bio signals and no DSS genus data yet
                if bio_count > 0 and not _fss_b.bio_genuses and _fss_b.planet_class:
                    # Find primary star type for this system
                    _pst = ""
                    for _sb in state.bodies:
                        if _sb.star_type and _sb.level == 0:
                            _pst = _sb.star_type
                            break
                    _fss_b.bio_genuses_predicted = predict_bio_genera(
                        _fss_b.planet_class, _fss_b.atmosphere,
                        _fss_b.surface_temp, _fss_b.surface_gravity,
                        _fss_b.volcanism, _pst,
                    )

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
                _say(tts_q, "FSSSignalDiscovered", True, fallback=msg, sig=sig)
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
                _say(tts_q, "CodexEntry", False, fallback=msg, name=name)
            return LogEvent.new(EventCategory.Explore, msg)

        case "SAASignalsFound":
            body_name = _s(ev, "BodyName")
            body_id   = _u(ev, "BodyID")
            signals   = ev.get("Signals") or []
            genuses   = ev.get("Genuses") or []

            if body_name not in state._bodies_by_name:
                state.upsert_body(_placeholder_body(body_name, body_id))

            _saa_idx = state._bodies_by_name.get(body_name, -1)
            _saa_b   = state.bodies[_saa_idx] if 0 <= _saa_idx < len(state.bodies) else None
            if _saa_b is not None:
                for sig in signals:
                    sig_type = _loc(sig, "Type")
                    count    = _u(sig, "Count")
                    if "Biological"   in sig_type: _saa_b.bio_signals = count
                    elif "Geological" in sig_type: _saa_b.geo_signals = count
                genus_names = [n for n in (_loc(g, "Genus") for g in genuses) if n]
                _saa_b.bio_genuses = genus_names
                if genus_names:
                    bvmin = bvmax = 0
                    for g in genus_names:
                        key = g.lower().split()[0] if g else ""
                        lo, hi = _BIO_GENUS_VALUE_RANGE.get(key, (0, 0))
                        bvmin += lo
                        bvmax += hi
                    _saa_b.bio_value_min = bvmin
                    _saa_b.bio_value_max = bvmax
            return None

        case "ScanOrganic":
            scan_type   = _s(ev, "ScanType")
            species     = _s(ev, "Species")
            species_loc = _loc(ev, "Species")
            genus_loc   = _loc(ev, "Genus")
            body_id     = _u(ev, "Body")

            _org_bidx = state._bodies_by_id.get(body_id, -1)
            body_name = (
                state.bodies[_org_bidx].name
                if 0 <= _org_bidx < len(state.bodies)
                else "Unknown"
            )
            if body_name == "Unknown":
                body_name = state.nearest_body or state.system or "Unknown"

            _org_nidx  = state._bodies_by_name.get(body_name, -1)
            _org_b     = state.bodies[_org_nidx] if 0 <= _org_nidx < len(state.bodies) else None
            body_radius = _org_b.radius if _org_b and _org_b.radius > 0 else 3_000_000.0

            match scan_type:
                case "Log":
                    first_disc = _b_absent_true(ev, "WasDiscovered") is False
                    first_logged = _b_absent_true(ev, "WasLogged") is False
                    log_lat, log_lon = state.lat, state.lon
                    from_ship = state.in_main_ship

                    existing_sc = next(
                        (sc for sc in state.bio_scans if sc.species == species and sc.body == body_name),
                        None
                    )
                    if existing_sc is None:
                        base_val = _bio_value_lookup(species_loc)
                        if first_disc or first_logged:
                            base_val *= 5

                        is_first_footfall = (
                            (bool(state.first_footfall_body) and body_name == state.first_footfall_body)
                            or (state.first_footfall_body_id > 0 and body_id == state.first_footfall_body_id)
                        )
                        new_sc = BioScan(
                            species=species, species_localised=species_loc,
                            genus_localised=genus_loc, body=body_name,
                            samples=1, min_dist=genus_min_dist(genus_loc),
                            last_lat=log_lat, last_lon=log_lon,
                            body_radius=body_radius, current_dist=None,
                            value=base_val,
                            alerted=False, complete=False,
                            first_discovered=first_disc or first_logged,
                            first_footfall=is_first_footfall,
                        )
                        if from_ship and log_lat is not None and log_lon is not None:
                            new_sc.comp_lats.append(log_lat)
                            new_sc.comp_lons.append(log_lon)
                        elif not from_ship and log_lat is not None and log_lon is not None:
                            new_sc.sample_lats.append(log_lat)
                            new_sc.sample_lons.append(log_lon)
                        state.bio_scans.append(new_sc)
                    else:
                        # Subsequent COMP scan of same species on same body — save new position
                        if from_ship and log_lat is not None and log_lon is not None:
                            existing_sc.comp_lats.append(log_lat)
                            existing_sc.comp_lons.append(log_lon)
                    tag = " — new species!" if first_logged else ""
                    if first_logged:
                        _say(tts_q, "ScanOrganic_Log_NewSpecies", False,
                             fallback=f"Biological: {species_loc}. New species!", species=species_loc)
                    else:
                        _say(tts_q, "ScanOrganic_Log", False,
                             fallback=f"Biological: {species_loc}.", species=species_loc)
                    return LogEvent.new(EventCategory.Explore, f"Bio{tag}: {species_loc} [{genus_loc}]")

                case "Sample":
                    lat, lon = state.lat, state.lon
                    count = 2
                    for sc in state.bio_scans:
                        if sc.species == species and sc.body == body_name:
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
                        msg = f"Bio sample {count} of 3: {species_loc}."
                        _say(tts_q, "ScanOrganic_Sample", False,
                             fallback=msg, count=count, species=species_loc,
                             remaining=3 - count)
                        return LogEvent.new(EventCategory.Explore, msg)
                    return None

                case "Analyse":
                    value = _u(ev, "Value")
                    matched_sc = None
                    for sc in state.bio_scans:
                        if sc.species == species and sc.body == body_name:
                            sc.samples  = 3
                            if value > 0:
                                sc.value = value   # keep lookup-table value if game gives 0
                            sc.complete = True
                            matched_sc  = sc
                            break
                    # Fallback: if first_footfall wasn't captured on the BioScan at Log time
                    # (e.g. body-name mismatch race), check current state here.
                    if matched_sc and not matched_sc.first_footfall:
                        is_ff_now = (
                            (bool(state.first_footfall_body) and body_name == state.first_footfall_body)
                            or (state.first_footfall_body_id > 0 and body_id == state.first_footfall_body_id)
                        )
                        if is_ff_now:
                            matched_sc.first_footfall = True
                    final_val      = matched_sc.value if matched_sc else value
                    is_ff          = matched_sc.first_footfall if matched_sc else False
                    val_str        = _tts_cr(final_val) if final_val > 0 else "unknown"
                    ff_suffix      = " First footfall bonus applied." if is_ff else ""
                    msg_tts = f"Bio complete: {species_loc}. Value: {val_str}.{ff_suffix}"
                    msg_log = f"Bio complete: {species_loc}. Value: {_fmt_credits(final_val) if final_val > 0 else '?'}.{' ✦FF' if is_ff else ''}"
                    _say(tts_q, "ScanOrganic_Analyse", False,
                         fallback=msg_tts, species=species_loc, val_str=val_str, ff_suffix=ff_suffix)
                    # Bio completion contextual announcement
                    body_done  = sum(1 for s in state.bio_scans if s.body == body_name and s.complete)
                    _anl_idx   = state._bodies_by_name.get(body_name, -1)
                    body_info  = state.bodies[_anl_idx] if 0 <= _anl_idx < len(state.bodies) else None
                    body_total = body_info.bio_signals if body_info else body_done
                    body_left  = body_total - body_done
                    bodies_with_bio = [b for b in state.bodies if b.bio_signals > 0]
                    remaining_by_body = {
                        b.name: b.bio_signals - sum(1 for s in state.bio_scans if s.body == b.name and s.complete)
                        for b in bodies_with_bio
                    }
                    remaining_by_body = {k: v for k, v in remaining_by_body.items() if v > 0}
                    if body_left > 0:
                        bio_word = "bio" if body_left == 1 else "bios"
                        verb     = "is" if body_left == 1 else "are"
                        _say(tts_q, "ScanOrganic_Analyse_BodyLeft", False,
                             fallback=f"There {verb} {body_left} more {bio_word} on this body.",
                             body_left=body_left, bio_word=bio_word, verb=verb)
                    elif remaining_by_body:
                        parts_r  = [f"{v} on {_short_body(k, state.system)}" for k, v in remaining_by_body.items()]
                        parts_str = ", ".join(parts_r)
                        _say(tts_q, "ScanOrganic_Analyse_SystemMore", False,
                             fallback=f"More bio signals: {parts_str}.",
                             parts_str=parts_str)
                    else:
                        _say(tts_q, "ScanOrganic_Analyse_SystemDone", False,
                             fallback="All bio signals in this system are complete.")
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
            # Track massacre missions for kill progress display
            raw_name = _s(ev, "Name")
            if "Massacre" in raw_name and mid:
                kill_count     = _u(ev, "KillCount")
                target_faction = _s(ev, "TargetFaction")
                if kill_count and target_faction:
                    state.massacre_kills[mid] = {
                        "faction": target_faction,
                        "needed":  kill_count,
                        "done":    0,
                    }
            if name:
                _say(tts_q, "MissionAccepted", False,
                     fallback=f"Mission accepted: {name}.",
                     name=name, dest=dest)
            return LogEvent.new(EventCategory.Mission, f"Mission accepted: {name}.")

        case "MissionCompleted":
            mid    = _u(ev, "MissionID")
            reward = _u(ev, "Reward")
            name   = _loc(ev, "LocalisedName") or _s(ev, "Name")
            if reward:
                state.credits += reward
            state.remove_mission(mid)
            state.massacre_kills.pop(mid, None)
            # Parse BGS faction effects
            faction_effects = ev.get("FactionEffects")
            if isinstance(faction_effects, list):
                for fe in faction_effects:
                    if not isinstance(fe, dict):
                        continue
                    faction = fe.get("Faction", "")
                    effects = fe.get("Effects") or []
                    for eff in effects:
                        if not isinstance(eff, dict):
                            continue
                        effect = eff.get("Effect_Localised") or eff.get("Effect", "")
                        if effect:
                            _bgs_add(state, faction, "mission")
                            break  # one log entry per faction per mission
            msg = f"Mission complete: {name}. Reward: {_fmt_credits(reward)}."
            _say(tts_q, "MissionCompleted", False,
                 fallback=f"Mission complete: {name}. Reward: {_tts_cr(reward)}.",
                 name=name, reward=_tts_cr(reward))
            return LogEvent.new(EventCategory.Mission, msg)

        case "MissionFailed":
            mid  = _u(ev, "MissionID")
            name = _loc(ev, "LocalisedName") or _s(ev, "Name")
            state.remove_mission(mid)
            state.massacre_kills.pop(mid, None)
            msg  = f"Mission failed: {name}."
            _say(tts_q, "MissionFailed", False, fallback=msg, name=name)
            return LogEvent.new(EventCategory.Mission, msg)

        case "MissionAbandoned":
            mid = _u(ev, "MissionID")
            state.remove_mission(mid)
            state.massacre_kills.pop(mid, None)
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
            if total:
                state.credits += total
            _bgs_add(state, state.controlling_faction, "trade")
            msg = f"Sold: {count}x {commodity} for {_fmt_credits(total)}."
            if profit > 0:
                msg += f" Profit: {_fmt_credits(profit)}."
            total_str  = _tts_cr(total)
            profit_str = _tts_cr(profit) if profit > 0 else ""
            if profit > 0:
                _say(tts_q, "MarketSell_profit", False,
                     fallback=f"Sold: {count}x {commodity} for {total_str}. Profit: {profit_str}.",
                     count=count, commodity=commodity, total=total_str, profit=profit_str)
            else:
                _say(tts_q, "MarketSell", False,
                     fallback=f"Sold: {count}x {commodity} for {total_str}.",
                     count=count, commodity=commodity, total=total_str)
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
                    rp = float(entry.get("RankProgress", 0))
                    eid = int(entry.get("EngineerID", 0))
                    if n:
                        existing = state.engineers.get(n)
                        if isinstance(existing, EngineerInfo):
                            existing.rank = r
                            existing.rank_progress = rp
                            existing.progress = p
                            existing.engineer_id = eid
                        else:
                            state.engineers[n] = EngineerInfo(
                                name=n, rank=r, rank_progress=rp, progress=p, engineer_id=eid
                            )
                return None
            # Individual event
            engineer = _s(ev, "Engineer")
            progress = _s(ev, "Progress")
            rank     = _u(ev, "Rank")
            rank_progress = _f(ev, "RankProgress")
            eng_id   = _u(ev, "EngineerID")
            if engineer:
                existing = state.engineers.get(engineer)
                if isinstance(existing, EngineerInfo):
                    existing.rank = rank
                    existing.rank_progress = rank_progress
                    existing.progress = progress
                    if eng_id:
                        existing.engineer_id = eng_id
                else:
                    state.engineers[engineer] = EngineerInfo(
                        name=engineer, rank=rank, rank_progress=rank_progress,
                        progress=progress, engineer_id=eng_id,
                    )
            if progress == "Unlocked":
                msg = f"Engineer unlocked: {engineer}!"
                _say(tts_q, "EngineerUnlocked", True, fallback=msg, engineer=engineer)
                return LogEvent.new(EventCategory.Mission, msg)
            elif rank > 0:
                msg = f"Engineer {engineer}: rank {rank}."
                _say(tts_q, "EngineerRank", False, fallback=msg,
                     engineer=engineer, rank=rank)
                return LogEvent.new(EventCategory.Mission, msg)
            return None

        # ── Loadout / Session init ───────────────────────────────────────────

        case "Fileheader":
            return None  # Journal session start marker, no state to update

        case "LoadGame":
            state.client_online = True
            state.client_shutdown_pending = False
            state.commander  = _s(ev, "Commander")
            state.ship_type  = _fmt_ship_type(_s(ev, "Ship"))
            state.ship_name  = _s(ev, "ShipName")
            state.ship_ident = _s(ev, "ShipIdent")
            state.fuel       = _f(ev, "FuelLevel")
            state.fuel_max   = _f(ev, "FuelCapacity")
            # Grab health from login if present
            state.hull       = _f(ev, "HullHealth", 1.0)
            cr = ev.get("Credits")
            if isinstance(cr, (int, float)):
                state.credits = int(cr)
            msg = f"CMDR {state.commander} online."
            _say(tts_q, "LoadGame", False, fallback=msg, commander=state.commander)
            return LogEvent.new(EventCategory.System, msg)

        case "Shutdown":
            if state.client_online:  # Guard: only announce once per session
                _say(tts_q, "Shutdown", False,
                     fallback="Systems powering down. Farewell, Commander.")
            state.client_online = False
            state.client_shutdown_pending = True
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
            # Max jump range for neutron plotter
            mjr = _f(ev, "MaxJumpRange")
            if mjr > 0.0:
                state.jump_range = mjr
            return None

        case "Repair":
            item = _s(ev, "Item")
            if item == "Wear" or "hull" in item.lower():
                state.hull = 1.0
                _say(tts_q, "Repair", False,
                     fallback=f"Repair complete: {item}.", item=item)
                return LogEvent.new(EventCategory.Status, "Hull repaired.")
            return None

        case "RepairAll":
            state.hull = 1.0
            _say(tts_q, "RepairAll", False, fallback="Full repair complete.")
            return LogEvent.new(EventCategory.Status, "Full repair complete.")

        case "Resurrect":
            state.hull       = 1.0
            state.shields_up = True
            _say(tts_q, "Resurrect", False, fallback="Respawned at station.")
            return LogEvent.new(EventCategory.Status, "Respawned at station.")

        # ── Status / Misc ────────────────────────────────────────────────────

        case "FuelScoop":
            total      = _f(ev, "Total")
            state.fuel = total
            is_full    = state.fuel_max > 0.0 and total >= (state.fuel_max - 0.05)
            if is_full and not state.fuel_announced:
                state.fuel_announced = True
                _say(tts_q, "FuelScoop_Full", False, fallback="Fuel tank full.")
                return LogEvent.new(EventCategory.Status, f"Fuel full ({total:.0f}t).")
            return None

        case "Interdicted":
            submitted   = _b(ev, "Submitted")
            interdictor = _s(ev, "Interdictor")
            if submitted:
                msg = f"Interdiction submitted to {interdictor}." if interdictor else "Interdiction submitted."
                if interdictor:
                    _say(tts_q, "Interdicted_Submitted_name", False,
                         fallback=msg, interdictor=interdictor)
                else:
                    _say(tts_q, "Interdicted_Submitted", False, fallback=msg)
            else:
                msg = f"Interdiction escaped from {interdictor}!" if interdictor else "Interdiction escaped!"
                if interdictor:
                    _say(tts_q, "Interdicted_Escaped_name", True,
                         fallback=msg, interdictor=interdictor)
                else:
                    _say(tts_q, "Interdicted_Escaped", True, fallback=msg)
            cat = EventCategory.Combat if submitted else EventCategory.Warn
            return LogEvent.new(cat, msg)

        case "Interdiction":
            success = _b(ev, "Success")
            victim  = _s(ev, "Interdicted")
            if success:
                msg = f"Interdiction successful: {victim}." if victim else "Interdiction successful."
                _say(tts_q, "Interdiction_Success", False,
                     fallback=msg, victim=victim or "target")
            else:
                msg = "Interdiction failed."
                _say(tts_q, "Interdiction_Failed", False, fallback=msg)
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
            state.docked_pad          = pad
            state.docked_station_type = _s(ev, "StationType")
            state.docked_station_name = stn
            msg  = f"Docking request granted. Proceed to pad {pad}."
            _say(tts_q, "DockingGranted", False, fallback=msg, pad=pad)
            return LogEvent.new(EventCategory.Nav, f"Docking at {stn} (Pad {pad}).")

        case "DockingDenied":
            reason = _s(ev, "Reason")
            msg    = f"Docking request denied. Reason: {reason}."
            _say(tts_q, "DockingDenied", False, fallback=msg, reason=reason)
            return LogEvent.new(EventCategory.Warn, msg)

        case "DockingCancelled" | "DockingTimeout":
            _say(tts_q, "DockingCancelled", False, fallback="Docking aborted.")
            return LogEvent.new(EventCategory.Nav, "Docking aborted.")

        case "StartJump":
            j_type = _s(ev, "JumpType")
            dest   = _s(ev, "StarSystem")
            if j_type == "Hyperspace":
                _say(tts_q, "StartJump_Hyperspace", False, fallback="Engaging hyperspace.")
                return LogEvent.new(EventCategory.Nav, f"Jumping to {dest}.")
            else:
                # No TTS here — SupercruiseEntry fires ~2s later and speaks the confirmation.
                # Speaking on StartJump too causes a double callout.
                return None

        case "FSSAllBodiesFound":
            system = _s(ev, "SystemName")
            msg    = f"System scan complete. All signals accounted for in {system}."
            _say(tts_q, "FSSAllBodiesFound", False, fallback=msg, system=system)
            return LogEvent.new(EventCategory.Explore, f"System scan complete: {system}")

        case "Scanned":
            scan_type = _s(ev, "ScanType")
            msg = f"Warning: {scan_type} scan detected!"
            _say(tts_q, "Scanned", True, fallback=msg, scan_type=scan_type)
            return LogEvent.new(EventCategory.Warn, msg)

        case "HeatWarning" | "HeatDamage":
            _say(tts_q, "HeatWarning", True, fallback="Warning: Heat critical!")
            return LogEvent.new(EventCategory.Warn, "Heat critical!")

        case "HyperdictInterdict":
            msg = "Thargoid interdiction! Hyperdrive interrupted!"
            _say(tts_q, "HyperdictInterdict", True, fallback=msg)
            return LogEvent.new(EventCategory.Warn, msg)

        case "EjectCargo":
            cargo = _loc(ev, "Type")
            msg   = f"Cargo ejected: {cargo}."
            _say(tts_q, "EjectCargo", False, fallback=msg, cargo=cargo)
            return LogEvent.new(EventCategory.Status, msg)

        # ── Wealth / inventory ───────────────────────────────────────────────

        case "Statistics":
            bank = ev.get("Bank_Account")
            if isinstance(bank, dict):
                w = bank.get("Current_Wealth")
                if isinstance(w, (int, float)) and w > 0:
                    state.credits = int(w)
            return None

        case "StoredShips":
            ships_here   = ev.get("ShipsHere")   or []
            ships_remote = ev.get("ShipsRemote")  or []
            current_sys  = _s(ev, "StarSystem")
            all_ships = []
            for raw in ships_here:
                if not isinstance(raw, dict):
                    continue
                all_ships.append({
                    "name":    raw.get("Name") or raw.get("Name_Localised") or raw.get("ShipType_Localised") or raw.get("ShipType", ""),
                    "type":    _fmt_ship_type(raw.get("ShipType", "")),
                    "ident":   raw.get("ShipIdent", ""),
                    "system":  current_sys,
                    "station": _s(ev, "StationName"),
                    "here":    True,
                })
            for raw in ships_remote:
                if not isinstance(raw, dict):
                    continue
                all_ships.append({
                    "name":    raw.get("Name") or raw.get("Name_Localised") or raw.get("ShipType_Localised") or raw.get("ShipType", ""),
                    "type":    _fmt_ship_type(raw.get("ShipType", "")),
                    "ident":   raw.get("ShipIdent", ""),
                    "system":  raw.get("StarSystem", ""),
                    "station": raw.get("StationName", ""),
                    "here":    False,
                })
            state.stored_ships = all_ships
            return None

        case "SuitLoadout":
            state.suit_loadout = {
                "suit":    _loc(ev, "SuitName"),
                "suit_id": _u(ev, "SuitID"),
                "modules": ev.get("Modules") or [],
                "weapons": ev.get("Weapons") or [],
            }
            return None

        case "Backpack":
            state.backpack = {
                "items":      ev.get("Items")      or [],
                "components": ev.get("Components") or [],
                "consumables": ev.get("Consumables") or [],
                "data":       ev.get("Data")       or [],
            }
            return None

        case "BackpackChange":
            # Delta event; full refresh on next Backpack event
            return None

        case "MarketBuy":
            cost = _u(ev, "TotalCost")
            if cost and state.credits > 0:
                state.credits = max(0, state.credits - cost)
            return None

        case "SellExplorationData" | "MultiSellExplorationData":
            total = _u(ev, "TotalEarnings") or _u(ev, "BaseValue")
            if total and state.credits >= 0:
                state.credits += total
            _bgs_add(state, state.controlling_faction, "exploration")
            if total:
                _say(tts_q, "SellExplorationData", False,
                     fallback=f"Exploration data sold: {_fmt_credits(total)}.",
                     value=_tts_cr(total))
                return LogEvent.new(EventCategory.Trade,
                                    f"Exploration data sold: {_fmt_credits(total)}.")
            return None

        case "RedeemVoucher":
            voucher_type = _s(ev, "Type")
            if voucher_type in ("Bounty", "CombatBond"):
                factions_raw = ev.get("Factions")
                if isinstance(factions_raw, list):
                    for f in factions_raw:
                        if isinstance(f, dict):
                            faction = f.get("Faction", "")
                            activity = "bounty" if voucher_type == "Bounty" else "combat bond"
                            _bgs_add(state, faction, activity)
            return None

        case "ColonisationConstructionDepot":
            # Fired when approaching a construction site; provides commodity requirement details
            market_id   = _u(ev, "MarketID")
            system_name = _s(ev, "SystemName") or state.system
            if not market_id:
                return None
            resources = ev.get("ResourcesRequired") or []
            commodities: list = []
            if isinstance(resources, list):
                for r in resources:
                    if not isinstance(r, dict):
                        continue
                    name     = _loc(r, "Name") or _s(r, "Name")
                    required = _u(r, "RequiredAmount")
                    provided = _u(r, "ProvidedAmount")
                    if name:
                        commodities.append({"name": name, "required": required, "provided": provided})
            existing = state.colonisation_sites.get(market_id, {})
            state.colonisation_sites[market_id] = {
                "market_id":   market_id,
                "system":      system_name,
                "commodities": commodities or existing.get("commodities", []),
            }
            return None

        case "ColonisationContribution":
            market_id = _u(ev, "MarketID")
            if not market_id:
                return None
            # Update or create site entry with contribution data
            site = state.colonisation_sites.setdefault(market_id, {
                "market_id": market_id,
                "system":    state.system,
                "commodities": [],
            })
            contributions = ev.get("Contributions") or []
            if isinstance(contributions, list):
                # Merge contributed amounts into existing commodities
                for c in contributions:
                    if not isinstance(c, dict):
                        continue
                    cname  = _loc(c, "Name") or _s(c, "Name")
                    ccount = _u(c, "Amount")
                    if not cname:
                        continue
                    found = False
                    for com in site["commodities"]:
                        if com.get("name", "").lower() == cname.lower():
                            com["provided"] = com.get("provided", 0) + ccount
                            found = True
                            break
                    if not found:
                        site["commodities"].append({"name": cname, "required": 0, "provided": ccount})
            _bgs_add(state, state.controlling_faction, "colonisation")
            commodity_count = _u(ev, "TotalCommodities") or sum(
                _u(c, "Amount") for c in contributions if isinstance(c, dict)
            )
            msg = f"Colonisation contribution: {commodity_count} t delivered."
            return LogEvent.new(EventCategory.Mission, msg)

        case "PowerplayMerits":
            state.pp_power          = _s(ev, "Power")
            state.pp_rank           = _u(ev, "Rank")
            state.pp_total_merits   = _u(ev, "TotalMerits")
            state.pp_session_merits = _u(ev, "MeritsGained")
            return None

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
