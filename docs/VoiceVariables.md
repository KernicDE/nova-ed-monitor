# Voiceline Template Variables

Every `{variable}` in a voiceline template is filled at runtime from the current game state. Missing variables render as empty strings (never cause errors). Unknown variable names also silently expand to `""`.

Templates also support [**includes** and **conditionals**](Settings#template-engine) — see the Settings guide for the template engine reference.

---

## Shared Variable Groups

These groups appear in many events and are noted per-event as **"+ System"**, **"+ Ship"**, etc.

### System Variables

Available in most navigation, exploration, and economy events.

| Variable | Example output | Notes |
|---|---|---|
| `{system}` | `Sol` | Current star system name |
| `{star_class}` | `G` | Primary star class (abbreviated). Also accessible as `{primary_star_class}` |
| `{primary_star_class}` | `G` | Alias for `{star_class}` |
| `{is_star_scoopable}` | `True` | `True` (primary star is scoopable) / `False` (not scoopable). Alias `{star_scoopable}` still works. |
| `{allegiance}` | `Federation` | System allegiance |
| `{economy}` | `Agriculture` | Primary economy |
| `{security}` | `Medium Security` | Security level |
| `{government}` | `Democracy` | Government type |
| `{faction}` | `Sol Federal Authority` | Controlling faction |
| `{population}` | `22.7 billion` | Population formatted for speech |
| `{population_raw}` | `22780000000` | Raw population number |

### Ship Variables

Available in combat, navigation, and status events.

| Variable | Example output | Notes |
|---|---|---|
| `{commander}` | `Hawk` | Commander name (without "CMDR" prefix) |
| `{ship}` | `Phantom` | Ship name if set, otherwise ship type |
| `{ship_type}` | `KraitPhantom` | Ship type identifier |
| `{ship_name}` | `Phantom` | Custom ship name (empty if not set) |
| `{ship_ident}` | `PH-01` | Ship ID plate |
| `{hull}` | `75 percent` | Hull health formatted for speech |
| `{hull_raw}` | `75` | Hull health as integer string (0–100) |
| `{fuel}` | `28 of 32 tonnes` | Current and max fuel |
| `{fuel_raw}` | `28` | Current fuel (tonnes, integer string) |
| `{fuel_max_raw}` | `32` | Max fuel capacity (tonnes, integer string) |
| `{jump_range}` | `40.2 light years` | Current max jump range |
| `{jump_range_raw}` | `40.2` | Raw jump range as decimal string |

### Body Variables

Available in scan, approach, and surface events. When listed as **"Nearest body"** prefix, all names gain `nearest_body_` (e.g. `{nearest_body_gravity}`).

| Variable | Example output | Notes |
|---|---|---|
| `{body_type}` | `High metal content body` | Planet class string |
| `{star_type}` | `G` | Abbreviated star type (only non-empty for stars) |
| `{is_scoopable}` | `True` | `True` (scoopable) / `False` (not scoopable). Alias `{scoopable}` still works. |
| `{atmosphere}` | `Carbon dioxide` | Atmosphere type |
| `{volcanism}` | `Minor water magma` | Volcanism |
| `{gravity}` | `0.83 G` | Surface gravity formatted for speech |
| `{gravity_raw}` | `0.83` | Raw gravity as decimal string |
| `{temp}` | `289 Kelvin` | Surface temperature formatted for speech |
| `{temp_raw}` | `289` | Raw temperature (integer string) |
| `{radius}` | `4892 kilometres` | Body radius formatted for speech |
| `{radius_raw}` | `4892` | Raw radius in kilometres (integer string) |
| `{mass}` | `0.58 Earth masses` | Mass formatted for speech |
| `{mass_raw}` | `0.58` | Raw mass as decimal string |
| `{dist_ls}` | `42 light seconds` | Distance from arrival star |
| `{dist_ls_raw}` | `42` | Raw distance in light seconds (integer string) |
| `{value}` | `1.2 million credits` | FSS scan value formatted for speech (formula-based for FSS'd bodies) |
| `{value_raw}` | `1200000` | Raw scan value as integer string (same base as `{value_mapped}`) |
| `{value_mapped}` | `3.4 million credits` | Projected or actual DSS payout (all bonuses) |
| `{value_mapped_raw}` | `3400000` | Raw mapped value as integer string |
| `{is_terraformable}` | `True` | `True` (terraformable) / `False` (not terraformable). Alias `{terra}` still works. |
| `{landable}` | `Landable` | `"Landable"` or `""` |
| `{bio_count}` | `3` | Number of bio signals (integer string) |
| `{geo_count}` | `7` | Number of geo signals (integer string) |
| `{first_disc}` | `Undiscovered` | `"Undiscovered"` or `""` |
| `{first_footfall_flag}` | `First footfall` | `"First footfall"` or `""` |
| `{has_rings}` | `Ringed` | `"Ringed"` or `""` |
| `{ring_count}` | `3` | Number of rings as integer string |
| `{tidal_lock}` | `Tidal lock` | `"Tidal lock"` or `""` |
| `{orbital_period}` | `3.1 days` | Orbital period formatted for speech (1 decimal) |
| `{orbital_period_raw}` | `3.1` | Numeric part only, no unit (use in other-language templates) |
| `{orbital_period_raw_d}` | `3` | Full days component (integer) |
| `{orbital_period_raw_h}` | `3` | Remaining full hours after removing days |
| `{orbital_period_raw_m}` | `22` | Remaining minutes rounded to nearest integer |
| `{semi_major_axis}` | `1.52 astronomical units` | Semi-major axis — spoken unit avoids "AU = Australian Dollar" misread |
| `{semi_major_axis_raw}` | `227936637600` | Raw value in metres (integer string) |
| `{semi_major_axis_au_raw}` | `1.52` | AU value without unit label |
| `{eccentricity}` | `0.15` | Orbital eccentricity |
| `{orbital_inclination}` | `25.3 degrees` | Inclination formatted for speech |
| `{orbital_inclination_raw}` | `25.3` | Raw inclination as decimal string |

### Nearest Body Variables

In system-level events (FSDJump, FSSDiscoveryScan, etc.), a `nearest_body_` prefixed copy of every **Body Variable** above is available when a nearby body is known. Example: `{nearest_body_gravity}`, `{nearest_body_orbital_period_raw_d}`, `{nearest_body_semi_major_axis_au_raw}`.

### Target Variables

Available where Ship Variables are listed. Populated from the ship's current locked target and nav destination.

| Variable | Example output | Notes |
|---|---|---|
| `{target_type}` | `ship` | `"ship"` / `"body"` / `""` |
| `{target_ship_type}` | `FerDeLance` | Targeted ship type |
| `{target_ship_pilot}` | `Ardan Voss` | Pilot name (after scan stage 1) |
| `{target_ship_rank}` | `Deadly` | Combat rank (after scan stage 1) |
| `{target_ship_faction}` | `Kumo Crew` | Faction (after scan stage 2) |
| `{target_ship_legal}` | `Wanted` | Legal status (after scan stage 2) |
| `{target_ship_shield}` | `82` | Shield health 0–100 (integer string) |
| `{target_ship_shield_raw}` | `0.82` | Shield health 0.0–1.0 (decimal string) |
| `{target_ship_hull}` | `74` | Hull health 0–100 (integer string) |
| `{target_ship_hull_raw}` | `0.74` | Hull health 0.0–1.0 (decimal string) |
| `{target_ship_bounty}` | `24 thousand credits` | Bounty formatted for speech |
| `{target_ship_bounty_raw}` | `24000` | Raw bounty as integer string |
| `{target_body}` | `Tau Ceti 5` | Current nav destination name |
| `{target_body_*}` | — | All Body Variables prefixed with `target_body_` (e.g. `{target_body_gravity}`) |

### Bio Scan Variables

Available in `ScanOrganic_*` and `BioReady`/`BioTooClose` events.

| Variable | Example output | Notes |
|---|---|---|
| `{genus}` | `Frutexa` | Genus localised name |
| `{sample_count}` | `2` | Samples taken so far (1–3) |
| `{samples_left}` | `1` | Remaining samples needed |
| `{min_dist}` | `150 metres` | Minimum distance to next sample |
| `{min_dist_raw}` | `150` | Raw minimum distance in metres |
| `{bio_value}` | `1.2 million credits` | Value of this species |
| `{bio_value_raw}` | `1200000` | Raw value as integer string |
| `{body_bio_total}` | `3` | Total bio signals on this body |
| `{body_bio_complete}` | `1` | Completed scans on this body |
| `{body_bio_remaining_count}` | `2` | Remaining scans on this body |
| `{body_bio_remaining_species}` | `Frutexa, Stratum` | Names of remaining species (comma-separated) |

### Bio System Variables

Available in all `ScanOrganic_Analyse_*` events and `ScanOrganic_Log`/`Sample`.

| Variable | Example output | Notes |
|---|---|---|
| `{bio_system_remaining_count}` | `4` | Total incomplete bio scans across the current system |
| `{bio_system_remaining_bodies}` | `2 on A 3, 2 on A 4` | Breakdown per body |
| `{bio_system_complete_count}` | `2` | Completed bio scans in this system |
| `{bio_system_done}` | `complete` | `"complete"` when nothing is left, `""` otherwise |
| `{bio_system_total_value}` | `3.4 million credits` | Total value of completed bio scans |
| `{bio_system_total_value_raw}` | `3400000` | Raw total value as integer string |

### Notable Bodies Variables

Available in `FSSAllBodiesFound`.

| Variable | Example output | Notes |
|---|---|---|
| `{notable_count}` | `3` | ELW + water world + ammonia world count |
| `{elw_count}` | `1` | Earthlike worlds |
| `{ww_count}` | `2` | Water worlds |
| `{aw_count}` | `0` | Ammonia worlds |
| `{tf_count}` | `4` | Terraformable bodies |
| `{bio_body_count}` | `5` | Bodies with bio signals |
| `{neutron_count}` | `1` | Neutron stars |
| `{black_hole_count}` | `0` | Black holes |
| `{high_value_count}` | `2` | Bodies above notable value threshold |
| `{notable_summary}` | `1 earthlike, 2 water worlds` | Pre-built spoken summary (empty: `"nothing notable"`) |
| `{total_scan_value}` | `12 million credits` | Total FSS scan value across all bodies |
| `{total_scan_value_raw}` | `12000000` | Raw total value as integer string |

---

## Events Reference

### Navigation

#### `FSDJump` — Hyperspace arrival
Fires on every FSD or carrier jump.

| Variable | Example | Notes |
|---|---|---|
| `{system}` | `Alpha Centauri` | Destination system |
| `{dist_ly}` | `12.3 light years` | Jump distance formatted for speech |
| `{dist_ly_raw}` | `12.3` | Raw distance as decimal string |
| `{hops_remaining}` | `4` | Hops remaining in active route (`"0"` if no route) |
| `{suffix}` | ` Star G, scoopable. 4 jumps remaining.` | Pre-built summary: star class + hops + population if non-zero |
| **+ System** | | `{star_class}` reflects the arrival star |
| **+ Ship** | | |
| **+ Target** | | |
| **+ Nearest body** | | |

Example:
```toml
[FSDJump]
add = ["Arrived in {system}. WHEN {is_star_scoopable} IS TRUE THEN \"Scoopable {star_class} star.\"; WHEN {hops_remaining} > 0 THEN \"{hops_remaining} jumps left.\";"]
```

---

#### `NavRoute` — Route set
Fires when a nav route is plotted in-game.

| Variable | Example | Notes |
|---|---|---|
| `{dest}` | `Colonia` | Destination system name |
| `{hops}` | `17` | Total number of jumps |
| `{hops_word}` | `jumps` | `"jump"` or `"jumps"` |
| `{dist_ly}` | `22 thousand light years` | Total route distance formatted for speech |
| `{dist_ly_raw}` | `22169.4` | Raw distance as decimal string |
| **+ System** | | Current system at time of plotting |

---

#### `NavRouteClear` — Route cleared
No variables.

---

#### `StartJump_Hyperspace` — Hyperspace jump engaged
No variables.

---

#### `StartJump_Supercruise` — Supercruise engaged from menu
No variables.

---

#### `SupercruiseEntry` — Entering supercruise
| Variable | Notes |
|---|---|
| **+ System** | |
| **+ Ship** | |

---

#### `SupercruiseExit` — Dropping from supercruise (body nearby)
| Variable | Example | Notes |
|---|---|---|
| `{body}` | `Tau Ceti 3` | Full body name |
| `{body_short}` | `3` | Short body name (suffix without system prefix) |
| **+ Body** | | Variables for the nearby body |
| **+ System** | | |

#### `SupercruiseExit_nobdy` — Dropping from supercruise (no body)
| Variable | Notes |
|---|---|
| **+ System** | |

---

#### `DockingGranted` — Docking permission approved
| Variable | Example | Notes |
|---|---|---|
| `{pad}` | `12` | Landing pad number |
| `{station}` | `Dalton Gateway` | Station name |
| **+ System** | | |

#### `DockingDenied` — Docking permission refused
| Variable | Example | Notes |
|---|---|---|
| `{reason}` | `NoSpace` | Denial reason string |

#### `DockingCancelled` — Docking cancelled
No variables.

---

#### `Docked` — Docked at station
| Variable | Example | Notes |
|---|---|---|
| `{station}` | `Dalton Gateway` | Station name |
| `{station_type}` | `Orbis Starport` | Station type string |
| **+ System** | | |
| **+ Ship** | | |

#### `Undocked` — Undocked from station
| Variable | Example | Notes |
|---|---|---|
| `{station}` | `Dalton Gateway` | Station name |
| **+ System** | | |
| **+ Ship** | | |

#### `Undocked_nostation` — Undocked (station name unknown)
| Variable | Notes |
|---|---|
| **+ System** | |
| **+ Ship** | |

---

#### `Touchdown` — Landing on a surface
| Variable | Example | Notes |
|---|---|---|
| `{body}` | `Tau Ceti 3 a` | Full body name |
| `{body_short}` | `3 a` | Short body name |
| `{lat}` | `12.34` | Latitude as decimal string |
| `{lon}` | `-56.78` | Longitude as decimal string |
| **+ Body** | | Variables for the body |
| **+ System** | | |

#### `Liftoff` — Lifting off from a surface
| Variable | Notes |
|---|---|
| `{body}` | Full body name |
| `{body_short}` | Short body name |
| **+ Body** | |
| **+ System** | |

#### `FirstFootfall` — First footfall on a world
| Variable | Notes |
|---|---|
| `{body}` | Full body name |
| `{body_short}` | Short body name |
| **+ Body** | |
| **+ System** | |

---

#### `HighGWarning` — Approaching a ≥ 1.5 G body
| Variable | Example | Notes |
|---|---|---|
| `{g}` | `2.3 G` | Gravity formatted for speech |
| `{g_raw}` | `2.31` | Raw gravity as decimal string |
| `{body}` | `Sirius A 1` | Full body name |
| `{body_short}` | `A 1` | Short body name |
| **+ Body** | | Full body variables |

#### `HighGExtreme` — Approaching a ≥ 3.0 G body (fires 3× spaced 10 s apart)
Same variables as `HighGWarning`.

---

### Combat

#### `UnderAttack` — Under attack (no attacker name)
No variables.

#### `UnderAttack_target` — Under attack (attacker known)
| Variable | Example | Notes |
|---|---|---|
| `{target}` | `Ardan Voss` | Attacker name |

---

#### `ShieldDown` — Shields offline
| Variable | Notes |
|---|---|
| **+ Ship** | |
| **+ System** | |

#### `ShieldUp` — Shields restored
| Variable | Notes |
|---|---|
| **+ Ship** | |
| **+ System** | |

---

#### `HullDamage_Warning` — Hull below 75%
| Variable | Example | Notes |
|---|---|---|
| `{pct}` | `74` | Hull health as integer string |
| **+ Ship** | | All ship variables including `{hull}` `{hull_raw}` |

#### `HullDamage_Critical` — Hull below 25%
Same variables as `HullDamage_Warning`.

---

#### `Died` — Ship destroyed
| Variable | Example | Notes |
|---|---|---|
| `{msg}` | `Ship destroyed in Alpha Centauri.` | Pre-built death message |
| **+ Ship** | | |
| **+ System** | | |

---

#### `Bounty` — Bounty earned (no specific target)
| Variable | Example | Notes |
|---|---|---|
| `{reward}` | `24 thousand credits` | Bounty formatted for speech |
| `{reward_raw}` | `24000` | Raw bounty as integer string |

#### `Bounty_target` — Bounty earned (specific target)
| Variable | Example | Notes |
|---|---|---|
| `{reward}` | `24 thousand credits` | Bounty formatted for speech |
| `{reward_raw}` | `24000` | Raw bounty as integer string |
| `{victim}` | `Ardan Voss` | Target name |

#### `FactionKillBond` — Combat bond awarded
| Variable | Example | Notes |
|---|---|---|
| `{reward}` | `50 thousand credits` | Bond value formatted for speech |
| `{reward_raw}` | `50000` | Raw bond value as integer string |

---

#### `Interdicted_Submitted` — Submitted to interdiction
No variables.

#### `Interdicted_Submitted_name` — Submitted (interdictor named)
| Variable | Example | Notes |
|---|---|---|
| `{interdictor}` | `Ardan Voss` | Interdictor name |

#### `Interdicted_Escaped` — Escaped interdiction
No variables.

#### `Interdicted_Escaped_name` — Escaped (interdictor named)
| Variable | Example | Notes |
|---|---|---|
| `{interdictor}` | `Ardan Voss` | Interdictor name |

#### `Interdiction_Success` — Successfully interdicted a target
| Variable | Example | Notes |
|---|---|---|
| `{victim}` | `Ardan Voss` | Interdicted target name |

#### `Interdiction_Failed` — Interdiction failed
No variables.

---

#### `Scanned` — Your ship was scanned
| Variable | Example | Notes |
|---|---|---|
| `{scan_type}` | `Crime` | Type of scan |

#### `HeatWarning` — Heat critical
No variables.

#### `HyperdictInterdict` — Thargoid interdiction
No variables.

---

### Exploration

#### `FSSDiscoveryScan` — Honk (discovery scan) complete
| Variable | Example | Notes |
|---|---|---|
| `{total}` | `12` | Total bodies detected (integer string) |
| **+ System** | | |

---

#### `FSSAllBodiesFound` — All bodies in system found
| Variable | Notes |
|---|---|
| **+ Notable bodies** | All notable body summary variables |
| **+ System** | |

Example:
```toml
[FSSAllBodiesFound]
add = ["Scan complete. WHEN {elw_count} > 0 THEN \"{elw_count} earthlike.\"; WHEN {tf_count} > 0 THEN \"{tf_count} terraformable.\";\nTotal value: {total_scan_value}."]
```

---

#### `FSSSignalDiscovered` — Unregistered signal source found
| Variable | Example | Notes |
|---|---|---|
| `{sig}` | `Unregistered Comms Beacon` | Signal name |

---

#### `Scan_Undiscovered` — Arrived in an undiscovered system (AutoScan)
| Variable | Notes |
|---|---|
| **+ System** | |

---

#### `Scan_Notable` — Scanned a notable body (earthlike, water/ammonia world, neutron, black hole, terraformable, high-value)
| Variable | Example | Notes |
|---|---|---|
| `{body_short}` | `A 3` | Short body name (suffix only, without system prefix) |
| `{body}` | `Sol A 3` | Full body name |
| `{detail}` | `Earthlike body. Landable. 3 bio signals.` | Pre-built detail string |
| **+ Body** | | All body variables |
| **+ System** | | |

---

#### `Scan_Detailed` — Scanned a detailed body (not notable)
Same variables as `Scan_Notable`.

---

#### `SAAScanComplete` — DSS mapping complete
| Variable | Example | Notes |
|---|---|---|
| `{body_short}` | `A 3` | Short body name |
| `{body}` | `Sol A 3` | Full body name |
| `{sig_txt}` | ` Signals: 3 bio.` | Bio/geo signal summary (empty string if none) |
| `{eff_txt}` | ` Efficiency target reached.` | Efficiency bonus message (empty if not reached) |
| `{map_txt}` | ` First map!` | `" First map!"` or `""` |
| `{map_value}` | `3.4 million credits` | Mapped body value formatted for speech (alias of `{value_mapped}`) |
| `{map_value_raw}` | `3400000` | Raw mapped value as integer string |
| **+ Body** | | |
| **+ System** | | |

---

#### `CodexEntry` — Codex entry discovered
| Variable | Example | Notes |
|---|---|---|
| `{name}` | `Lagrange Cloud (Caeruleum)` | Codex entry name |

---

### Biological Scanning

#### `ScanOrganic_Log` — First sample of a bio species taken
| Variable | Example | Notes |
|---|---|---|
| `{species}` | `Frutexa Acus` | Species localised name |
| `{body}` | `Sol A 3 a` | Full body name |
| `{body_short}` | `A 3 a` | Short body name |
| **+ Bio scan** | | `{genus}` `{sample_count}` `{min_dist}` `{bio_value}` etc. |
| **+ Body** | | |
| **+ Bio system** | | System-wide progress |

#### `ScanOrganic_Log_NewSpecies` — First sample and it's a new-to-galaxy species
Same variables as `ScanOrganic_Log`.

---

#### `ScanOrganic_Sample` — Second or third sample taken
| Variable | Example | Notes |
|---|---|---|
| `{count}` | `2` | Current sample number (`"2"` or `"3"`) |
| `{species}` | `Frutexa Acus` | Species localised name |
| `{body}` | `Sol A 3 a` | Full body name |
| `{body_short}` | `A 3 a` | Short body name |
| **+ Bio scan** | | |
| **+ Body** | | |
| **+ Bio system** | | |

---

#### `ScanOrganic_Analyse` — All 3 samples taken, analysis complete
| Variable | Example | Notes |
|---|---|---|
| `{species}` | `Frutexa Acus` | Species localised name |
| `{val_str}` | `1.2 million credits` | Credit value formatted for speech |
| `{val_raw}` | `1200000` | Raw credit value as integer string |
| `{ff_suffix}` | ` First footfall bonus applied.` | Empty string if no footfall bonus |
| `{body}` | `Sol A 3 a` | Full body name |
| `{body_short}` | `A 3 a` | Short body name |
| **+ Bio scan** | | |
| **+ Body** | | |
| **+ Bio system** | | |

---

#### `ScanOrganic_Analyse_BodyLeft` — Remaining bios on this body after analysis
| Variable | Example | Notes |
|---|---|---|
| `{body_left}` | `2` | Remaining bio signals on this body |
| `{bio_word}` | `bios` | `"bio"` or `"bios"` |
| `{verb}` | `are` | `"is"` or `"are"` |
| `{body}` | `Sol A 3 a` | Full body name |
| `{body_short}` | `A 3 a` | Short body name |
| **+ Bio system** | | |

---

#### `ScanOrganic_Analyse_SystemMore` — Remaining bios in system after analysis
| Variable | Example | Notes |
|---|---|---|
| `{parts_str}` | `2 on A 3, 1 on A 4` | Summary of remaining bios per body |
| **+ Bio system** | | |

---

#### `ScanOrganic_Analyse_SystemDone` — All bios in system complete
| Variable | Notes |
|---|---|
| **+ Bio system** | All bio system variables |

---

#### `BioReady` — Distance to next sample is sufficient (can scan)
| Variable | Example | Notes |
|---|---|---|
| `{species}` | `Frutexa Acus` | Species localised name |
| **+ Bio scan** | | `{min_dist}` `{sample_count}` `{bio_value}` etc. |
| **+ Body** | | |

#### `BioTooClose` — Re-entered exclusion zone around a previous sample
| Variable | Notes |
|---|---|
| `{species}` | Species localised name |
| **+ Bio scan** | |
| **+ Body** | |

---

### Missions

#### `MissionAccepted` — Mission taken
| Variable | Example | Notes |
|---|---|---|
| `{name}` | `Massacre Wing` | Mission name |
| `{dest}` | `Deciat` | Destination system or station |
| **+ System** | | |

#### `MissionCompleted` — Mission handed in
| Variable | Example | Notes |
|---|---|---|
| `{name}` | `Massacre Wing` | Mission name |
| `{reward}` | `2 million credits` | Reward formatted for speech |
| `{reward_raw}` | `2000000` | Raw reward as integer string |
| **+ System** | | |

#### `MissionFailed` — Mission failed
| Variable | Example | Notes |
|---|---|---|
| `{name}` | `Massacre Wing` | Mission name |

---

### Trade & Economy

#### `MarketSell` — Sold cargo (no profit data)
| Variable | Example | Notes |
|---|---|---|
| `{count}` | `120` | Units sold |
| `{commodity}` | `Gold` | Commodity name |
| `{total}` | `2.4 million credits` | Total sale value |
| `{total_raw}` | `2400000` | Raw total as integer string |

#### `MarketSell_profit` — Sold cargo (with profit)
Same as `MarketSell` plus:

| Variable | Example | Notes |
|---|---|---|
| `{profit}` | `800 thousand credits` | Profit on the sale |
| `{profit_raw}` | `800000` | Raw profit as integer string |

---

#### `SellExplorationData` — Exploration data sold at cartographics
| Variable | Example | Notes |
|---|---|---|
| `{value}` | `4.2 million credits` | Sale value formatted for speech |
| `{value_raw}` | `4200000` | Raw sale value as integer string |
| **+ System** | | |

---

#### `EjectCargo` — Cargo ejected
| Variable | Example | Notes |
|---|---|---|
| `{cargo}` | `Gold` | Cargo type name |

---

### Engineers

#### `EngineerUnlocked` — Engineer unlocked
| Variable | Example | Notes |
|---|---|---|
| `{engineer}` | `Felicity Farseer` | Engineer name |

#### `EngineerRank` — Engineer rank increased
| Variable | Example | Notes |
|---|---|---|
| `{engineer}` | `Felicity Farseer` | Engineer name |
| `{rank}` | `3` | New rank (integer string) |

---

### Ship Status

#### `FuelScoop_Full` — Fuel tank reached full during scooping
| Variable | Notes |
|---|---|
| **+ Ship** | `{fuel}` `{fuel_raw}` `{fuel_max_raw}` `{ship}` etc. |

---

#### `Repair` — Component repair complete
| Variable | Example | Notes |
|---|---|---|
| `{item}` | `Hull` | Repaired item name |

#### `RepairAll` — Full repair complete
No variables.

#### `Resurrect` — Respawned after death
No variables.

---

### Login / Logout

#### `LoadGame` — Logged into the game
| Variable | Notes |
|---|---|
| **+ Ship** | `{commander}` `{ship}` `{hull}` `{fuel}` `{jump_range}` etc. |

#### `Shutdown` — Game closed or logged out
| Variable | Notes |
|---|---|
| **+ System** | |
| **+ Ship** | |

#### `Nova_Startup` — NOVA started
No variables.

---

### COVAS / Ship Status Callouts

These events have **no variables**. Silence any with `replace = []`.

| Event key | Default callout |
|---|---|
| `LandingGear_Deployed` | "Landing gear deployed." |
| `LandingGear_Retracted` | "Landing gear retracted." |
| `CargoScoop_Deployed` | "Cargo scoop deployed." |
| `CargoScoop_Retracted` | "Cargo scoop retracted." |
| `Hardpoints_Deployed` | "Hardpoints deployed." |
| `Hardpoints_Retracted` | "Hardpoints retracted." |
| `Lights_On` | "Lights on." |
| `Lights_Off` | "Lights off." |
| `NightVision_On` | "Night vision enabled." |
| `NightVision_Off` | "Night vision disabled." |
| `FlightAssist_Off` | "Flight assist off." |
| `FlightAssist_On` | "Flight assist on." |
| `SilentRunning_On` | "Silent running enabled." |
| `SilentRunning_Off` | "Silent running disabled." |
| `AnalysisMode` | "Analysis mode." |
| `CombatMode` | "Combat mode." |
| `MassLocked` | "Mass locked." |
| `MassLockReleased` | "Mass lock released." |
| `SRV_Deployed` | "S R V deployed." |
| `SRV_Secured` | "S R V secured." |
| `SRV_Boarded` | "S R V boarded." |
| `SRV_Exited` | "S R V exited." |
| `NavRouteClear` | "Route cleared." |
| `DockingCancelled` | "Docking aborted." |
| `HeatWarning` | "Warning: Heat critical!" |
| `HyperdictInterdict` | "Thargoid interdiction! Hyperdrive interrupted!" |
| `System_EDSM_Unknown` | "System unknown to EDSM." |

---

## Conditional Examples

Boolean variables (`{is_scoopable}`, `{is_terraformable}`) return Python `True`/`False`.
Use `IS TRUE` / `IS FALSE` for these (e.g. `WHEN {is_scoopable} IS TRUE THEN "Scoopable.";`).
Deprecated aliases (`{terra}`, `{scoopable}`, `{star_scoopable}`) still evaluate the same way.
Other flag variables (`{landable}`, `{first_disc}` etc.) are `""` when absent and non-empty when present — use `IS TRUE` for those.

```toml
[Scan_Notable]
add = [
  'Scanned {body_short}. WHEN {value_raw} > 1000000 THEN "Value: {value}."; WHEN {bio_count} > 0 THEN "{bio_count} bio signals."; WHEN {is_terraformable} IS TRUE THEN "Terraformable!";'
]

[FSDJump]
add = [
  'Arrived in {system}. WHEN {is_star_scoopable} IS TRUE THEN "Scoopable {star_class} star."; WHEN {hops_remaining} > 0 THEN "{hops_remaining} jumps remaining.";'
]

[FSSAllBodiesFound]
add = [
  'Scan complete. WHEN {elw_count} > 0 THEN "{elw_count} earthlike."; WHEN {ww_count} > 0 THEN "{ww_count} water worlds."; Total value: {total_scan_value}.'
]

[ScanOrganic_Analyse]
add = [
  '{species} complete. Worth {val_str}.{ff_suffix} WHEN {bio_system_done} IS TRUE THEN "All bios done in system!"; WHEN {bio_system_remaining_count} > 0 THEN "{bio_system_remaining_count} remaining.";'
]
```
