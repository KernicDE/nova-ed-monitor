# NOVA Personality — User Customisation

Create a file named `default.toml` here (or `<name>.toml` and set
`personality_name = <name>` in config.toml) to customise how NOVA's
AI-generated voice lines sound. Only used when `voice_engine` is set
to `kimi` or `claude` — the static voiceline system ignores this file.

## Fields

    name         = "NOVA"
    tone         = "Short free-text description of overall tone."
    traits       = ["trait one", "trait two"]
    speech_style = "How lines should be phrased for TTS."
    style_notes  = "Any additional guidance for the AI generator."

Fields absent from your file fall back to the built-in default.

## Finding the built-in default

The current default file is copied to the `default/` subfolder here
on every NOVA launch — use it as a reference.
Do **not** edit files in `default/` directly; they are overwritten each launch.
