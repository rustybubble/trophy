"""Spacetime 2.13's SQL API names columns as options; the house-rule read-back must unwrap them (seen at the demo)."""

from __future__ import annotations

from trophy_engine.state import sql_column_names


def test_option_names_are_unwrapped():
    schema = {
        "elements": [
            {"name": {"some": "rule_version"}, "algebraic_type": {"String": []}},
            {"name": {"none": []}, "algebraic_type": {"F64": []}},
            {"name": "json", "algebraic_type": {"String": []}},
        ]
    }
    assert sql_column_names(schema) == ["rule_version", "col1", "json"]


def test_empty_schema():
    assert sql_column_names({}) == []
