"""The input contract must reject bad data loudly, with a message that names the field."""

import copy

import pytest

import figure_core
from helpers import BAR_SPEC, LINE_SPEC


def spec_error(spec):
    with pytest.raises(figure_core.SpecError) as excinfo:
        figure_core.validate_spec(spec)
    return str(excinfo.value)


def mutate(base, **changes):
    spec = copy.deepcopy(base)
    spec.update(changes)
    return spec


def test_valid_specs_round_trip():
    assert figure_core.validate_spec(copy.deepcopy(LINE_SPEC))["kind"] == "line"
    assert figure_core.validate_spec(copy.deepcopy(BAR_SPEC))["kind"] == "bar"


def test_input_order_is_preserved():
    spec = mutate(LINE_SPEC, x=[3, 1, 2, 0])
    assert figure_core.validate_spec(spec)["x"] == [3.0, 1.0, 2.0, 0.0]

    spec = mutate(BAR_SPEC, categories=["z", "a", "m"], values=[3.0, 1.0, 2.0])
    normalised = figure_core.validate_spec(spec)
    assert normalised["categories"] == ["z", "a", "m"]
    assert normalised["values"] == [3.0, 1.0, 2.0]


def test_unknown_kind_is_rejected_by_name():
    message = spec_error(mutate(LINE_SPEC, kind="histogram"))
    assert "histogram" in message and "kind" in message


def test_wrong_schema_version_is_rejected():
    assert "schema_version" in spec_error(mutate(LINE_SPEC, schema_version="2"))


def test_unknown_field_is_rejected_not_ignored():
    spec = copy.deepcopy(LINE_SPEC)
    spec["y_lable"] = "typo"
    message = spec_error(spec)
    assert "y_lable" in message


def test_unknown_field_inside_a_series_is_rejected():
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"][0]["colour"] = "#000000"
    assert "colour" in spec_error(spec)


def test_missing_required_field():
    spec = copy.deepcopy(LINE_SPEC)
    del spec["y_label"]
    assert "y_label" in spec_error(spec)


@pytest.mark.parametrize("empty", [[], None])
def test_empty_line_data_is_rejected(empty):
    assert "spec.x" in spec_error(mutate(LINE_SPEC, x=empty))


def test_empty_series_list_is_rejected():
    assert "series" in spec_error(mutate(LINE_SPEC, series=[]))


def test_length_mismatch_is_rejected_with_both_lengths():
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"][0]["y"] = [1.0, 2.0]
    message = spec_error(spec)
    assert "2" in message and "4" in message


def test_bar_length_mismatch_is_rejected():
    assert "values" in spec_error(mutate(BAR_SPEC, values=[1.0, 2.0]))


def test_non_numeric_value_is_rejected():
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"][0]["y"] = [1.0, "2.0", 3.0, 4.0]
    message = spec_error(spec)
    assert "series[0].y[1]" in message


def test_booleans_are_not_numbers():
    spec = copy.deepcopy(BAR_SPEC)
    spec["values"] = [True, 1.0, 2.0]
    assert "values[0]" in spec_error(spec)


def test_non_finite_value_is_rejected():
    spec = copy.deepcopy(BAR_SPEC)
    spec["values"] = [float("nan"), 1.0, 2.0]
    assert "finite" in spec_error(spec)


def test_json_nan_literal_is_rejected_at_load(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text('{"schema_version": "1", "kind": "bar", "x_label": "a", '
                    '"y_label": "b", "categories": ["a"], "values": [NaN]}')
    with pytest.raises(figure_core.SpecError) as excinfo:
        figure_core.load_spec(str(path))
    assert "NaN" in str(excinfo.value)


def test_duplicate_series_names_are_rejected():
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"].append({"name": "a", "y": [4.0, 3.0, 2.0, 1.0]})
    assert "unique" in spec_error(spec)


def test_duplicate_bar_categories_are_rejected():
    spec = mutate(BAR_SPEC, categories=["a", "a", "c"])
    assert "unique" in spec_error(spec)


def test_malformed_json_names_the_file(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    with pytest.raises(figure_core.SpecError) as excinfo:
        figure_core.load_spec(str(path))
    assert "broken.json" in str(excinfo.value)


def test_missing_file_is_reported():
    with pytest.raises(figure_core.SpecError) as excinfo:
        figure_core.load_spec("/nonexistent/spec.json")
    assert "not found" in str(excinfo.value)
