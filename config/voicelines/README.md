# NOVA Voicelines — User Customisation

Place files named `en.toml`, `de.toml`, etc. here to customise
built-in voicelines.  Only the events you define are affected;
everything else uses the built-in defaults.

## Format

    [EventKey]
    add = [
        "Extra variant one.",
        "Extra variant two.",
    ]

    [AnotherEvent]
    replace = [
        "Only this line is used now.",
    ]

## Rules

- `add`     — appends your lines to the built-in pool (more random variety).
- `replace` — replaces the built-in lines entirely for this event.
- `replace = []` — silences the event completely.
- Keys absent from your file use the built-in default.

## Finding built-in defaults

The current default files are copied to the `default/` subfolder here
on every NOVA launch — use them as a reference for available keys and formats.
Do **not** edit the files in `default/` directly; they are overwritten each launch.

## Template Engine

### Includes

Define a reusable fragment (key must start with `_`) in your user file:

    [_ship_status]
    add = ["{ship_name} — hull {hull}, fuel {fuel}."]

Use `{include:_ship_status}` or shorthand `{_ship_status}` in any line.
Hyphens in key names require the explicit form: `{include:_my-key}`.

### Conditionals

Inline `WHEN condition THEN "text";` blocks in any line:

    [Scan_Notable]
    add = ['Scanned {body_short}. WHEN {value_raw} > 500000 THEN "Worth {value}.";']

Condition true → 'text' included. False → replaced with ''.

Supported: `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`
