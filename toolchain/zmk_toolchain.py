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
from pathlib import Path

import yaml


REPO = Path(os.environ.get("ZMK_CONFIG_ROOT", "/workspace")).resolve()
REPO_LOCK = REPO / "toolchain/versions.env"
IMAGE_LOCK = Path(os.environ.get("ZMK_TOOLCHAIN_LOCK", "/opt/zmk-config-roba/versions.env"))
WORKSPACE = Path("/tmp/zmk-config-roba-workspace")
BUILD_ROOT = Path("/tmp/zmk-config-roba-build")
ARTIFACTS = REPO / "artifacts"
LOCK_KEYS = {
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
HEX40 = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]+")


class Error(RuntimeError):
    pass


def run(args: list[str], cwd: Path, capture: bool = False) -> str:
    print(f"+ (cd {cwd} && {shlex.join(args)})", flush=True)
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def clean(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)


def load_lock(path: Path) -> dict[str, str]:
    lock: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise Error(f"{path}:{number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        if not key or not value or key in lock:
            raise Error(f"{path}:{number}: invalid or duplicate key {key!r}")
        lock[key] = value
    return lock


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def files_sha(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda item: item.relative_to(REPO).as_posix()):
        relative = path.relative_to(REPO).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def source_files() -> list[Path]:
    output = run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            "ls-files",
            "-co",
            "--exclude-standard",
            "-z",
        ],
        REPO,
        capture=True,
    )
    excluded = ("artifacts/", "keymap-drawer/")
    return [
        REPO / name
        for name in output.split("\0")
        if name and not name.startswith(excluded) and (REPO / name).is_file()
    ]


def verify(lock: dict[str, str]) -> None:
    if set(lock) != LOCK_KEYS:
        raise Error(f"lock keys differ: expected {sorted(LOCK_KEYS)}, got {sorted(lock)}")
    if not re.fullmatch(
        r"docker\.io/zmkfirmware/zmk-build-arm@sha256:[0-9a-f]{64}",
        lock["ZMK_BASE_IMAGE"],
    ):
        raise Error("ZMK_BASE_IMAGE must be the official image at an immutable digest")
    for key in ("ZMK_REVISION", "ZEPHYR_REVISION", "PMW3610_REVISION"):
        if not HEX40.fullmatch(lock[key]):
            raise Error(f"{key} must be an exact commit")
    for key in ("ZEPHYR_VERSION", "ZEPHYR_SDK_VERSION", "KEYMAP_DRAWER_VERSION", "PIP_VERSION"):
        if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", lock[key]):
            raise Error(f"{key} must be an exact version")
    if not re.fullmatch(r"[0-9a-f]{64}", lock["PIP_WHEEL_SHA256"]):
        raise Error("PIP_WHEEL_SHA256 must be exact")

    if not IMAGE_LOCK.is_file() or IMAGE_LOCK.read_bytes() != REPO_LOCK.read_bytes():
        raise Error("the checked-out lock and image-embedded lock differ")

    west = yaml.safe_load((REPO / "config/west.yml").read_text(encoding="utf-8"))
    revisions = {item["name"]: item["revision"] for item in west["manifest"]["projects"]}
    expected = {
        "zmk": lock["ZMK_REVISION"],
        "zmk-pmw3610-driver": lock["PMW3610_REVISION"],
    }
    if any(revisions.get(name) != revision for name, revision in expected.items()):
        raise Error(f"config/west.yml does not match the root project locks: {expected}")

    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    required_docker_text = (
        f"FROM {lock['ZMK_BASE_IMAGE']}",
        f"pip-{lock['PIP_VERSION']}-py3-none-any.whl",
        lock["PIP_WHEEL_SHA256"],
    )
    if any(value not in dockerfile for value in required_docker_text):
        raise Error("Dockerfile does not match versions.env")

    requirements = (REPO / "toolchain/keymap-drawer-requirements.txt").read_text(encoding="utf-8")
    logical = requirements.replace("\\\n", " ")
    pins = re.findall(r"(?m)^([A-Za-z0-9_.-]+)==([^\s]+)([^\n]*)", logical)
    if not pins or any("--hash=sha256:" not in tail for _, _, tail in pins):
        raise Error("every keymap-drawer package must have an exact version and hash")
    versions = {name.lower(): version for name, version, _ in pins}
    if versions.get("keymap-drawer") != lock["KEYMAP_DRAWER_VERSION"]:
        raise Error("keymap-drawer package and environment lock differ")

    build_workflow = (REPO / ".github/workflows/build.yml").read_text(encoding="utf-8")
    draw_workflow = (REPO / ".github/workflows/draw.yml").read_text(encoding="utf-8")
    if "zmkfirmware/zmk/.github/workflows/build-user-config.yml" in build_workflow:
        raise Error("the mutable upstream build workflow remains authoritative")
    for command in ("./scripts/zmk-env repeat", "./scripts/zmk-env draw"):
        if command not in build_workflow:
            raise Error(f"CI does not run {command}")
    if "./scripts/zmk-env draw" not in draw_workflow:
        raise Error("manual and CI drawing commands differ")
    build_matrix()

    if not HEX40.fullmatch(os.environ.get("SOURCE_REVISION", "")):
        raise Error("SOURCE_REVISION must be the checked-out commit")
    if not IMAGE_ID.fullmatch(os.environ.get("TOOLCHAIN_IMAGE_ID", "")):
        raise Error("TOOLCHAIN_IMAGE_ID must be the built image ID")
    if sys.version_info[:2] != (3, 12):
        raise Error(f"expected Python 3.12, got {sys.version.split()[0]}")
    if importlib.metadata.version("keymap-drawer") != lock["KEYMAP_DRAWER_VERSION"]:
        raise Error("keymap-drawer runtime and lock differ")
    if os.environ.get("ZEPHYR_VERSION") != lock["ZEPHYR_VERSION"]:
        raise Error("base image Zephyr version and lock differ")
    if os.environ.get("ZEPHYR_SDK_VERSION") != lock["ZEPHYR_SDK_VERSION"]:
        raise Error("base image Zephyr SDK version and lock differ")

    print("Issue #164 environment checks passed.")


def prepare(lock: dict[str, str]) -> str:
    clean(WORKSPACE)
    shutil.copytree(REPO / "config", WORKSPACE / "config")
    run(["west", "init", "-l", str(WORKSPACE / "config")], WORKSPACE)
    run(["west", "update", "--fetch-opt=--filter=tree:0"], WORKSPACE)
    run(["west", "zephyr-export"], WORKSPACE)

    expected = {
        "zmk": lock["ZMK_REVISION"],
        "zephyr": lock["ZEPHYR_REVISION"],
        "zmk-pmw3610-driver": lock["PMW3610_REVISION"],
    }
    for project, revision in expected.items():
        actual = run(["git", "rev-parse", "HEAD"], WORKSPACE / project, capture=True).strip()
        if actual != revision:
            raise Error(f"resolved {project}@{actual}, expected {revision}")

    frozen = run(["west", "manifest", "--freeze"], WORKSPACE, capture=True)
    return frozen if frozen.endswith("\n") else frozen + "\n"


def build_matrix() -> list[dict[str, str]]:
    document = yaml.safe_load((REPO / "build.yaml").read_text(encoding="utf-8"))
    entries = document.get("include") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        raise Error("build.yaml must contain a non-empty include list")

    allowed = {"board", "shield", "snippet", "cmake-args", "artifact-name"}
    matrix: list[dict[str, str]] = []
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) - allowed or not isinstance(raw.get("board"), str):
            raise Error(f"unsupported build entry: {raw!r}")
        entry = {str(key): str(value) for key, value in raw.items()}
        entry["artifact-name"] = entry.get("artifact-name") or (
            f"{entry.get('shield') + '-' if entry.get('shield') else ''}{entry['board']}-zmk"
        )
        if not SAFE_NAME.fullmatch(entry["artifact-name"]):
            raise Error(f"unsafe artifact name: {entry['artifact-name']}")
        matrix.append(entry)
    return matrix


def receipt(lock: dict[str, str], kind: str, frozen: str, artifacts: list[tuple[str, Path]]) -> dict:
    config_files = [path for path in (REPO / "config").rglob("*") if path.is_file()]
    oci_files = [
        REPO / "Dockerfile",
        REPO / ".dockerignore",
        REPO / "toolchain/versions.env",
        REPO / "toolchain/keymap-drawer-requirements.txt",
    ]
    inputs = {
        "source_tree_sha256": files_sha(source_files()),
        "build_matrix_sha256": file_sha(REPO / "build.yaml"),
        "config_tree_sha256": files_sha(config_files),
        "oci_definition_sha256": files_sha(oci_files),
        "west_manifest_sha256": sha(frozen.encode()),
    }
    environment = {
        **lock,
        "TOOLCHAIN_IMAGE_ID": os.environ["TOOLCHAIN_IMAGE_ID"],
        "PYTHON_VERSION": sys.version.split()[0],
    }
    identity = {
        "schema": 1,
        "source": {"revision": os.environ["SOURCE_REVISION"]},
        "environment": environment,
        "inputs": inputs,
    }
    identity["input_identity_sha256"] = sha(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    )
    identity["kind"] = kind
    identity["artifacts"] = [
        {"path": name, "sha256": file_sha(path), "size": path.stat().st_size}
        for name, path in sorted(artifacts)
    ]
    return identity


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_to(lock: dict[str, str], output: Path) -> dict:
    frozen = prepare(lock)
    clean(BUILD_ROOT)
    clean(output)
    products: list[tuple[str, Path]] = []

    for entry in build_matrix():
        name = entry["artifact-name"]
        build_dir = BUILD_ROOT / name
        command = [
            "west",
            "build",
            "-s",
            str(WORKSPACE / "zmk/app"),
            "-d",
            str(build_dir),
            "-b",
            entry["board"],
        ]
        if entry.get("snippet"):
            command += ["-S", entry["snippet"]]
        command += [
            "--",
            f"-DZMK_CONFIG={WORKSPACE / 'config'}",
            f"-DZMK_EXTRA_MODULES={REPO}",
        ]
        if entry.get("shield"):
            command += [f"-DSHIELD={entry['shield']}"]
        if entry.get("cmake-args"):
            command += shlex.split(entry["cmake-args"])
        run(command, WORKSPACE)

        binaries = [
            build_dir / "zephyr/zmk.uf2",
            build_dir / "zephyr/zmk.bin",
        ]
        built = next((path for path in binaries if path.is_file()), None)
        if built is None:
            raise Error(f"{name}: no zmk.uf2 or zmk.bin was produced")
        destination = output / f"{name}{built.suffix}"
        shutil.copyfile(built, destination)
        products.append((f"firmware/{destination.name}", destination))

    manifest = output / "west-manifest.lock.yml"
    manifest.write_text(frozen, encoding="utf-8")
    result = receipt(lock, "firmware", frozen, products + [("west-manifest.lock.yml", manifest)])
    write_json(output / "provenance.json", result)
    return result


def draw(lock: dict[str, str]) -> None:
    frozen = prepare(lock)
    temporary = Path("/tmp/zmk-config-roba-keymap")
    clean(temporary)

    yaml_text = run(
        [
            sys.executable,
            "-m",
            "keymap_drawer",
            "parse",
            "-z",
            str(WORKSPACE / "config/roBa.keymap"),
        ],
        WORKSPACE,
        capture=True,
    )
    generated_yaml = temporary / "roBa.yaml"
    generated_yaml.write_text(yaml_text, encoding="utf-8")
    svg_text = run(
        [
            sys.executable,
            "-m",
            "keymap_drawer",
            "draw",
            str(generated_yaml),
            "-j",
            str(WORKSPACE / "config/roBa.json"),
        ],
        WORKSPACE,
        capture=True,
    )
    generated_svg = temporary / "roBa.svg"
    generated_svg.write_text(svg_text, encoding="utf-8")

    target = REPO / "keymap-drawer"
    target.mkdir(parents=True, exist_ok=True)
    final_yaml, final_svg = target / "roBa.yaml", target / "roBa.svg"
    shutil.copyfile(generated_yaml, final_yaml)
    shutil.copyfile(generated_svg, final_svg)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    manifest = ARTIFACTS / "keymap-west-manifest.lock.yml"
    manifest.write_text(frozen, encoding="utf-8")
    result = receipt(
        lock,
        "keymap",
        frozen,
        [
            ("keymap-drawer/roBa.svg", final_svg),
            ("keymap-drawer/roBa.yaml", final_yaml),
            ("keymap-west-manifest.lock.yml", manifest),
        ],
    )
    write_json(ARTIFACTS / "keymap-provenance.json", result)


def artifact_hashes(result: dict) -> dict[str, str]:
    return {item["path"]: item["sha256"] for item in result["artifacts"]}


def repeat(lock: dict[str, str]) -> None:
    first_dir = Path("/tmp/zmk-config-roba-repeat-first")
    second_dir = Path("/tmp/zmk-config-roba-repeat-second")
    first, second = build_to(lock, first_dir), build_to(lock, second_dir)
    first_hashes, second_hashes = artifact_hashes(first), artifact_hashes(second)
    names = sorted(set(first_hashes) | set(second_hashes))
    differences = [
        {
            "path": name,
            "first_sha256": first_hashes.get(name),
            "second_sha256": second_hashes.get(name),
        }
        for name in names
        if first_hashes.get(name) != second_hashes.get(name)
    ]
    report = {
        "schema": 1,
        "source_revision": os.environ["SOURCE_REVISION"],
        "toolchain_image_id": os.environ["TOOLCHAIN_IMAGE_ID"],
        "first_input_identity_sha256": first["input_identity_sha256"],
        "second_input_identity_sha256": second["input_identity_sha256"],
        "identical_inputs": first["input_identity_sha256"] == second["input_identity_sha256"],
        "identical_artifacts": not differences,
        "differences": differences,
    }

    final = ARTIFACTS / "firmware"
    shutil.rmtree(final, ignore_errors=True)
    shutil.copytree(first_dir, final)
    write_json(ARTIFACTS / "repeat-build.json", report)
    if not report["identical_inputs"]:
        raise Error("repeat build resolved different source/toolchain inputs")
    if differences:
        raise Error("repeat build produced different artifact identities")
    print("Repeat build input and artifact identities are identical.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "build", "draw", "repeat"))
    args = parser.parse_args()
    try:
        lock = load_lock(REPO_LOCK)
        verify(lock)
        if args.command == "build":
            build_to(lock, ARTIFACTS / "firmware")
        elif args.command == "draw":
            draw(lock)
        elif args.command == "repeat":
            repeat(lock)
        return 0
    except (Error, KeyError, OSError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
