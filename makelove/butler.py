import os
import shutil
import subprocess
import sys


def publish(itchapp, config, version, targets, build_directory):
    if shutil.which("butler") is None:
        sys.exit("Could not find butler.")

    if config.get("publish_love", False):
        targets = targets.copy()
        targets.append("love")

    for platform_target in targets:
        target_root = os.path.join(build_directory, platform_target)
        if not os.path.isdir(target_root):
            sys.exit(f"Could not find artifacts for publish target '{platform_target}'")

        published = False
        for file in os.listdir(target_root):
            fpath = os.path.join(target_root, file)
            if not os.path.isfile(fpath):
                continue

            command = ["butler", "push", fpath, f"{itchapp}:{platform_target}"]
            if version is not None:
                command.extend(["--userversion", version])
            subprocess.check_call(command)
            published = True

        if not published:
            sys.exit(f"No files to publish for target '{platform_target}'")
