#!/usr/bin/env python3
"""Pinned ZMK build/draw entrypoint for project_template Issue #164."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import yaml


REPO = Path(os.environ.get("ZMK_CONFIG_ROOT", "/workspace")).resolve()
REPO_LOCK = REPO / "toolchain" / "versions.env"
IMAGE_LOCK = Path(os.environ.get("ZMK_TOOLCHAIN_LOCK", "/opt/zmk-config-roba/versions.env"))
WORKSPACE = Path("/tmp/zmk-config-roba-workspace")
BUILD_ROOT = Path("/tmp/zmk-config-roba-build")
ARTIFACT_ROOT = REPO / "artifacts"

REQUIRED_LOCK_KEYS = {
    "ZMK_BASE_IMAGE",
    "ZMK_REVISION",
    "ZEPHYR_REVISION",
    "ZEPHYR_VERSION",
    "ZEPHYR_SDK_VERSION",
    "PMW3610_REVISION",
    "KEYMAP_DRAWER_VERSION",
    "PIP_VERSION",
    "PIP_WHEEL_SHA256",
}
SOURCE_INPUTS = (
    Path(".dockerignore"),
    Path(".gitignore"),
    Path("Dockerfile"),
    Path("README.md"),
    Path("build.yaml"),
    Path(".github/workflows"),
    Path("boards"),
    Path("config"),
    Path("scripts"),
    Path("toolchain"),
    Path("zephyr"),
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class ToolchainError(RuntimeError):
    """A user-actionable environment or reproducibility failure."""


@dataclass(frozen=True)
class BuildResult:
    output_dir: Path
    receipt: dict[str, object]
    artifact_hashes: dict[str, str]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ToolchainError(f"{path}:{number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        if not key or not value or key in values:
            raise ToolchainError(f"{path}:{number}: invalid or duplicate key {key!r}")
        values[key] = value
    return values


def run(
    args: Sequence[str],
    *,
    cwd: Path,
    capture: bool = False,
) -> str:
    print(f"+ (cd {cwd} && {shlex.join(args)})", flush=True)
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return completed.stdout if capture else ""


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_input_files(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    for relative in paths:
        candidate = REPO / relative
        if candidate.is_file():
            result.append(candidate)
        elif candidate.is_dir():
            result.extend(
                path
                for path in candidate.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            )
        else:
            raise ToolchainError(f"declared source input is missing: {relative}")
    return sorted(set(result), key=lambda path: path.relative_to(REPO).as_posix())


def digest_inputs(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in iter_input_files(paths):
        relative = path.relative_to(REPO).as_posix().encode("utf-8")
        contents = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
    return digest.hexdigest()


def logical_requirements(text: str) -> list[str]:
    logical: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            current += line[:-1].strip() + " "
            continue
        logical.append((current + line).strip())
        current = ""
    if current:
        raise ToolchainError("unterminated continuation in keymap-drawer requirements")
    return logical


def verify_static(lock: dict[str, str]) -> None:
    missing = REQUIRED_LOCK_KEYS - lock.keys()
    extra = lock.keys() - REQUIRED_LOCK_KEYS
    if missing or extra:
        raise ToolchainError(f"lock key mismatch: missing={sorted(missing)}, extra={sorted(extra)}")

    if not re.fullmatch(
        r"docker\.io/zmkfirmware/zmk-build-arm@sha256:[0-9a-f]{64}",
        lock["ZMK_BASE_IMAGE"],
    ):
        raise ToolchainError("ZMK_BASE_IMAGE must be the official image at an immutable digest")
    for key in ("ZMK_REVISION", "ZEPHYR_REVISION", "PMW3610_REVISION"):
        if not HEX40.fullmatch(lock[key]):
            raise ToolchainError(f"{key} must be an exact 40-hex commit")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", lock["ZEPHYR_SDK_VERSION"]):
        raise ToolchainError("ZEPHYR_SDK_VERSION must be exact")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", lock["KEYMAP_DRAWER_VERSION"]):
        raise ToolchainError("KEYMAP_DRAWER_VERSION must be exact")
    if not re.fullmatch(r"[0-9a-f]{64}", lock["PIP_WHEEL_SHA256"]):
        raise ToolchainError("PIP_WHEEL_SHA256 must be an exact digest")

    if IMAGE_LOCK.exists() and IMAGE_LOCK.read_bytes() != REPO_LOCK.read_bytes():
        raise ToolchainError("the checked-out lock and the lock embedded in the image differ")

    west = yaml.safe_load((REPO / "config" / "west.yml").read_text(encoding="utf-8"))
    projects = {project["name"]: project for project in west["manifest"]["projects"]}
    expected_projects = {
        "zmk": lock["ZMK_REVISION"],
        "zmk-pmw3610-driver": lock["PMW3610_REVISION"],
    }
    for name, revision in expected_projects.items():
        actual = projects.get(name, {}).get("revision")
        if actual != revision:
            raise ToolchainError(f"config/west.yml has {name}@{actual}, expected {revision}")

    matrix = yaml.safe_load((REPO / "build.yaml").read_text(encoding="utf-8"))
    entries = matrix.get("include") if isinstance(matrix, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ToolchainError("build.yaml must contain a non-empty include matrix")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("board"), str):
            raise ToolchainError("each build matrix entry must contain a string board")

    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    expected_from = f"FROM {lock['ZMK_BASE_IMAGE']}"
    if expected_from not in dockerfile:
        raise ToolchainError("Dockerfile base image does not match versions.env")
    if f"pip-{lock['PIP_VERSION']}-py3-none-any.whl" not in dockerfile:
        raise ToolchainError("Dockerfile pip bootstrap version does not match versions.env")
    if lock["PIP_WHEEL_SHA256"] not in dockerfile:
        raise ToolchainError("Dockerfile pip wheel digest does not match versions.env")

    requirements = logical_requirements(
        (REPO / "toolchain" / "keymap-drawer-requirements.txt").read_text(encoding="utf-8")
    )
    pinned: dict[str, str] = {}
    for requirement in requirements:
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s]+)\s+(.+)$", requirement)
        if not match or "--hash=sha256:" not in match.group(3):
            raise ToolchainError(f"unlocked keymap-drawer requirement: {requirement}")
        pinned[match.group(1).lower()] = match.group(2)
    if pinned.get("keymap-drawer") != lock["KEYMAP_DRAWER_VERSION"]:
        raise ToolchainError("keymap-drawer requirement does not match versions.env")

    build_workflow = (REPO / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    draw_workflow = (REPO / ".github" / "workflows" / "draw.yml").read_text(encoding="utf-8")
    if "zmkfirmware/zmk/.github/workflows/build-user-config.yml" in build_workflow:
        raise ToolchainError("mutable upstream build workflow remains authoritative")
    if "./scripts/zmk-env repeat" not in build_workflow:
        raise ToolchainError("CI does not use the local repeat-build entrypoint")
    if "./scripts/zmk-env draw" not in build_workflow or "./scripts/zmk-env draw" not in draw_workflow:
        raise ToolchainError("local and CI keymap drawing entrypoints differ")

    source_revision = os.environ.get("SOURCE_REVISION", "")
    image_id = os.environ.get("TOOLCHAIN_IMAGE_ID", "")
    if not HEX40.fullmatch(source_revision):
        raise ToolchainError("SOURCE_REVISION must be the exact checked-out commit")
    if not SHA256.fullmatch(image_id):
        raise ToolchainError("TOOLCHAIN_IMAGE_ID must be the built image ID")

    if sys.version_info[:2] != (3, 12):
        raise ToolchainError(f"expected Python 3.12, got {sys.version.split()[0]}")
    actual_drawer = importlib.metadata.version("keymap-drawer")
    if actual_drawer != lock["KEYMAP_DRAWER_VERSION"]:
        raise ToolchainError(
            f"keymap-drawer runtime is {actual_drawer}, expected {lock['KEYMAP_DRAWER_VERSION']}"
        )
    if os.environ.get("ZEPHYR_VERSION") != lock["ZEPHYR_VERSION"]:
        raise ToolchainError("base image Zephyr version does not match versions.env")
    if os.environ.get("ZEPHYR_SDK_VERSION") != lock["ZEPHYR_SDK_VERSION"]:
        raise ToolchainError("base image Zephyr SDK version does not match versions.env")

    print("Issue #164 static environment checks passed.")


def prepare_workspace(lock: dict[str, str]) -> str:
    reset_directory(WORKSPACE)
    shutil.copytree(REPO / "config", WORKSPACE / "config")

    run(["west", "init", "-l", str(WORKSPACE / "config")], cwd=WORKSPACE)
    run(["west", "update", "--fetch-opt=--filter=tree:0"], cwd=WORKSPACE)
    run(["west", "zephyr-export"], cwd=WORKSPACE)

    expected = {
        "zmk": lock["ZMK_REVISION"],
        "zephyr": lock["ZEPHYR_REVISION"],
        "zmk-pmw3610-driver": lock["PMW3610_REVISION"],
    }
    for project, revision in expected.items():
        checkout = WORKSPACE / project
        actual = run(["git", "rev-parse", "HEAD"], cwd=checkout, capture=True).strip()
        if actual != revision:
            raise ToolchainError(f"resolved {project}@{actual}, expected {revision}")

    frozen = run(["west", "manifest", "--freeze"], cwd=WORKSPACE, capture=True)
    if not frozen.endswith("\n"):
        frozen += "\n"
    return frozen


def load_build_matrix() -> list[dict[str, str]]:
    document = yaml.safe_load((REPO / "build.yaml").read_text(encoding="utf-8"))
    entries = document["include"]
    result: list[dict[str, str]] = []
    allowed = {"board", "shield", "snippet", "cmake-args", "artifact-name"}
    for raw_entry in entries:
        unknown = set(raw_entry) - allowed
        if unknown:
            raise ToolchainError(f"unsupported build matrix fields: {sorted(unknown)}")
        entry = {str(key): str(value) for key, value in raw_entry.items()}
        name = entry.get("artifact-name") or (
            f"{entry.get('shield') + '-' if entry.get('shield') else ''}{entry['board']}-zmk"
        )
        if not SAFE_NAME.fullmatch(name):
            raise ToolchainError(f"unsafe artifact name: {name!r}")
        entry["artifact-name"] = name
        result.append(entry)
    return result


def source_identity(lock: dict[str, str], frozen_manifest: str) -> dict[str, object]:
    source_revision = os.environ["SOURCE_REVISION"]
    image_id = os.environ["TOOLCHAIN_IMAGE_ID"]
    inputs = {
        "source_tree_sha256": digest_inputs(SOURCE_INPUTS),
        "build_matrix_sha256": sha256_file(REPO / "build.yaml"),
        "config_tree_sha256": digest_inputs((Path("config"),)),
        "oci_definition_sha256": digest_inputs(
            (
                Path("Dockerfile"),
                Path(".dockerignore"),
                Path("toolchain/versions.env"),
                Path("toolchain/keymap-drawer-requirements.txt"),
            )
        ),
        "west_manifest_sha256": sha256_bytes(frozen_manifest.encode("utf-8")),
    }
    environment = {
        **lock,
        "TOOLCHAIN_IMAGE_ID": image_id,
        "PYTHON_VERSION": sys.version.split()[0],
    }
    identity_payload = {
        "schema": 1,
        "source": {"revision": source_revision},
        "environment": environment,
        "inputs": inputs,
    }
    encoded = json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **identity_payload,
        "input_identity_sha256": sha256_bytes(encoded),
    }


def artifact_record(logical_path: str, path: Path) -> dict[str, object]:
    return {
        "path": logical_path,
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_receipt(
    kind: str,
    lock: dict[str, str],
    frozen_manifest: str,
    artifacts: Sequence[tuple[str, Path]],
) -> dict[str, object]:
    identity = source_identity(lock, frozen_manifest)
    return {
        **identity,
        "kind": kind,
        "artifacts": [
            artifact_record(logical_path, path)
            for logical_path, path in sorted(artifacts, key=lambda item: item[0])
        ],
    }


def build_firmware(lock: dict[str, str], output_dir: Path) -> BuildResult:
    frozen = prepare_workspace(lock)
    reset_directory(BUILD_ROOT)
    reset_directory(output_dir)

    binaries: list[tuple[str, Path]] = []
    for entry in load_build_matrix():
        board = entry["board"]
        shield = entry.get("shield")
        snippet = entry.get("snippet")
        artifact_name = entry["artifact-name"]
        build_dir = BUILD_ROOT / artifact_name

        command = [
            "west",
            "build",
            "-s",
            str(WORKSPACE / "zmk" / "app"),
            "-d",
            str(build_dir),
            "-b",
            board,
        ]
        if snippet:
            command.extend(["-S", snippet])
        command.extend(
            [
                "--",
                f"-DZMK_CONFIG={WORKSPACE / 'config'}",
                f"-DZMK_EXTRA_MODULES={REPO}",
            ]
        )
        if shield:
            command.append(f"-DSHIELD={shield}")
        if entry.get("cmake-args"):
            command.extend(shlex.split(entry["cmake-args"]))

        run(command, cwd=WORKSPACE)

        built = None
        for suffix in (".uf2", ".bin"):
            candidate = build_dir / "zephyr" / f"zmk{suffix}"
            if candidate.is_file():
                built = candidate
                break
        if built is None:
            raise ToolchainError(f"{artifact_name}: no zmk.uf2 or zmk.bin was produced")

        destination = output_dir / f"{artifact_name}{built.suffix}"
        shutil.copyfile(built, destination)
        binaries.append((f"firmware/{destination.name}", destination))

    manifest_path = output_dir / "west-manifest.lock.yml"
    manifest_path.write_text(frozen, encoding="utf-8")
    artifacts = [*binaries, ("west-manifest.lock.yml", manifest_path)]
    receipt = create_receipt("firmware", lock, frozen, artifacts)
    write_json(output_dir / "provenance.json", receipt)
    hashes = {
        str(record["path"]): str(record["sha256"])
        for record in receipt["artifacts"]  # type: ignore[index]
    }
    return BuildResult(output_dir=output_dir, receipt=receipt, artifact_hashes=hashes)


def draw_keymap(lock: dict[str, str]) -> None:
    frozen = prepare_workspace(lock)
    generated = Path("/tmp/zmk-config-roba-keymap")
    reset_directory(generated)

    keymap_source = WORKSPACE / "config" / "roBa.keymap"
    layout_json = WORKSPACE / "config" / "roBa.json"
    yaml_text = run(
        [sys.executable, "-m", "keymap_drawer", "parse", "-z", str(keymap_source)],
        cwd=WORKSPACE,
        capture=True,
    )
    generated_yaml = generated / "roBa.yaml"
    generated_yaml.write_text(yaml_text, encoding="utf-8")

    svg_text = run(
        [
            sys.executable,
            "-m",
            "keymap_drawer",
            "draw",
            str(generated_yaml),
            "-j",
            str(layout_json),
        ],
        cwd=WORKSPACE,
        capture=True,
    )
    generated_svg = generated / "roBa.svg"
    generated_svg.write_text(svg_text, encoding="utf-8")

    destination = REPO / "keymap-drawer"
    destination.mkdir(parents=True, exist_ok=True)
    final_yaml = destination / "roBa.yaml"
    final_svg = destination / "roBa.svg"
    shutil.copyfile(generated_yaml, final_yaml)
    shutil.copyfile(generated_svg, final_svg)

    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ARTIFACT_ROOT / "keymap-west-manifest.lock.yml"
    manifest_path.write_text(frozen, encoding="utf-8")
    receipt = create_receipt(
        "keymap",
        lock,
        frozen,
        (
            ("keymap-drawer/roBa.svg", final_svg),
            ("keymap-drawer/roBa.yaml", final_yaml),
            ("keymap-west-manifest.lock.yml", manifest_path),
        ),
    )
    write_json(ARTIFACT_ROOT / "keymap-provenance.json", receipt)


def compare_builds(first: BuildResult, second: BuildResult) -> dict[str, object]:
    first_identity = str(first.receipt["input_identity_sha256"])
    second_identity = str(second.receipt["input_identity_sha256"])
    names = sorted(set(first.artifact_hashes) | set(second.artifact_hashes))
    differences = [
        {
            "path": name,
            "first_sha256": first.artifact_hashes.get(name),
            "second_sha256": second.artifact_hashes.get(name),
        }
        for name in names
        if first.artifact_hashes.get(name) != second.artifact_hashes.get(name)
    ]
    return {
        "schema": 1,
        "source_revision": os.environ["SOURCE_REVISION"],
        "toolchain_image_id": os.environ["TOOLCHAIN_IMAGE_ID"],
        "first_input_identity_sha256": first_identity,
        "second_input_identity_sha256": second_identity,
        "identical_inputs": first_identity == second_identity,
        "identical_artifacts": not differences,
        "differences": differences,
    }


def command_build(lock: dict[str, str]) -> None:
    build_firmware(lock, ARTIFACT_ROOT / "firmware")


def command_repeat(lock: dict[str, str]) -> None:
    first_dir = Path("/tmp/zmk-config-roba-repeat-first")
    second_dir = Path("/tmp/zmk-config-roba-repeat-second")
    first = build_firmware(lock, first_dir)
    second = build_firmware(lock, second_dir)
    report = compare_builds(first, second)

    final_dir = ARTIFACT_ROOT / "firmware"
    reset_directory(final_dir)
    for source in first_dir.iterdir():
        if source.is_file():
            shutil.copyfile(source, final_dir / source.name)
    write_json(ARTIFACT_ROOT / "repeat-build.json", report)

    if not report["identical_inputs"]:
        raise ToolchainError("repeat build resolved different source/toolchain inputs")
    if not report["identical_artifacts"]:
        raise ToolchainError("repeat build produced different artifact identities")
    print("Repeat build input and artifact identities are identical.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "build", "draw", "repeat"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        lock = load_env(REPO_LOCK)
        verify_static(lock)
        if args.command == "build":
            command_build(lock)
        elif args.command == "draw":
            draw_keymap(lock)
        elif args.command == "repeat":
            command_repeat(lock)
        return 0
    except (ToolchainError, KeyError, OSError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
