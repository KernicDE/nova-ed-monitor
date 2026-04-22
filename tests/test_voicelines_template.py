"""Tests for the voiceline template engine — includes and conditionals (issue #96)."""
from __future__ import annotations
from pathlib import Path
import pytest
from ed_monitor.voicelines import _eval_clause, _eval_condition, _expand_includes, _evaluate_conditionals


class TestEvalClause:
    def test_is_true_with_nonempty(self):
        assert _eval_clause("Terraformable IS TRUE") is True

    def test_is_true_with_empty(self):
        assert _eval_clause(" IS TRUE") is False

    def test_is_false_with_empty(self):
        assert _eval_clause(" IS FALSE") is True

    def test_is_false_with_nonempty(self):
        assert _eval_clause("Landable IS FALSE") is False

    def test_is_not_true_with_nonempty(self):
        assert _eval_clause("Landable IS NOT TRUE") is False

    def test_is_not_true_with_empty(self):
        assert _eval_clause(" IS NOT TRUE") is True

    def test_numeric_less_than_true(self):
        assert _eval_clause("25 < 50") is True

    def test_numeric_less_than_false(self):
        assert _eval_clause("75 < 50") is False

    def test_numeric_greater_than(self):
        assert _eval_clause("3 > 0") is True

    def test_numeric_equal(self):
        assert _eval_clause("100 == 100") is True

    def test_numeric_not_equal(self):
        assert _eval_clause("50 != 100") is True

    def test_numeric_lte(self):
        assert _eval_clause("50 <= 50") is True

    def test_numeric_gte(self):
        assert _eval_clause("75 >= 75") is True

    def test_string_equality_true(self):
        assert _eval_clause('Industrial == Industrial') is True

    def test_string_equality_false(self):
        assert _eval_clause('Refinery == Industrial') is False

    def test_string_equality_quoted(self):
        assert _eval_clause('Refinery == "Refinery"') is True

    def test_string_not_equal(self):
        assert _eval_clause('Industrial != "Refinery"') is True

    def test_zero_is_falsy_for_is_true(self):
        assert _eval_clause("0 IS TRUE") is False

    def test_zero_is_truthy_for_is_false(self):
        assert _eval_clause("0 IS FALSE") is True


class TestEvalCondition:
    def test_and_both_true(self):
        assert _eval_condition("3 > 0 AND Terraformable IS TRUE", {}) is True

    def test_and_first_false(self):
        assert _eval_condition("0 > 3 AND Terraformable IS TRUE", {}) is False

    def test_and_second_false(self):
        assert _eval_condition("3 > 0 AND  IS TRUE", {}) is False

    def test_or_first_true(self):
        assert _eval_condition("3 > 0 OR  IS TRUE", {}) is True

    def test_or_both_false(self):
        assert _eval_condition(" IS TRUE OR 0 > 3", {}) is False

    def test_variable_substitution(self):
        assert _eval_condition("{bio_count} > 0", {"bio_count": "3"}) is True

    def test_variable_substitution_false(self):
        assert _eval_condition("{bio_count} > 0", {"bio_count": ""}) is False

    def test_is_true_via_var(self):
        assert _eval_condition("{terra} IS TRUE", {"terra": "Terraformable"}) is True

    def test_is_true_via_empty_var(self):
        assert _eval_condition("{terra} IS TRUE", {"terra": ""}) is False

    def test_and_with_vars(self):
        assert _eval_condition(
            "{bio_count} > 0 AND {first_disc} IS TRUE",
            {"bio_count": "2", "first_disc": "Undiscovered"},
        ) is True

    def test_or_with_vars(self):
        assert _eval_condition(
            "{terra} IS TRUE OR {landable} IS TRUE",
            {"terra": "", "landable": "Landable"},
        ) is True


class TestEvaluateConditionals:
    def test_condition_true_inserts_text(self):
        result = _evaluate_conditionals(
            'Hello. WHEN {terra} IS TRUE THEN "Terraformable.";',
            {"terra": "Terraformable"},
        )
        assert result == "Hello. Terraformable."

    def test_condition_false_removes_block(self):
        result = _evaluate_conditionals(
            'Hello. WHEN {terra} IS TRUE THEN "Terraformable.";',
            {"terra": ""},
        )
        assert result == "Hello. "

    def test_condition_without_trailing_semicolon(self):
        result = _evaluate_conditionals(
            'WHEN {bio_count} > 0 THEN "Bio detected."',
            {"bio_count": "3"},
        )
        assert result == "Bio detected."

    def test_multiple_when_blocks(self):
        result = _evaluate_conditionals(
            'X. WHEN {terra} IS TRUE THEN "TF."; WHEN {bio_count} > 0 THEN "Bio.";',
            {"terra": "Terraformable", "bio_count": "2"},
        )
        assert result == "X. TF. Bio."

    def test_multiple_when_one_false(self):
        result = _evaluate_conditionals(
            'X. WHEN {terra} IS TRUE THEN "TF."; WHEN {bio_count} > 0 THEN "Bio.";',
            {"terra": "", "bio_count": "2"},
        )
        assert result == "X.  Bio."

    def test_then_text_preserves_var_references(self):
        # {value} reference in THEN text is preserved for later format pass
        result = _evaluate_conditionals(
            'WHEN {value_raw} > 0 THEN "Worth {value}.";',
            {"value_raw": "500000", "value": "500 thousand"},
        )
        assert result == "Worth {value}."

    def test_no_when_blocks_unchanged(self):
        result = _evaluate_conditionals("Arrived in {system}.", {"system": "Sol"})
        assert result == "Arrived in {system}."

    def test_empty_string(self):
        assert _evaluate_conditionals("", {}) == ""


class TestExpandIncludes:
    def test_explicit_include_replaced_with_fragment(self):
        lines_map = {"_greeting": ["Hello, {commander}."]}
        result = _expand_includes("{include:_greeting} Arrived.", lines_map, {"commander": "Kernic"})
        assert result == "Hello, {commander}. Arrived."

    def test_shorthand_include_replaced_with_fragment(self):
        lines_map = {"_greeting": ["Hello, {commander}."]}
        result = _expand_includes("{_greeting} Arrived.", lines_map, {})
        assert result == "Hello, {commander}. Arrived."

    def test_shorthand_and_explicit_equivalent(self):
        lines_map = {"_frag": ["X"]}
        assert _expand_includes("{include:_frag}", lines_map, {}) == \
               _expand_includes("{_frag}", lines_map, {})

    def test_missing_explicit_include_replaced_with_empty(self):
        result = _expand_includes("{include:_missing} Text.", {}, {})
        assert result == " Text."

    def test_missing_shorthand_replaced_with_empty(self):
        result = _expand_includes("{_missing} Text.", {}, {})
        assert result == " Text."

    def test_no_include_unchanged(self):
        result = _expand_includes("Arrived in {system}.", {}, {"system": "Sol"})
        assert result == "Arrived in {system}."

    def test_include_without_underscore_prefix_treated_as_missing(self):
        # Only _ prefix keys are fragments (explicit syntax)
        lines_map = {"greeting": ["Hello."]}
        result = _expand_includes("{include:greeting} Text.", lines_map, {})
        assert result == " Text."

    def test_circular_include_resolved_as_empty(self):
        lines_map = {"_loop": ["{include:_loop}"]}
        result = _expand_includes("{include:_loop}", lines_map, {})
        assert result == ""

    def test_circular_shorthand_resolved_as_empty(self):
        lines_map = {"_loop": ["{_loop}"]}
        result = _expand_includes("{_loop}", lines_map, {})
        assert result == ""

    def test_nested_include(self):
        lines_map = {
            "_b": ["world"],
            "_a": ["hello {include:_b}"],
        }
        result = _expand_includes("{include:_a}", lines_map, {})
        assert result == "hello world"

    def test_nested_shorthand(self):
        lines_map = {
            "_b": ["world"],
            "_a": ["hello {_b}"],
        }
        result = _expand_includes("{_a}", lines_map, {})
        assert result == "hello world"

    def test_multiple_includes_same_line(self):
        lines_map = {"_x": ["X"], "_y": ["Y"]}
        result = _expand_includes("{include:_x} and {_y}", lines_map, {})
        assert result == "X and Y"

    def test_hyphenated_key_via_explicit_syntax(self):
        lines_map = {"_my-frag": ["Hyphenated."]}
        result = _expand_includes("{include:_my-frag}", lines_map, {})
        assert result == "Hyphenated."


class TestPickIntegration:
    """Integration tests: pick() with includes and conditionals end-to-end."""

    def setup_method(self):
        import ed_monitor.voicelines as vl
        vl._CACHE.clear()
        vl._CONFIG_DIR = Path("/nonexistent_test_dir")

    def teardown_method(self):
        import ed_monitor.voicelines as vl
        vl._CACHE.clear()
        vl._CONFIG_DIR = None

    def test_pick_with_conditional_true(self):
        import ed_monitor.voicelines as vl
        vl._CACHE["en"] = {
            "MyEvent": ['Scanned. WHEN {terra} IS TRUE THEN "Terraformable.";'],
        }
        result = vl.pick("MyEvent", lang="en", terra="Terraformable")
        assert result == "Scanned. Terraformable."

    def test_pick_with_conditional_false(self):
        import ed_monitor.voicelines as vl
        vl._CACHE["en"] = {
            "MyEvent": ['Scanned. WHEN {terra} IS TRUE THEN "Terraformable.";'],
        }
        result = vl.pick("MyEvent", lang="en", terra="")
        assert result == "Scanned. "

    def test_pick_with_include(self):
        import ed_monitor.voicelines as vl
        vl._CACHE["en"] = {
            "_hull_info": ["{hull} hull."],
            "MyEvent":    ["Status: {include:_hull_info}"],
        }
        result = vl.pick("MyEvent", lang="en", hull="80 percent")
        assert result == "Status: 80 percent hull."

    def test_pick_include_with_variable_in_fragment(self):
        import ed_monitor.voicelines as vl
        vl._CACHE["en"] = {
            "_summary": ["{system} has {bio_count} bio signals."],
            "FSSAllBodiesFound": ["Scan complete. {include:_summary}"],
        }
        result = vl.pick("FSSAllBodiesFound", lang="en", system="Colonia", bio_count="3")
        assert result == "Scan complete. Colonia has 3 bio signals."

    def test_fragment_keys_not_pickable_directly(self):
        import ed_monitor.voicelines as vl
        vl._CACHE["en"] = {"_greeting": ["Hello."]}
        assert vl.pick("_greeting", lang="en") is None

    def test_pick_unknown_variable_returns_empty_not_crash(self):
        import ed_monitor.voicelines as vl
        vl._CACHE["en"] = {"MyEvent": ["Value: {value_mapped}."]}
        # value_mapped not in kwargs — SafeDict returns ""
        result = vl.pick("MyEvent", lang="en")
        assert result == "Value: ."
