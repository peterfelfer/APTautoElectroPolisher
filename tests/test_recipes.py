from pathlib import Path

import yaml

from apt_polisher.recipes import RecipeLoader, list_recipes, load_recipe, RecipeConfigError


def test_list_recipes_includes_default(tmp_path: Path, monkeypatch):
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()
    (recipes_dir / "example.yml").write_text("metadata:\n  description: test\nmotion:\n  safe_z_mm: 10\n  pickup_macro: pick\n  place_macro: place\npolishing:\n  waveform:\n    amplitude_mm: 0.2\n    period_s: 1.0\n    center_z_mm: 0.0\n  contact:\n    approach_speed_mm_s: 1\n    detection_current_ma: 5\n    max_depth_mm: 1\n")

    monkeypatch.setattr("apt_polisher.recipes.loader.find_project_root", lambda: tmp_path)
    loader = RecipeLoader()
    recipes = loader.list()
    assert "example" in recipes


def test_load_recipe(tmp_path: Path, monkeypatch):
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()
    recipe_path = recipes_dir / "sample.yml"
    recipe_path.write_text(
        """
metadata:
  description: Sample recipe
motion:
  safe_z_mm: 30
  pickup_macro: pick
  place_macro: place
motion_macros:
  pick:
    file: pick.gcode
polishing:
  waveform:
    amplitude_mm: 0.4
    period_s: 1.5
    center_z_mm: -1.0
  contact:
    approach_speed_mm_s: 0.8
    detection_current_ma: 4.0
    max_depth_mm: 3.0
  cycle:
    mode: cycles
    max_cycles: 3
    duration_s: 45
  voltage_v: 9.5
  current_limit_a: 0.75
cleaning:
  rinse_cycles: 1
  dry_time_s: 3
imaging:
  thickness_threshold_um: 200
  inspect_interval_s: 90
        """
    )

    monkeypatch.setattr("apt_polisher.recipes.loader.find_project_root", lambda: tmp_path)
    recipe = load_recipe("sample")
    assert recipe.name == "sample"
    assert recipe.safe_z_mm == 30.0
    assert recipe.polishing_cycle.mode == "cycles"
    assert recipe.motion_macros["pick"].file == "pick.gcode"


def test_missing_recipe_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("apt_polisher.recipes.loader.find_project_root", lambda: tmp_path)
    loader = RecipeLoader()
    try:
        loader.load("missing")
    except RecipeConfigError:
        pass
    else:
        raise AssertionError("Expected RecipeConfigError for missing recipe")
