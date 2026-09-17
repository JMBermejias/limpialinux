#!/usr/bin/env python3
# Copyright (C) 2026 Jose Manuel Bernabeu Mejias
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

"""Verifica la firma _gpg* de un .deb (formato dpkg-sig v4).

Requiere gpg y la clave publica del firmante importada. Ejemplo:
    python3 verify_deb.py dist/limpialinux_1.0.0_all.deb
"""

import hashlib
import re
import subprocess
import sys


class DebError(Exception):
    pass


def read_ar(path):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"!<arch>\n"):
        raise DebError("No es un archivo ar valido")
    members, pos = [], 8
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        name = hdr[:16].decode("latin1").strip().rstrip("/").strip()
        try:
            size = int(hdr[48:58].strip() or b"0")
        except ValueError:
            break
        members.append((name, data[pos + 60:pos + 60 + size]))
        pos += 60 + size + (size % 2)
    return members


def gpg_decrypt(blob):
    proc = subprocess.run(["gpg", "--batch", "--status-fd", "2", "--decrypt"],
                          input=blob, capture_output=True, timeout=60)
    status = proc.stderr.decode(errors="replace")
    ok = "VALIDSIG" in status
    fingerprint = None
    for line in status.splitlines():
        if line.startswith("[GNUPG:] VALIDSIG "):
            fingerprint = line.split()[2]
    return ok, fingerprint, proc.stdout


def parse_sig_info(text):
    fields = {}
    files = []
    for line in text.splitlines():
        if line.startswith("\t") or line.startswith(" "):
            parts = line.strip().split()
            if len(parts) == 4:
                files.append({"md5": parts[0], "sha1": parts[1],
                              "size": int(parts[2]), "name": parts[3]})
        elif ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return fields, files


def verify(path):
    members = read_ar(path)
    for name, blob in members:
        m = re.match(r"^_gpg(\S+?)([0-9A-Z]?)$", name)
        if not m:
            continue
        role = m.group(1)
        ok, fpr, plain = gpg_decrypt(blob)
        fields, files = parse_sig_info(plain.decode(errors="replace"))
        print("Firma en miembro: %s" % name)
        print("  Role: %s  (miembro esperado: _gpg%s)" % (fields.get("Role"), role))
        print("  Version: %s  Signer: %s  Date: %s"
              % (fields.get("Version"), fields.get("Signer"), fields.get("Date")))
        print("  Verificacion gpg:", "OK" if ok else "FALLIDA",
              "(%s)" % fpr if fpr else "")
        if not ok:
            return 1
        if role != fields.get("Role"):
            print("  ERROR: Role no coincide con el nombre del miembro")
            return 1
        by_name = {f["name"]: f for f in files}
        for mname, mdata in members:
            if mname in by_name:
                f = by_name[mname]
                match = (f["md5"] == hashlib.md5(mdata).hexdigest() and
                         f["sha1"] == hashlib.sha1(mdata).hexdigest() and
                         f["size"] == len(mdata))
                print("  %-16s size=%d md5=%s  %s"
                      % (mname, len(mdata), f["md5"], "ok" if match else "!! CORRUPTA"))
                if not match:
                    return 1
        for required in ("debian-binary", "control.tar.gz", "data.tar.gz"):
            if required not in by_name:
                print("  ERROR: miembro obligatorio %s no firmado" % required)
                return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 verify_deb.py <paquete.deb>")
        sys.exit(2)
    try:
        sys.exit(verify(sys.argv[1]))
    except DebError as exc:
        print("ERROR:", exc)
        sys.exit(1)