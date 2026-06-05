from pathlib import Path
import json
import subprocess


REPO_ROOT = Path("/opt/data/steadyplan")
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _docker_cmd() -> list[str]:
    for line in DOCKERFILE.read_text().splitlines():
        if line.startswith("CMD "):
            return json.loads(line.removeprefix("CMD "))
    raise AssertionError("Dockerfile CMD line not found")


def _extract_shell_command() -> str:
    cmd = _docker_cmd()
    assert cmd[:2] == ["sh", "-c"]
    return cmd[2]


def test_dockerfile_expands_forwarded_allow_ips_default_before_gunicorn_parses_it():
    shell_command = _extract_shell_command()

    rendered = subprocess.run(
        ["/bin/sh", "-c", f"printf '%s\\n' {shell_command}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "${FORWARDED_ALLOW_IPS:-127.0.0.1,::1}" not in rendered
    assert "--forwarded-allow-ips=127.0.0.1,::1" in rendered


def test_dockerfile_check_config_accepts_default_forwarded_allow_ips_value():
    shell_command = _extract_shell_command().replace("gunicorn ", "gunicorn --check-config ", 1)

    result = subprocess.run(
        ["/bin/sh", "-c", shell_command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
