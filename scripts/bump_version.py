#!/usr/bin/env python

import argparse
import hashlib
import subprocess
from pathlib import Path

from notifications_utils.version_tools import color

version_file_path = "notifications_utils/version.py"

globals = {}
with open(version_file_path) as f:
    version_contents = f.read()
    exec(version_contents, globals)
old_version = globals["__version__"]

version_parts = ("major", "minor", "patch")

parser = argparse.ArgumentParser()
parser.add_argument("version_part", choices=version_parts)
version_part = parser.parse_args().version_part

current_major, current_minor, current_patch = map(int, old_version.split("."))

print(f"current version {old_version=}")

new_major, new_minor, new_patch = {
    "major": (current_major + 1, 0, 0),
    "minor": (current_major, current_minor + 1, 0),
    "patch": (current_major, current_minor, current_patch + 1),
}[version_part]

package_contents = subprocess.run(("tar", "cf", "-", "notifications_utils"), capture_output=True).stdout

# Putting a hash of the package contents on the same line as the version
# number will force a merge conflict if two people try to release
# different code under the same version
package_contents_hash = hashlib.md5(package_contents).hexdigest()

output = f"""
# This file is autogenerated.
#
# To update or resolve merge conflicts run one of:
# - `make version-major` for breaking changes
# - `make version-minor` for new features
# - `make version-patch` for bug fixes

__version__ = "{new_major}.{new_minor}.{new_patch}"  # {package_contents_hash}
""".lstrip()

with Path(version_file_path).open("w") as version_file:
    version_file.write(output)

print("")
print(
    f"{color.BOLD}{color.GREEN}"
    f"Changed version from {old_version} to {new_major}.{new_minor}.{new_patch}"
    f"{color.END} ✅"
)
print("")
print("   Update requirements files in other apps with:")
print("")
print(
    f"   "
    f"notifications-utils @ git+https://github.com/alphagov/notifications-utils.git"
    f"@{new_major}.{new_minor}.{new_patch}"
)
print("")

print(f"{color.YELLOW}{color.BOLD}Make sure to update CHANGELOG.md, for example:{color.END}")
print(
    f"""
## {new_major}.{new_minor}.{new_patch}

* Details of change 1
* Details of change 2
"""
)
