import os
import re
import subprocess
import sys
from dataclasses import dataclass

import appdirs

VALID_ARTIFACTS = {"apk", "aab"}


@dataclass(frozen=True)
class AndroidKeystore:
    volume: str
    container_path: str
    alias: str
    store_password: str
    key_password: str


def get_android_config(config):
    return config.get("android", {})


def get_android_artifacts(config):
    artifacts = get_android_config(config).get("artifacts", ["apk", "aab"])
    if isinstance(artifacts, str):
        artifacts = [artifacts]
    if not isinstance(artifacts, list) or not all(
        isinstance(x, str) for x in artifacts
    ):
        sys.exit("android.artifacts must be a string or list of strings")
    invalid = set(artifacts) - VALID_ARTIFACTS
    if invalid:
        sys.exit(f"Invalid Android artifacts: {', '.join(sorted(invalid))}")
    return artifacts


def get_docker_image(config):
    android_config = get_android_config(config)
    if "docker_image" in android_config:
        return android_config["docker_image"]
    return f"luke100000/love-android-builder:{config['love_version']}"


def get_application_id(config):
    android_config = get_android_config(config)
    if "application_id" in android_config:
        return android_config["application_id"]

    name = re.sub(r"[^A-Za-z0-9_]", "", config["name"].lower())
    if not name or not re.match(r"[A-Za-z]", name):
        name = "app" + name
    return "org.love2d." + name


def validate_application_id(application_id):
    segment = r"[A-Za-z][A-Za-z0-9_]*"
    if not re.fullmatch(rf"{segment}(\.{segment})+", application_id):
        sys.exit(f"Invalid Android application_id: {application_id}")


def validate_version_code(android_version_code):
    if not str(android_version_code).isdigit() or int(android_version_code) < 1:
        sys.exit("android.version_code must be a positive integer")


def get_android_debug_keystore_dir():
    return os.path.join(appdirs.user_cache_dir("makelove"), "android")


def get_android_keystore(config):
    android_config = get_android_config(config)
    keystore = android_config.get("keystore")
    keystore_alias = android_config.get(
        "keystore_alias", os.environ.get("KEYSTORE_ALIAS")
    )
    keystore_password = android_config.get(
        "keystore_password", os.environ.get("KEYSTORE_PW")
    )
    key_password = android_config.get(
        "key_password", os.environ.get("KEY_PW", keystore_password)
    )

    if keystore:
        if not keystore_alias or not keystore_password:
            sys.exit(
                "Android release signing requires keystore, keystore_alias, "
                "and keystore_password"
            )
        keystore_path = str(os.path.abspath(keystore))
        keystore_dir = os.path.dirname(keystore_path)
        return AndroidKeystore(
            volume=f"{keystore_dir}:/work/keystore",
            container_path=f"/work/keystore/{os.path.basename(keystore_path)}",
            alias=keystore_alias,
            store_password=keystore_password,
            key_password=key_password or keystore_password,
        )

    # Use a debug key
    keystore_dir = get_android_debug_keystore_dir()
    print(
        "Android release keystore not configured; using a generated debug "
        f"keystore in {keystore_dir}"
    )
    return AndroidKeystore(
        volume=f"{keystore_dir}:/work/keystore",
        container_path="/work/keystore/debug.keystore",
        alias="androiddebugkey",
        store_password="android",
        key_password="android",
    )


def validate_optional_file(path, description):
    if path and not os.path.isfile(path):
        sys.exit(f"Could not find Android {description}: {path}")


def run_command(args, error_message, env=None):
    try:
        ret = subprocess.run(args, env=env)
    except FileNotFoundError:
        sys.exit("Docker is required to build the android target.")
    if ret.returncode != 0:
        sys.exit(f"{error_message} with exit code {ret.returncode}")


def build_android(config, version, target, target_directory, love_file_path):
    android_config = get_android_config(config)
    manifest = android_config.get("manifest")
    icon_file = android_config.get("icon_file", config.get("icon_file"))
    application_id = get_application_id(config)
    output_name = config["name"]
    android_version_code = android_config.get("version_code", "1")
    android_version_name = android_config.get("version_name", version or "1.0.0")
    android_app_name = android_config.get("app_name", config["name"])
    artifacts = get_android_artifacts(config)

    validate_optional_file(manifest, "manifest")
    validate_optional_file(icon_file, "icon")
    validate_application_id(application_id)
    validate_version_code(android_version_code)
    keystore = get_android_keystore(config)

    image = get_docker_image(config)
    docker_env = os.environ.copy()
    docker_env["KEYSTORE_PASSWORD"] = keystore.store_password
    docker_env["KEY_PASSWORD"] = keystore.key_password
    docker_args = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.path.abspath(love_file_path)}:/work/game.love:ro",
        "-v",
        f"{os.path.abspath(target_directory)}:/out",
        "-v",
        keystore.volume,
        "-e",
        "GAME_LOVE=/work/game.love",
        "-e",
        "OUT_DIR=/out",
        "-e",
        f"OUTPUT_NAME={output_name}",
        "-e",
        f"APP_NAME={android_app_name}",
        "-e",
        f"APPLICATION_ID={application_id}",
        "-e",
        f"VERSION_CODE={android_version_code}",
        "-e",
        f"VERSION_NAME={android_version_name}",
        "-e",
        f"ORIENTATION={android_config.get('orientation', 'landscape')}",
        "-e",
        f"RECORD_AUDIO={str(android_config.get('record_audio', False)).lower()}",
        "-e",
        f"ARTIFACTS={' '.join(artifacts)}",
        "-e",
        f"KEYSTORE={keystore.container_path}",
        "-e",
        f"KEYSTORE_ALIAS={keystore.alias}",
        "-e",
        "KEYSTORE_PASSWORD",
        "-e",
        "KEY_PASSWORD",
    ]

    if icon_file:
        docker_args.extend(
            [
                "-v",
                f"{os.path.abspath(icon_file)}:/work/icon:ro",
                "-e",
                "ICON=/work/icon",
            ]
        )
    if manifest:
        docker_args.extend(
            [
                "-v",
                f"{os.path.abspath(manifest)}:/work/AndroidManifest.xml:ro",
                "-e",
                "MANIFEST=/work/AndroidManifest.xml",
            ]
        )

    docker_args.append(image)
    print(f"Building Android artifacts with prebuilt Docker image {image}")
    run_command(docker_args, "Android build failed", env=docker_env)
