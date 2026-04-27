"""Smoke tests for predict_bio_species — verifies eliminative gates and key correctness.

Tests are anchored to known game conditions, not to the prediction function itself
(that would be circular). Where possible, names verified against _BIO_SPECIES_VALUES.
"""
from __future__ import annotations
from ed_monitor.events import predict_bio_species, _BIO_SPECIES_VALUES


def predict(
    planet_class: str = "Rocky body",
    atmosphere: str = "Thin Carbon dioxide atmosphere",
    surface_temp: float = 185.0,
    surface_gravity: float = 2.7,   # ~0.275 G — below 0.28 gate
    volcanism: str = "No volcanism",
    primary_star_type: str = "G",
    dist_ls: float = 500.0,
) -> list[str]:
    return predict_bio_species(
        planet_class, atmosphere, surface_temp, surface_gravity,
        volcanism, primary_star_type, dist_ls,
    )


# ── Global gates ──────────────────────────────────────────────────────────────

class TestGlobalGates:
    def test_empty_atmosphere_returns_nothing(self):
        assert predict(atmosphere="") == []

    def test_thick_atmosphere_returns_nothing(self):
        assert predict(atmosphere="Dense Carbon dioxide atmosphere") == []

    def test_none_atmosphere_returns_nothing(self):
        assert predict(atmosphere="No atmosphere") == []

    def test_thin_atmosphere_can_produce_predictions(self):
        assert len(predict()) > 0

    def test_high_gravity_blocks_aleoida(self):
        """g > 0.28 must suppress Aleoida even on a CO2 rocky body at 180K."""
        result = predict(
            atmosphere="Thin Carbon dioxide atmosphere",
            surface_temp=179.0,
            surface_gravity=3.0,  # ~0.306 G
        )
        assert not any(s.startswith("Aleoida") for s in result)

    def test_low_gravity_allows_aleoida(self):
        """g <= 0.28, CO2 rocky, 179K → Aleoida Coronamus expected."""
        result = predict(
            atmosphere="Thin Carbon dioxide atmosphere",
            surface_temp=183.0,
            surface_gravity=2.7,  # ~0.275 G
        )
        assert "Aleoida Coronamus" in result


# ── Wrong-name regression (none of the old bad names should appear) ───────────

class TestNoOldBadNames:
    def _all_species(self) -> set[str]:
        atmospheres = [
            ("Rocky body",            "Thin Carbon dioxide atmosphere",   185.0, 2.7),
            ("Rocky body",            "Thin Ammonia atmosphere",          165.0, 2.7),
            ("Rocky body",            "Thin Sulphur dioxide atmosphere",  170.0, 2.7),
            ("Rocky body",            "Thin Water atmosphere",            200.0, 2.7),
            ("High metal content body", "Thin Carbon dioxide atmosphere", 185.0, 2.7),
            ("Icy body",              "Thin Methane atmosphere",           97.0, 2.0),
            ("Icy body",              "Thin Argon atmosphere",             50.0, 2.0),
            ("Icy body",              "Thin Neon atmosphere",              22.0, 2.0),
            ("Rocky body",            "Thin Nitrogen atmosphere",         100.0, 2.7),
            ("Rocky body",            "Thin Oxygen atmosphere",           195.0, 2.7),
        ]
        result: set[str] = set()
        for pc, atm, t, g in atmospheres:
            for sp in predict_bio_species(pc, atm, t, g, "No volcanism", "G", 500.0):
                result.add(sp)
        return result

    def test_no_recepta_condiviva(self):
        assert "Recepta Condiviva" not in self._all_species()

    def test_no_recepta_delta(self):
        assert "Recepta Delta" not in self._all_species()

    def test_no_clypeus_speculumi(self):
        assert "Clypeus Speculumi" not in self._all_species()

    def test_no_fungoida_setisis(self):
        assert "Fungoida Setisis" not in self._all_species()

    def test_no_fonticulua_upupam(self):
        assert "Fonticulua Upupam" not in self._all_species()

    def test_no_osseus_pelleas(self):
        assert "Osseus Pelleas" not in self._all_species()

    def test_no_tussock_serrani(self):
        assert "Tussock Serrani" not in self._all_species()

    def test_no_frutexa_catena(self):
        assert "Frutexa Catena" not in self._all_species()

    def test_no_tussock_viridan(self):
        assert "Tussock Viridan" not in self._all_species()

    def test_all_predicted_names_in_value_table(self):
        """Every predicted species must resolve to a non-zero value in _BIO_SPECIES_VALUES."""
        unknowns = [sp for sp in self._all_species() if sp not in _BIO_SPECIES_VALUES]
        assert unknowns == [], f"Species not in value table: {unknowns}"


# ── Spot-checks for specific species placement ────────────────────────────────

class TestSpeciesPlacement:
    def test_aleoida_arcus_is_co2_not_argon(self):
        """Aleoida Arcus spawns in CO2 (175-180K), NOT argon."""
        co2_result = predict(
            atmosphere="Thin Carbon dioxide atmosphere",
            surface_temp=177.0, surface_gravity=2.7,
        )
        argon_result = predict_bio_species(
            "Rocky body", "Thin Argon atmosphere", 50.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        assert "Aleoida Arcus" in co2_result
        assert "Aleoida Arcus" not in argon_result

    def test_concha_aureolas_is_ammonia(self):
        """Concha Aureolas is in ammonia, NOT nitrogen."""
        ammonia = predict_bio_species(
            "Rocky body", "Thin Ammonia atmosphere", 165.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        nitrogen = predict_bio_species(
            "Rocky body", "Thin Nitrogen atmosphere", 100.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        assert "Concha Aureolas" in ammonia
        assert "Concha Aureolas" not in nitrogen

    def test_concha_biconcavis_is_nitrogen(self):
        """Concha Biconcavis is in nitrogen, NOT ammonia."""
        nitrogen = predict_bio_species(
            "Rocky body", "Thin Nitrogen atmosphere", 100.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        ammonia = predict_bio_species(
            "Rocky body", "Thin Ammonia atmosphere", 165.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        assert "Concha Biconcavis" in nitrogen
        assert "Concha Biconcavis" not in ammonia

    def test_fonticulua_upsilon_in_argon_rich(self):
        """Fonticulua Upsilon requires argon-rich on icy body, not plain argon."""
        rich = predict_bio_species(
            "Icy body", "Thin Argon-rich atmosphere", 50.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        plain = predict_bio_species(
            "Icy body", "Thin Argon atmosphere", 50.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        assert "Fonticulua Upsilon" in rich
        assert "Fonticulua Upsilon" not in plain
        assert "Fonticulua Campestris" in plain
        assert "Fonticulua Campestris" not in rich

    def test_recepta_in_sulphur_dioxide(self):
        """All Recepta species are in sulphur dioxide atmosphere."""
        sulphur_icy = predict_bio_species(
            "Icy body", "Thin Sulphur dioxide atmosphere", 171.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        sulphur_rocky = predict_bio_species(
            "Rocky body", "Thin Sulphur dioxide atmosphere", 138.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        assert "Recepta Conditivus" in sulphur_icy
        assert "Recepta Deltahedronix" in sulphur_rocky

    def test_fumerola_all_variants_by_volcanism(self):
        """Each Fumerola variant appears only under its specific volcanism type."""
        aquatis = predict_bio_species(
            "Icy body", "Thin Methane atmosphere", 80.0, 2.0,
            "Water Geysers Volcanism", "G", 500.0,
        )
        carbosis = predict_bio_species(
            "Icy body", "Thin Methane atmosphere", 95.0, 2.0,
            "Methane Magma Volcanism", "G", 500.0,
        )
        extremus = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 185.0, 2.0,
            "Silicate Vapour Geysers Volcanism", "G", 500.0,
        )
        assert "Fumerola Aquatis" in aquatis
        assert "Fumerola Carbosis" in carbosis
        assert "Fumerola Extremus" in extremus

    def test_fungoida_setulus_in_methane_ammonia(self):
        """Fungoida Setulus (not Setisis) is in methane or ammonia."""
        methane = predict_bio_species(
            "Rocky body", "Thin Methane atmosphere", 165.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        assert "Fungoida Setulus" in methane

    def test_tussock_temperature_split(self):
        """Tussock variants split by temperature on CO2 rocky bodies."""
        at_177 = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 177.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        at_185 = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 185.0, 2.5,
            "No volcanism", "G", 500.0,
        )
        assert "Tussock Albata" in at_177       # 175-180K
        assert "Tussock Albata" not in at_185
        assert "Tussock Caputus" in at_185      # 180-190K


# ── No-atmosphere genera (require system context or specific star/planet types) ─

class TestNoAtmosphereGenera:
    def test_amphora_requires_metal_rich_star_a_and_system_life(self):
        """Amphora Plant: no atmo, metal-rich, star A, system has ELW/GG life."""
        base = predict_bio_species(
            "Metal rich body", "", 300.0, 2.0,
            "No volcanism", "A", 500.0,
            system_has_earth_like=True,
        )
        assert "Amphora Plant" in base
        # Missing system context → no Amphora
        no_ctx = predict_bio_species(
            "Metal rich body", "", 300.0, 2.0,
            "No volcanism", "A", 500.0,
        )
        assert "Amphora Plant" not in no_ctx
        # Wrong star type → no Amphora
        wrong_star = predict_bio_species(
            "Metal rich body", "", 300.0, 2.0,
            "No volcanism", "G", 500.0,
            system_has_earth_like=True,
        )
        assert "Amphora Plant" not in wrong_star

    def test_brain_tree_requires_volcanism(self):
        """Brain Trees need volcanism and planet type + temp match."""
        # Roseum is the only species that doesn't need system context
        roseum = predict_bio_species(
            "Rocky body", "", 250.0, 2.0,
            "Silicate Vapour Geysers Volcanism", "G", 500.0,
        )
        assert "Brain Tree Roseum" in roseum
        # No volcanism → no Brain Trees
        no_vol = predict_bio_species(
            "Rocky body", "", 250.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        assert "Brain Tree Roseum" not in no_vol

    def test_brain_tree_system_context_for_non_roseum(self):
        """Aureum etc. need system ELW/GG life context."""
        with_ctx = predict_bio_species(
            "Metal rich body", "", 400.0, 2.0,
            "Silicate Vapour Geysers Volcanism", "G", 500.0,
            system_has_earth_like=True,
        )
        assert "Brain Tree Aureum" in with_ctx
        assert "Brain Tree Ostrinum" in with_ctx
        without_ctx = predict_bio_species(
            "Metal rich body", "", 400.0, 2.0,
            "Silicate Vapour Geysers Volcanism", "G", 500.0,
        )
        assert "Brain Tree Aureum" not in without_ctx
        # Roseum still appears without context
        assert "Brain Tree Roseum" in without_ctx

    def test_crystalline_shard_conditions(self):
        """Crystalline Shard: no atmo, star A/F/G/K/M/S, dist>12000 LS, system life."""
        ok = predict_bio_species(
            "Rocky body", "", 50.0, 2.0,
            "No volcanism", "G", 15000.0,
            system_has_ammonia_world=True,
        )
        assert "Crystalline Shard" in ok
        # Too close → no shard
        close = predict_bio_species(
            "Rocky body", "", 50.0, 2.0,
            "No volcanism", "G", 5000.0,
            system_has_ammonia_world=True,
        )
        assert "Crystalline Shard" not in close
        # Wrong star → no shard
        wrong_star = predict_bio_species(
            "Rocky body", "", 50.0, 2.0,
            "No volcanism", "O", 15000.0,
            system_has_ammonia_world=True,
        )
        assert "Crystalline Shard" not in wrong_star

    def test_sinuous_tuber_by_planet_type(self):
        """Sinuous Tubers appear on volcanism bodies by planet type."""
        rocky = predict_bio_species(
            "Rocky body", "", 200.0, 2.0,
            "Water Geysers Volcanism", "G", 500.0,
        )
        assert "Sinuous Tuber Albidum" in rocky
        assert "Sinuous Tuber Caeruleum" in rocky
        mr = predict_bio_species(
            "Metal rich body", "", 200.0, 2.0,
            "Water Geysers Volcanism", "G", 500.0,
        )
        assert "Sinuous Tuber Blatteum" in mr
        # No volcanism → none
        no_vol = predict_bio_species(
            "Rocky body", "", 200.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        assert not any(s.startswith("Sinuous Tuber") for s in no_vol)

    def test_anemone_star_type_filtering(self):
        """Anemones only on O/B/A stars, planet-type dependent."""
        o_star = predict_bio_species(
            "Rocky body", "", 200.0, 2.0,
            "No volcanism", "O", 500.0,
        )
        assert "Anemone Prasinum Bioluminescent" in o_star
        b_star = predict_bio_species(
            "Rocky body", "", 200.0, 2.0,
            "No volcanism", "B", 500.0,
        )
        assert "Anemone Luteolum" in b_star
        g_star = predict_bio_species(
            "Rocky body", "", 200.0, 2.0,
            "No volcanism", "G", 500.0,
        )
        assert not any(s.startswith("Anemone") for s in g_star)


# ── max_predictions capping ───────────────────────────────────────────────────

class TestMaxPredictions:
    def test_cap_limits_output_length(self):
        """When max_predictions is set, output is capped to that many species."""
        result = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 185.0, 2.5,
            "No volcanism", "G", 500.0,
            max_predictions=3,
        )
        assert len(result) <= 3

    def test_no_cap_when_zero(self):
        """max_predictions=0 means no cap."""
        result = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 185.0, 2.5,
            "No volcanism", "G", 500.0,
            max_predictions=0,
        )
        assert len(result) > 3  # normally many predictions on CO2 rocky

    def test_cap_prefers_higher_value_species(self):
        """Capping should keep higher-value species over lower-value ones."""
        full = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 185.0, 2.5,
            "No volcanism", "G", 500.0,
            max_predictions=0,
        )
        capped = predict_bio_species(
            "Rocky body", "Thin Carbon dioxide atmosphere", 185.0, 2.5,
            "No volcanism", "G", 500.0,
            max_predictions=2,
        )
        assert len(capped) == 2
        # The top 2 by value from the full list should be the capped result
        from ed_monitor.events import _BIO_SPECIES_VALUES, _BIO_GENUS_VALUE_RANGE

        def _score(sp: str) -> int:
            v = _BIO_SPECIES_VALUES.get(sp, 0)
            if v == 0:
                genus = sp.split()[0].lower() if sp else ""
                lo, hi = _BIO_GENUS_VALUE_RANGE.get(genus, (0, 0))
                v = hi
            return v

        full_sorted = sorted(full, key=_score, reverse=True)
        assert capped == full_sorted[:2]
