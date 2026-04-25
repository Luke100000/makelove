import html
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve
from zipfile import ZipFile

from .util import eprint, get_default_love_binary_dir, parse_love_version

DEFAULT_DOWNLOAD_URL = "https://github.com/rozenmad/love-web-builder/archive/master.zip"
DEFAULT_INDEX = "lovejs_source/template.html"
DEFAULT_THEME = "lovejs_source/theme"
DEFAULT_GAME_JS = "lovejs_source/game.js"

versions = {
    "11.5": {
        "love.js": "https://raw.githubusercontent.com/Davidobot/love.js/refs/heads/master/src/compat/love.js",
        "love.wasm": "https://raw.githubusercontent.com/Davidobot/love.js/refs/heads/master/src/compat/love.wasm",
    },
    "12.0": {
        "love.js": "https://raw.githubusercontent.com/rozenmad/love-web-builder/refs/heads/main/lovejs_source/compat/love.js",
        "love.wasm": "https://raw.githubusercontent.com/rozenmad/love-web-builder/refs/heads/main/lovejs_source/compat/love.wasm",
    },
}


def resolve_lovejs_version(version):
    if version in versions:
        return version, versions[version]

    major = parse_love_version(version)[0]
    matching_versions = [
        supported_version
        for supported_version in versions
        if parse_love_version(supported_version)[0] == major
    ]
    if matching_versions:
        selected_version = sorted(matching_versions, key=parse_love_version)[-1]
        eprint(
            f"No love.js support files configured for LÖVE {version}. "
            f"Using {selected_version}."
        )
        return selected_version, versions[selected_version]

    supported_versions = ", ".join(sorted(versions, key=parse_love_version))
    sys.exit(
        f"No love.js support files configured for LÖVE {version}. "
        f"Supported versions: {supported_versions}"
    )


def download_love(version, platform):
    _lovejs_version, lovejs_config = resolve_lovejs_version(version)

    target_path = get_default_love_binary_dir(version, platform)
    print(f"Downloading love binaries to: '{target_path}'")

    os.makedirs(target_path, exist_ok=True)
    try:
        print(f"Downloading '{DEFAULT_DOWNLOAD_URL}'..")
        urlretrieve(DEFAULT_DOWNLOAD_URL, os.path.join(target_path, "love.zip"))
        for name, url in lovejs_config.items():
            print(f"Downloading '{url}'..")
            urlretrieve(url, os.path.join(target_path, name))
    except URLError as exc:
        eprint(f"Could not download löve: {exc}")
        eprint(
            "If there is in fact no download on GitHub for this version, specify 'love_binaries' manually."
        )
        sys.exit(1)
    print("Download complete")


# Simplified [mustache](https://github.com/janl/mustache.js) templating used by love.js
def render_mustache(tmpl, cx):
    tmpl = tmpl.decode("utf-8")
    for k, v in cx.items():
        tmpl = tmpl.replace("{{{" + k + "}}}", str(v))
        tmpl = tmpl.replace("{{" + k + "}}", html.escape(str(v)))
    return tmpl.encode("utf-8")


def read_zip_file(zip_file, path):
    return zip_file.read(get_zip_prefix(zip_file) + path)


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def get_zip_prefix(zip_file):
    top_level_dirs = set()
    for zipinfo in zip_file.filelist:
        if "/" not in zipinfo.filename:
            return ""
        top_level_dirs.add(zipinfo.filename.split("/", 1)[0])
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop() + "/"
    return ""


def copy_file(output_files, dst, src):
    if not os.path.isfile(src):
        sys.exit(f"Cannot copy love.js file '{src}'")
    output_files[dst] = read_file(src)


def copy_zip_directory(output_files, dst, zip_file, src):
    prefix = get_zip_prefix(zip_file) + src.rstrip("/") + "/"
    for zipinfo in zip_file.infolist():
        if zipinfo.is_dir() or not zipinfo.filename.startswith(prefix):
            continue
        relpath = zipinfo.filename[len(prefix) :]
        output_files[f"{dst}/{relpath}"] = zip_file.read(zipinfo)


def copy_directory(output_files, dst, src):
    if not os.path.isdir(src):
        sys.exit(f"Cannot copy love.js directory '{src}'")
    for root, _dirs, files in os.walk(src):
        for filename in files:
            path = os.path.join(root, filename)
            relpath = os.path.relpath(path, src).replace(os.sep, "/")
            output_files[f"{dst}/{relpath}"] = read_file(path)


def has_default_zip(path):
    zip_path = Path(path) / "love.zip"
    if not zip_path.is_file():
        return False
    with ZipFile(zip_path, mode="r") as love_binary_zip:
        prefix = get_zip_prefix(love_binary_zip)
        names = love_binary_zip.namelist()
        return all(prefix + name in names for name in (DEFAULT_INDEX, DEFAULT_GAME_JS))


def build_lovejs(config, version, target, target_directory, love_file_path):
    if target in config and "love_binaries" in config[target]:
        love_binaries = config[target]["love_binaries"]
    else:
        assert "love_version" in config
        print(f"No love binaries specified for target {target}")
        love_binaries = get_default_love_binary_dir(config["love_version"], target)
        if os.path.isdir(love_binaries):
            print(f"Love binaries already present in '{love_binaries}'")
        else:
            download_love(config["love_version"], target)

    with open(love_file_path, "rb") as love_zip:
        game_data = love_zip.read()

    lovejs_section = config.get("lovejs", {})

    src = Path(love_binaries) / "love.zip"
    dst = Path(target_directory) / f"{config['name']}-{target}.zip"

    output_files = {}
    with ZipFile(src, mode="r") as love_binary_zip, ZipFile(dst, mode="w") as app_zip:
        package_info = {
            "package_uuid": str(uuid.uuid4()),
            "remote_package_size": len(game_data),
            "files": [{"filename": "/game.love", "start": 0, "end": len(game_data)}],
        }

        output_files["index.html"] = render_mustache(
            read_file(lovejs_section["index_file"])
            if "index_file" in lovejs_section
            else read_zip_file(love_binary_zip, DEFAULT_INDEX),
            {" TITLE ": lovejs_section.get("title", config["name"])},
        )

        output_files["game.js"] = render_mustache(
            read_zip_file(love_binary_zip, DEFAULT_GAME_JS),
            {
                " PACKAGE ": json.dumps(package_info),
                " FILES ": json.dumps(["/game.love"]),
            },
        )
        output_files["game.data"] = game_data

        if "theme_directory" in lovejs_section:
            copy_directory(output_files, "theme", lovejs_section["theme_directory"])
        else:
            copy_zip_directory(output_files, "theme", love_binary_zip, DEFAULT_THEME)

        copy_file(
            output_files,
            "love.js",
            lovejs_section.get("love_js_file", Path(love_binaries) / "love.js"),
        )

        copy_file(
            output_files,
            "love.wasm",
            lovejs_section.get("love_wasm_file", Path(love_binaries) / "love.wasm"),
        )

        for path, data in output_files.items():
            app_zip.writestr(f"{config['name']}/{path}", data)
