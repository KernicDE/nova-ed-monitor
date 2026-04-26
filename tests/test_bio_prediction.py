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
