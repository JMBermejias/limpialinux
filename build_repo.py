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

"""Genera un repositorio apt firmado con los .deb de dist/.

Estructura resultante (listo para GitHub Pages):
    repo/pool/main/l/limpialinux/*.deb
    repo/dists/stable/main/binary-all/Packages(.gz)
    repo/dists/stable/main/binary-amd64/Packages(.gz)
    repo/dists/stable/Release
    repo/dists/stable/InRelease   (firmado por Jose Manuel Bernabeu Mejias)
    repo/dists/stable/Release.gpg (firma despegada)

Uso:
    python3 build_repo.py

La clave gpg del autor debe existir en el llavero (o usar --key).
"""

import gzip
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
REPO = os.path.join(ROOT, "repo")
HOMEPAGE = "https://github.com/JMBermejias/limpialinux"
HOST = "https://JMBermejias.github.io/limpialinux"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)


def key_id():
    out = run(["gpg", "--batch", "--with-colons", "--list-secret-keys",
               "--fingerprint"])
    fprs = [l.split(":")[9] for l in out.stdout.splitlines()
            if l.startswith("fpr:")]
    return fprs[0] if fprs else None


def packages_entry(deb_path):
    with open(deb_path, "rb") as f:
        data = f.read()
    size = len(data)
    md5 = hashlib.md5(data).hexdigest()
    sha1 = hashlib.sha1(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    name = os.path.basename(deb_path)
    return ("Package: limpialinux\n"
            "Version: %s\n"
            "Architecture: all\n"
            "Maintainer: Jose Manuel Bernabeu Mejias\n"
            "Installed-Size: %d\n"
            "Depends: python3, python3-gi, gir1.2-gtk-3.0, policykit-1\n"
            "Section: admin\n"
            "Priority: optional\n"
            "Homepage: %s\n"
            "Description: Limpieza de Zorin OS y sistemas basados en Debian\n"
            " Limpia la papelera, caches de aplicaciones y navegadores,\n"
            " paquetes huerfanos, kernels antiguos, registros del sistema\n"
            " y logs rotados. Interfaz grafica (GTK3) y CLI. GPLv3 o\n"
            " posterior.\n"
            "Filename: pool/main/l/limpialinux/%s\n"
            "Size: %d\n"
            "MD5sum: %s\n"
            "SHA1: %s\n"
            "SHA256: %s\n\n"
            % (version_of(deb_path), size // 1024, HOMEPAGE, name,
               size, md5, sha1, sha256))


def version_of(deb_path):
    base = os.path.basename(deb_path)
    return base.replace("limpialinux_", "").replace("_all.deb", "")


def checksums_line(entries):
    out = []
    for rel, path in entries:
        with open(path, "rb") as f:
            data = f.read()
        out.append((rel,
                    hashlib.md5(data).hexdigest(),
                    hashlib.sha1(data).hexdigest(),
                    hashlib.sha256(data).hexdigest(),
                    len(data)))
    return out


def build():
    debs = sorted(f for f in os.listdir(DIST) if f.endswith(".deb"))
    if not debs:
        print("No hay .deb en dist/. Ejecuta primero build_deb.py")
        sys.exit(1)

    if os.path.isdir(REPO):
        shutil.rmtree(REPO)

    pool = os.path.join(REPO, "pool/main/l/limpialinux")
    os.makedirs(pool)
    for d in debs:
        shutil.copy(os.path.join(DIST, d), os.path.join(pool, d))

    for arch in ("all", "amd64"):
        d = os.path.join(REPO, "dists/stable/main/binary-%s" % arch)
        os.makedirs(d)
        pkgs = "".join(packages_entry(os.path.join(pool, x)) for x in debs)
        with open(os.path.join(d, "Packages"), "w") as f:
            f.write(pkgs)
        with gzip.open(os.path.join(d, "Packages.gz"), "wb") as f:
            f.write(pkgs.encode())

    key = key_id()
    label = "LimpiaLinux signed repository"
    entries = []
    for arch in ("all", "amd64"):
        d = "main/binary-%s" % arch
        entries.append((d + "/Packages", os.path.join(
            REPO, "dists/stable", d + "/Packages")))
        entries.append((d + "/Packages.gz", os.path.join(
            REPO, "dists/stable", d + "/Packages.gz")))
    sums = checksums_line(entries)
    lines = ["Origin: LimpiaLinux",
             "Label: %s" % label,
             "Suite: stable",
             "Codename: stable",
             "Version: 1.0",
             "Architectures: all amd64",
             "Components: main",
             "Description: Repositorio oficial de LimpiaLinux, firmado "
             "por Jose Manuel Bernabeu Mejias.",
             "Date: %s" % _rfc2822(),
             ""]
    lines += ["MD5Sum:", "SHA1:", "SHA256:"]
    for rel, md5, sha1, sha256, size in sums:
        for tag, digest in (("MD5Sum:", md5), ("SHA1:", sha1), ("SHA256:", sha256)):
            lines.append(" %s %16d %s" % (digest, size, rel))
    release = "\n".join(lines) + "\n"
    release_path = os.path.join(REPO, "dists/stable/Release")
    with open(release_path, "w") as f:
        f.write(release)

    if key:
        inrelease = os.path.join(REPO, "dists/stable/InRelease")
        incl = run(["gpg", "--batch", "--yes", "--armor", "--clearsign",
                    "--digest-algo", "SHA512", "--local-user", key,
                    "--output", inrelease, release_path])
        if incl.returncode == 0:
            print("InRelease generado y firmado")
        else:
            print("AVISO: no se genero InRelease:", incl.stderr[:200])
        det = run(["gpg", "--batch", "--yes", "--detach-sign",
                   "--digest-algo", "SHA512", "--local-user", key,
                   "--output", os.path.join(REPO, "dists/stable/Release.gpg"),
                   release_path])
        if det.returncode != 0:
            print("AVISO: no se genero Release.gpg:", det.stderr[:200])
        asc = os.path.join(REPO, "dists/stable/Release.asc")
        if os.path.isfile(asc):
            os.remove(asc)
    else:
        print("AVISO: no hay clave gpg, el repositorio no queda firmado")

    if key:
        pub = subprocess.run(["gpg", "--export", key], capture_output=True,
                             timeout=60).stdout
        if pub:
            with open(os.path.join(REPO, "limpialinux.gpg"), "wb") as f:
                f.write(pub)

    # .nojekyll: GitHub Pages no debe pasar el sitio por Jekyll
    with open(os.path.join(REPO, ".nojekyll"), "w") as f:
        f.write("")

    print("Repositorio generado en repo/")
    print("Host de Pages:", HOST)
    print("Fuente apt para el usuario:")
    print("  deb [signed-by=/usr/share/keyrings/limpialinux.gpg] %s/ stable main" % HOST)


def _rfc2822():
    import time
    DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    tm = time.gmtime()
    return "%s, %02d %s %d %02d:%02d:%02d +0000" % (
        DAYS[tm.tm_wday], tm.tm_mday, MONTHS[tm.tm_mon - 1], tm.tm_year,
        tm.tm_hour, tm.tm_min, tm.tm_sec)


if __name__ == "__main__":
    build()