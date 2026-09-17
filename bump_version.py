#!/usr/bin/env python3
# Copyright (C) 2026 Jose Manuel Bernabeu Mejias
#
# LimpiaLinux is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Incrementa la version (patch) de LimpiaLinux.

Mantiene sincronizada la version en pyproject.toml y en el modulo
limpialinux.py. Imprime la nueva version por pantalla.

Uso:
    python3 bump_version.py          -> sube el patch (1.0.0 -> 1.0.1)
    python3 bump_version.py minor    -> 1.0.1 -> 1.1.0
    python3 bump_version.py major    -> 1.1.0 -> 2.0.0
"""

import re
import sys


def read(path):
    with open(path) as f:
        return f.read()


def write(path, content):
    with open(path, "w") as f:
        f.write(content)


def bump(version, part):
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return "%d.%d.%d" % (major, minor, patch)


def main():
    part = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in (
        "major", "minor", "patch") else "patch"

    py = read("pyproject.toml")
    m = re.search(r'^version\s*=\s*"([^"]+)"', py, re.M)
    old = m.group(1)
    new = bump(old, part)
    write("pyproject.toml", py.replace(m.group(0), 'version = "%s"' % new, 1))

    lp = read("limpialinux.py")
    new_lp = re.sub(r'^VERSION\s*=\s*"[^"]+"', 'VERSION = "%s"' % new,
                    lp, count=1, flags=re.M)
    write("limpialinux.py", new_lp)

    print(new)


if __name__ == "__main__":
    main()