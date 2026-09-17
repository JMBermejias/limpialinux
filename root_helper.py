#!/usr/bin/env python3
# Copyright (C) 2026 JMBermejas
#
# LimpiaLinux is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Helper privilegiado de LimpiaLinux (se ejecuta via pkexec como root).

SOLO acepta identificadores de tarea de un conjunto fijo; nunca acepta
rutas ni argumentos arbitrarios. Emite JSON por linea:

    {"id": "...", "ok": true, "bytes": N, "count": N, "detail": "..."}

Uso:
    root_helper.py size  apt-cache,registros
    root_helper.py clean apt-cache,registros
"""

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

VERBOSE = True
START = time.time()


def out(**kw):
    line = json.dumps(kw, ensure_ascii=False)
    print(line, flush=True)


def ok(cid, size, count, detail=""):
    out(id=cid, ok=True, bytes=size, count=count, detail=detail)


def fail(cid, detail):
    out(id=cid, ok=False, bytes=0, count=0, detail=detail)


def valid_ids(ids):
    valid = set(c["id"] for c in core.catalog())
    good = []
    for i in ids:
        i = str(i).strip()
        if not re.match(r"^[a-z0-9-]+$", i):
            continue
        if i in valid:
            good.append(i)
    return sorted(set(good))


def main(argv):
    if len(argv) < 2:
        fail("args", "uso: root_helper.py (size|clean) id1,id2,...")
        return 1
    cmd = argv[0]
    if cmd not in ("size", "clean"):
        fail("args", "comando desconocido: %s" % cmd)
        return 1

    ids = valid_ids(argv[1].split(",")) if len(argv) > 1 else []
    if not ids:
        fail("args", "no hay tareas validas")
        return 1

    for cid in ids:
        c = core.by_id(cid)
        if c is None or c["scope"] != "system":
            fail(cid, "tarea no permitida")
            continue
        try:
            if cmd == "size":
                size, count, det = c["scan"]({"root": True})
                ok(cid, size, count, det)
            else:
                size, count, det = c["clean"]({"root": True})
                ok(cid, size, count, det)
        except Exception as e:
            fail(cid, "error: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))