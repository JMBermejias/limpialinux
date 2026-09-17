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

"""Genera el paquete .deb de LimpiaLinux sin depender de dpkg-deb.

Uso:
    python3 build_deb.py                 -> dist/limpialinux_1.0.0_all.deb
    python3 build_deb.py --version 1.1.0

La version se lee de pyproject.toml salvo que se pase --version.
"""

import argparse
import hashlib
import io
import os
import re
import tarfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PACKAGE = "limpialinux"
MAINTAINER = "JMBermejas"
HOMEPAGE = "https://github.com/JMBermejias/limpialinux"
DESCRIPTION = "Limpieza de Zorin OS y sistemas basados en Debian"

# Dependencias minimas: python3 + GTK3 (interfaz) y polkit (elevacion de las
# tareas de sistema con pkexec). El resto del codigo es libreria estandar.
DEPENDS = "python3, python3-gi, gir1.2-gtk-3.0, policykit-1"

CONTROL = """Package: {pkg}
Version: {version}
Architecture: all
Maintainer: {maintainer}
Installed-Size: {size}
Depends: {depends}
Section: admin
Priority: optional
Homepage: {homepage}
Description: {desc_short}
 Limpia la papelera, caches de aplicaciones y navegadores, paquetes
 huerfanos, kernels antiguos, registros del sistema y logs rotados.
 Interfaz grafica nativa (GTK3) y linea de comandos. Las tareas de
 sistema elevan permisos con pkexec/polkit sin ejecutar la interfaz
 como root. Licencia GPLv3.
"""

POSTINST = """#!/bin/sh
set -e
case "$1" in
  configure)
    if command -v update-desktop-database >/dev/null 2>&1; then
      update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
      gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi
    ;;
esac
exit 0
"""

POSTRM = """#!/bin/sh
set -e
case "$1" in
  remove|purge)
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
      gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
      update-desktop-database -q /usr/share/applications || true
    fi
    ;;
esac
exit 0
"""

WRAPPER = """#!/bin/sh
# Lanzador de LimpiaLinux. El interprete y las librerias son las del sistema
# (dependencias python3/python3-gi); no se crea venv.
exec /usr/bin/python3 /usr/lib/limpialinux/limpialinux.py "$@"
"""


def read_version():
    path = os.path.join(ROOT, "pyproject.toml")
    with open(path) as f:
        m = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "1.0.0"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copyright_text():
    with open(os.path.join(ROOT, "LICENSE")) as f:
        gpl = f.read().strip()
    indent = lambda text: "\n".join(" " + line if line else "" for line in text.splitlines())
    return (
        "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
        "Upstream-Name: limpialinux\n"
        "Source: {homepage}\n"
        "\n"
        "Files: *\n"
        "Copyright: 2026 JMBermejas\n"
        "License: GPL-3.0-or-later\n"
        " This program is free software: you can redistribute it and/or modify\n"
        " it under the terms of the GNU General Public License as published by\n"
        " the Free Software Foundation, either version 3 of the License, or\n"
        " (at your option) any later version.\n"
        " .\n"
        " This program is distributed in the hope that it will be useful,\n"
        " but WITHOUT ANY WARRANTY; without even the implied warranty of\n"
        " MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the\n"
        " GNU General Public License for more details.\n"
        " .\n"
        " You should have received a copy of the GNU General Public License\n"
        " along with this program.  If not, see <https://www.gnu.org/licenses/>.\n"
        " .\n"
        " On Debian systems, the complete text of the GNU General Public\n"
        " License can be found in the file '/usr/share/common-licenses/GPL-3'.\n"
        " .\n"
        "{indented}\n"
    ).format(homepage=HOMEPAGE, indented=indent(gpl))


def build_tree():
    """Devuelve {ruta_relativa_en_el_paquete: (ruta_origen, permisos)}."""
    files = {}
    lib_src = {
        "core.py": 0o644,
        "limpialinux.py": 0o644,
        "root_helper.py": 0o755,
    }
    for name, mode in lib_src.items():
        files["usr/lib/limpialinux/" + name] = (
            os.path.join(ROOT, name), mode)
    assets = {
        "usr/share/applications/limpialinux.desktop": "assets/limpialinux.desktop",
        "usr/share/icons/hicolor/scalable/apps/limpialinux.svg": "assets/limpialinux.svg",
        "usr/share/polkit-1/actions/com.jmbernabeu.limpialinux.policy":
            "assets/com.jmbernabeu.limpialinux.policy",
    }
    for rel, src in assets.items():
        files[rel] = (os.path.join(ROOT, src), 0o644)
    # documentacion
    files["usr/share/doc/limpialinux/LICENSE"] = (os.path.join(ROOT, "LICENSE"), 0o644)
    files["usr/share/doc/limpialinux/README.md"] = (os.path.join(ROOT, "README.md"), 0o644)
    # lanzador
    files["usr/bin/limpialinux"] = (os.path.join(ROOT, "build",
                                                 "usr-bin-limpialinux"), 0o755)
    return files


def stage_files(files):
    import shutil
    stage = os.path.join(ROOT, "build", "stage")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    for rel, (src, mode) in files.items():
        dst = os.path.join(stage, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as fi, open(dst, "wb") as fo:
            fo.write(fi.read())
        os.chmod(dst, mode)
    return stage


def make_tar(stage, member_paths, modes, prefix=""):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        for rel, mode in zip(member_paths, modes):
            p = os.path.join(stage, rel)
            ti = tf.gettarinfo(p, arcname=prefix + rel)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            ti.mode = mode
            ti.mtime = 0
            if ti.isdir():
                tf.addfile(ti)
            else:
                with open(p, "rb") as f:
                    tf.addfile(ti, f)
    return buf.getvalue()


def ar_member(name, data, mode=0o100644):
    hdr = "%s/%-15s" % (name, " ")
    hdr = hdr[:16]
    mtime, uid, gid = "0", "0", "0"
    size = str(len(data))
    mode_s = "%06o" % mode
    header = (hdr + mtime.rjust(12) + uid.rjust(6) + gid.rjust(6) +
              mode_s.rjust(8) + size.rjust(10) + "`\n").encode()
    payload = data
    if len(payload) % 2:
        payload += b"\n"
    return header + payload


def build_deb(version):
    # lanzador
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with open(os.path.join(ROOT, "build", "usr-bin-limpialinux"), "w") as f:
        f.write(WRAPPER)
    os.chmod(os.path.join(ROOT, "build", "usr-bin-limpialinux"), 0o755)

    files = build_tree()
    stage = stage_files(files)
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)

    # control.tar.gz
    control_dir = os.path.join(ROOT, "build", "control")
    import shutil
    if os.path.isdir(control_dir):
        shutil.rmtree(control_dir)
    os.makedirs(control_dir)

    total = sum(os.path.getsize(s) for s, _m in files.values())
    control_content = CONTROL.format(
        pkg=PACKAGE, version=version, maintainer=MAINTAINER,
        homepage=HOMEPAGE, size=max(1, total // 1024), depends=DEPENDS,
        desc_short=DESCRIPTION)
    with open(os.path.join(control_dir, "control"), "w") as f:
        f.write(control_content)

    md5s = "\n".join("%s  %s" % (md5(src), rel)
                     for rel, (src, _m) in sorted(files.items())) + "\n"
    with open(os.path.join(control_dir, "md5sums"), "w") as f:
        f.write(md5s)
    with open(os.path.join(control_dir, "postinst"), "w") as f:
        f.write(POSTINST)
    with open(os.path.join(control_dir, "postrm"), "w") as f:
        f.write(POSTRM)
    # copyright DEP-5 en control/ (se copia tambien a la doc)
    with open(os.path.join(control_dir, "copyright"), "w") as f:
        f.write(copyright_text())
    import shutil as _sh
    _sh.copyfile(os.path.join(control_dir, "copyright"),
                 os.path.join(stage, "usr/share/doc/limpialinux/copyright"))
    # md5sums debe incluir el copyright empaquetado en data
    md5s = md5s + ("%s  usr/share/doc/limpialinux/copyright\n" %
                   md5(os.path.join(control_dir, "copyright")))
    with open(os.path.join(control_dir, "md5sums"), "w") as f:
        f.write(md5s)

    control_tar = make_tar(control_dir,
                           ["control", "md5sums", "postinst", "postrm", "copyright"],
                           [0o100644, 0o100644, 0o100755, 0o100755, 0o100644],
                           prefix="./")

    # data.tar.gz (directorios intermedios con 0755)
    extra_data = ["usr/share/doc/limpialinux/copyright"]
    data_members = []
    seen_dirs = set()
    all_paths = sorted(files) + extra_data
    for rel in all_paths:
        parts = rel.split("/")
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if d not in seen_dirs:
                seen_dirs.add(d)
                os.makedirs(os.path.join(stage, d), exist_ok=True)
                data_members.append((d, 0o40755))
        mode = files.get(rel, (None, 0o644))[1] if rel in files else 0o644
        data_members.append((rel, mode))
    data_tar = make_tar(stage, [m[0] for m in data_members], [m[1] for m in data_members])

    deb = (ar_member("debian-binary", b"2.0\n", 0o100644) +
           ar_member("control.tar.gz", control_tar, 0o100644) +
           ar_member("data.tar.gz", data_tar, 0o100644))

    out = os.path.join(out_dir, "%s_%s_all.deb" % (PACKAGE, version))
    with open(out, "wb") as f:
        f.write(b"!<arch>\n" + deb)
    print("Paquete generado:", out)
    print("Ficheros:", len(files), "- Tamano:", len(deb), "bytes")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el .deb de LimpiaLinux")
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    build_deb(args.version or read_version())