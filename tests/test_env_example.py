from pathlib import Path

from scripts.update_env_example import generate_env_example


def test_env_example_is_current():
    project_root = Path(__file__).resolve().parents[1]
    env_example_path = project_root / ".env.example"
    expected_content = generate_env_example()
    actual_content = env_example_path.read_text()
    assert (
        actual_content == expected_content
    ), ".env.example is out of sync with settings. Run scripts/update_env_example.py to regenerate."
