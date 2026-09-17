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

"""Motor de limpieza de LimpiaLinux.

Define el catalogo de tareas de limpieza (identificador, etiqueta,
descripcion, alcance y funciones de escaneo/borrado) compartido por la
interfaz grafica, la linea de comandos y el helper privilegiado
(root_helper.py).

Cada tarea expone:
    scan(ctx)   -> (bytes, count, detalle)
    clean(ctx)  -> (bytes_liberados, count, detalle)

donde ctx es None para tareas de usuario (la GUI las ejecuta con los
permisos del usuario actual) u otro contexto para tareas de sistema que
solo puede ejecutar root a traves del helper privilegiado.
"""

import os
import re
import shutil
import subprocess
import datetime

# Dias de antiguedad que se consideran "viejo" para temporales y logs.
OLD_DAYS = 7
# Dias de historial de journald que se conservan al limpiar registros.
JOURNAL_KEEP_DAYS = 7
# Numero de nucleos (imagenes de kernel) que se conservan instalados.
KERNELS_KEEP = 2

# Identificadores de tareas de sistema que exigen root (via pkexec).
SYSTEM_IDS = [
    "apt-cache",
    "apt-parcial",
    "paquetes-autoremovibles",
    "nucleos-antiguos",
    "registros",
    "logs-antiguos",
    "pip-cache",
]

# Identificadores de tareas que se ejecutan con los permisos del usuario.
USER_IDS = [
    "papelera",
    "cache-usuario",
    "miniaturas",
    "navegadores",
    "temporales",
]


def fmt_size(n):
    """Devuelve una cadena legible para un numero de bytes."""
    n = max(0, int(n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return "%d B" % n
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0
    return "%d B" % n


def dir_size(path):
    """Tamano en bytes y numero de ficheros de un directorio (seguimiento
    a primer nivel de enlaces simbolicos, ignorando errores de permisos)."""
    total = 0
    count = 0
    seen = set()
    for root, dirs, files in os.walk(path, topdown=True):
        try:
            st = os.lstat(root)
        except OSError:
            continue
        if os.path.islink(root):
            continue
        for name in files:
            fp = os.path.join(root, name)
            try:
                if os.path.islink(fp):
                    continue
                total += os.path.getsize(fp)
                count += 1
            except OSError:
                continue
    return total, count


def remove_path(path, ignore_errors=True):
    """Borra un fichero o directorio, devolviendo si existia."""
    if not os.path.lexists(path):
        return False
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=ignore_errors)
        else:
            os.remove(path)
        return True
    except OSError:
        return False


def run(cmd, **kw):
    """Ejecuta un comando sin mostrarle terminal."""
    kw.setdefault("env", dict(os.environ))
    kw["env"].pop("GIT_PAGER", None)
    try:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, **kw).communicate()[0]
    except OSError:
        return b""


def packages(pkg_re):
    """Lista de paquetes instalados cuyo nombre casa con la expresion."""
    out = run(["dpkg-query", "-W", "-f=${Status}|${Package}|${Version}\n"])
    res = set()
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        status, pkg, ver = parts
        if status.startswith("install ok installed"):
            res.add((pkg, ver))
    if pkg_re is None:
        return res
    rx = re.compile(pkg_re)
    return [(p, v) for (p, v) in res if rx.match(p)]


def current_kernels():
    """Conjunto de versiones de kernel que no se deben borrar."""
    keep = set()
    try:
        out = run(["uname", "-r"])
        running = out.decode("utf-8", "replace").strip().split("-")[0]
        keep.add(running)
    except Exception:
        pass
    try:
        # genera, sin ser exhaustivo: versiones instaladas en /usr/lib/modules
        for name in os.listdir("/usr/lib/modules"):
            base = name.split("-")[0]
            keep.add(base)
    except OSError:
        pass
    return keep


def running_kernel_base():
    try:
        out = run(["uname", "-r"]).decode("utf-8", "replace").strip()
        return out.split("-")[0]
    except Exception:
        return None


# ---------------------------------------------------------------- tareas

def _scan_papelera(ctx):
    trash = os.path.expanduser("~/.local/share/Trash")
    if not os.path.isdir(trash):
        return 0, 0, "Papelera vacia"
    total, count = dir_size(trash)
    return total, count, "Papelera del usuario actual"


def _clean_papelera(ctx):
    trash = os.path.expanduser("~/.local/share/Trash")
    total, count = dir_size(trash)
    for name in ("files", "info"):
        remove_path(os.path.join(trash, name))
    return total, count, "Papelera vaciada"


def _scan_cache(ctx):
    base = os.path.expanduser("~/.cache")
    excl = {"thumbnails", "pip"}
    total = 0
    count = 0
    for name in os.listdir(base):
        if name in excl:
            continue
        b, c = dir_size(os.path.join(base, name))
        total += b
        count += c
    return total, count, "Cache de aplicaciones (~/.cache)"


def _clean_cache(ctx):
    base = os.path.expanduser("~/.cache")
    excl = {"thumbnails", "pip"}
    total = 0
    count = 0
    for name in os.listdir(base):
        if name in excl:
            continue
        p = os.path.join(base, name)
        b, c = dir_size(p)
        remove_path(p)
        total += b
        count += c
    return total, count, "Cache de aplicaciones vaciada"


def _scan_miniaturas(ctx):
    base = os.path.expanduser("~/.cache/thumbnails")
    total, count = dir_size(base)
    return total, count, "Miniaturas de archivos"


def _clean_miniaturas(ctx):
    base = os.path.expanduser("~/.cache/thumbnails")
    total, count = dir_size(base)
    for d in (("fail", "large", "normal", "x-large", "xx-large")):
        remove_path(os.path.join(base, d))
    return total, count, "Miniaturas borradas"


def _browser_caches():
    """Directorios de cache de los navegadores comunes en HOME."""
    home = os.path.expanduser("~")
    dirs = []
    pats = [
        "~/.cache/mozilla/firefox",
        "~/.mozilla/firefox",
        "~/.cache/google-chrome",
        "~/.cache/chromium",
        "~/.cache/microsoft-edge",
        "~/.cache/brave-browser",
        "~/.cache/opera",
        "~/.cache/vivaldi",
    ]
    for p in pats:
        d = os.path.expanduser(p)
        if not os.path.isdir(d):
            continue
        if "firefox" in p:
            for prof in os.listdir(d):
                if not prof.endswith(".default"):
                    continue
                for sub in ("cache2", "startupCache"):
                    fp = os.path.join(d, prof, sub)
                    if os.path.isdir(fp):
                        dirs.append(fp)
        else:
            dirs.append(d)
    return dirs


def _scan_navegadores(ctx):
    total = 0
    count = 0
    for d in _browser_caches():
        b, c = dir_size(d)
        total += b
        count += c
    if count == 0:
        return 0, 0, "Sin caches de navegadores"
    return total, count, "Caches de Firefox/Chromium/Chrome"


def _clean_navegadores(ctx):
    total = 0
    count = 0
    for d in _browser_caches():
        b, c = dir_size(d)
        remove_path(d)
        total += b
        count += c
    return total, count, "Caches de navegadores borradas"


def _scan_temporales(ctx):
    """Ficheros temporales del usuario (/tmp, /var/tmp) antiguos."""
    uid = os.getuid()
    total = 0
    count = 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=OLD_DAYS)
    for base in ("/tmp", "/var/tmp"):
        if not os.path.isdir(base):
            continue
        try:
            for name in os.listdir(base):
                fp = os.path.join(base, name)
                try:
                    st = os.lstat(fp)
                except OSError:
                    continue
                if st.st_uid != uid:
                    continue
                if datetime.datetime.fromtimestamp(st.st_mtime) > cutoff:
                    continue
                if os.path.isdir(fp) and not os.path.islink(fp):
                    b, c = dir_size(fp)
                    total += b
                    count += c
                else:
                    total += st.st_size
                    count += 1
        except OSError:
            continue
    return total, count, "Temporales de usuario antiguos (>%d dias)" % OLD_DAYS


def _clean_temporales(ctx):
    uid = os.getuid()
    total = 0
    count = 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=OLD_DAYS)
    for base in ("/tmp", "/var/tmp"):
        if not os.path.isdir(base):
            continue
        try:
            for name in os.listdir(base):
                fp = os.path.join(base, name)
                try:
                    st = os.lstat(fp)
                except OSError:
                    continue
                if st.st_uid != uid:
                    continue
                if datetime.datetime.fromtimestamp(st.st_mtime) > cutoff:
                    continue
                b = st.st_size
                c = 1
                if os.path.isdir(fp) and not os.path.islink(fp):
                    b, c = dir_size(fp)
                remove_path(fp)
                total += b
                count += c
        except OSError:
            continue
    return total, count, "Temporales de usuario borrados"


# --------------------------------------------------------- tareas sistema

def _scan_apt_cache(ctx):
    arch = "/var/cache/apt/archives"
    total = 0
    count = 0
    for name in os.listdir(arch):
        if not name.endswith(".deb"):
            continue
        fp = os.path.join(arch, name)
        try:
            total += os.path.getsize(fp)
            count += 1
        except OSError:
            pass
    return total, count, "Paquetes .deb descargados por apt"


def _clean_apt_cache(ctx):
    # se eliminan directamente; equivalente funcional a 'apt-get clean'
    arch = "/var/cache/apt/archives"
    total = 0
    count = 0
    for name in os.listdir(arch):
        if not name.endswith(".deb"):
            continue
        fp = os.path.join(arch, name)
        try:
            total += os.path.getsize(fp)
        except OSError:
            pass
        remove_path(fp)
        count += 1
    return total, count, "Cache de apt limpiada"


def _scan_apt_parcial(ctx):
    partial = "/var/cache/apt/archives/partial"
    total = 0
    count = 0
    if os.path.isdir(partial):
        for name in os.listdir(partial):
            fp = os.path.join(partial, name)
            try:
                total += os.path.getsize(fp)
                count += 1
            except OSError:
                pass
    return total, count, "Descargas interrumpidas de apt"


def _clean_apt_parcial(ctx):
    partial = "/var/cache/apt/archives/partial"
    total = 0
    count = 0
    for name in os.listdir(partial):
        fp = os.path.join(partial, name)
        try:
            total += os.path.getsize(fp)
            count += 1
        except OSError:
            pass
        remove_path(fp)
    return total, count, "Descargas interrumpidas eliminadas"


def _scan_paquetes_autoremovibles(ctx):
    """Ficheros que apt marcaria como autoremovibles (mirada a dpkg)."""
    total = count = 0
    try:
        out = subprocess.run(
            ["apt-get", "-s", "-o", "APT::Get::List-Cleanup=0", "autoremove"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode("utf-8", "replace")
        for line in out.splitlines():
            pass
        count = len([l for l in out.splitlines() if "Remv " in l])
        m = re.search(r"(\d+)\s+files? freed", out)
        if m:
            total = int(m.group(1))
    except Exception:
        pass
    if count == 0:
        return 0, 0, "Sin paquetes autoremovibles"
    return total, count, "Paquetes huerfanos (autoremove)"


def _clean_paquetes_autoremovibles(ctx):
    out = subprocess.run(["apt-get", "-y", "autoremove", "--purge"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = out.stdout.decode("utf-8", "replace")
    m = re.search(r"(\d+)\s+files? freed", text)
    freed = int(m.group(1)) if m else 0
    count = len([l for l in text.splitlines() if "Remv " in l])
    return freed, count, "Paquetes huerfanos eliminados"


def _kernel_pkgs():
    """Paquetes de kernel instalados (linux-image/linux-modules-extra)."""
    allp = packages(None)
    rx = re.compile(r"^(linux-image|linux-modules-extra|linux-headers)-([0-9][0-9.]*)")
    inst = []
    for p, v in allp:
        m = rx.match(p)
        if m:
            inst.append((p, v, m.group(2)))
    # agrupar por version de kernel
    byver = {}
    for p, v, base in inst:
        byver.setdefault(base, []).append(p)
    return byver


def _scan_nucleos_antiguos(ctx):
    byver = _kernel_pkgs()
    run_base = running_kernel_base()
    versions = sorted(byver, key=lambda x: tuple(int(i) for i in x.split(".")))
    total = 0
    count = 0
    keep = set((run_base or ""))
    # se conservan los KERNELS_KEEP mas recientes
    usable = [v for v in versions if v == run_base or v in keep]
    removable = []
    for v in versions:
        if v == run_base or v in keep:
            continue
        if len(versions) > KERNELS_KEEP and versions[-KERNELS_KEEP:] == [v]:
            continue
        removable.append(v)
    for v in removable:
        for p in byver[v]:
            out = subprocess.run(["dpkg-query", "-W", "-f=${Installed-Size}\n", p],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                total += int(out.stdout.decode().strip()) * 1024
                count += 1
            except ValueError:
                pass
    if count == 0:
        return 0, 0, "Sin kernels antiguos"
    return total, count, "Kernels antiguos (se conserva el actual y el anterior)"


def _clean_nucleos_antiguos(ctx):
    byver = _kernel_pkgs()
    run_base = running_kernel_base()
    versions = sorted(byver, key=lambda x: tuple(int(i) for i in x.split(".")))
    removable = [v for v in versions
                 if v != run_base and (len(versions) - versions.index(v)) > KERNELS_KEEP]
    pkgs = []
    for v in removable:
        pkgs.extend(byver[v])
    if not pkgs:
        return 0, 0, "Nada que purgar"
    out = subprocess.run(["apt-get", "-y", "purge"] + pkgs,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = out.stdout.decode("utf-8", "replace")
    freed = 0
    m = re.search(r"(\d+)\s+files? freed", text)
    if m:
        freed = int(m.group(1))
    return freed, len(pkgs), "Kernels antiguos purgados"


def _journal_disk_usage():
    out = subprocess.run(["journalctl", "--disk-usage"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    # respuesta: "Archived and active journals take up 12.0M on disk."
    m = re.search(r"take up\s+([\d.]+)([KMG]?)", out.stdout.decode("utf-8", "replace"))
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        mul = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}.get(unit, 1)
        return int(val * mul)
    return 0


def _scan_registros(ctx):
    return _journal_disk_usage(), 0, "Registros del sistema (journald)"


def _clean_registros(ctx):
    before = _journal_disk_usage()
    subprocess.run(["journalctl", "--vacuum-time=%dd" % JOURNAL_KEEP_DAYS, "--vacuum-size=100M"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    after = _journal_disk_usage()
    return max(0, before - after), 0, "Registros del sistema compactados"


def _scan_logs_antiguos(ctx):
    total = 0
    count = 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=OLD_DAYS)
    for root, dirs, files in os.walk("/var/log"):
        for name in files:
            if not (name.endswith((".gz", ".old", ".0", ".1", ".2", ".3", ".4"))):
                continue
            fp = os.path.join(root, name)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if datetime.datetime.fromtimestamp(st.st_mtime) < cutoff:
                total += st.st_size
                count += 1
    return total, count, "Logs rotados antiguos (>%d dias)" % OLD_DAYS


def _clean_logs_antiguos(ctx):
    total = 0
    count = 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=OLD_DAYS)
    for root, dirs, files in os.walk("/var/log"):
        for name in files:
            if not (name.endswith((".gz", ".old", ".0", ".1", ".2", ".3", ".4"))):
                continue
            fp = os.path.join(root, name)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if datetime.datetime.fromtimestamp(st.st_mtime) < cutoff:
                total += st.st_size
                count += 1
                remove_path(fp)
    return total, count, "Logs rotados antiguos borrados"


def _pip_cache_dirs():
    dirs = ["/root/.cache/pip"]
    try:
        for name in os.listdir("/home"):
            dirs.append(os.path.join("/home", name, ".cache", "pip"))
    except OSError:
        pass
    return dirs


def _scan_pip_cache(ctx):
    total = 0
    count = 0
    for d in _pip_cache_dirs():
        if os.path.isdir(d):
            b, c = dir_size(d)
            total += b
        count += 0
    return total, count, "Cache de pip (todos los usuarios)"


def _clean_pip_cache(ctx):
    total = 0
    for d in _pip_cache_dirs():
        if os.path.isdir(d):
            b, _ = dir_size(d)
            remove_path(d)
            total += b
    return total, 0, "Cache de pip limpiada"


# ------------------------------------------------------- catalogo

def _mk(id_, scope, nombre, desc, riesgo, fn_scan, fn_clean, predet=True):
    return {
        "id": id_,
        "scope": scope,
        "nombre": nombre,
        "descripcion": desc,
        "riesgo": riesgo,
        "predeterminada": predet,
        "scan": fn_scan,
        "clean": fn_clean,
    }


def catalog():
    c = []
    c.append(_mk("papelera", "user", "Papelera",
                 "Vacia la papelera de reciclaje del usuario actual", "bajo",
                 _scan_papelera, _clean_papelera))
    c.append(_mk("cache-usuario", "user", "Cache de aplicaciones",
                 "Cache de todos los programas del usuario (~/.cache)",
                 "bajo", _scan_cache, _clean_cache))
    c.append(_mk("miniaturas", "user", "Miniaturas",
                 "Miniaturas de imagenes y documentos (~/.cache/thumbnails)",
                 "bajo", _scan_miniaturas, _clean_miniaturas))
    c.append(_mk("navegadores", "user", "Caches de navegadores",
                 "Cache de Firefox, Chromium, Chrome, Edge y otros",
                 "medio", _scan_navegadores, _clean_navegadores))
    c.append(_mk("temporales", "user", "Temporales de usuario",
                 "Ficheros temporales antiguos en /tmp y /var/tmp (>%d dias)" % OLD_DAYS,
                 "bajo", _scan_temporales, _clean_temporales))
    c.append(_mk("apt-cache", "system", "Cache de apt",
                 "Paquetes .deb descargados por el gestor de paquetes",
                 "bajo", _scan_apt_cache, _clean_apt_cache))
    c.append(_mk("apt-parcial", "system", "Descargas interrumpidas",
                 "Descargas incompletas de apt en la carpeta 'partial'",
                 "bajo", _scan_apt_parcial, _clean_apt_parcial))
    c.append(_mk("paquetes-autoremovibles", "system", "Paquetes huerfanos",
                 "Dependencias que ya no usa ningun programa (autoremove)",
                 "medio", _scan_paquetes_autoremovibles,
                 _clean_paquetes_autoremovibles))
    c.append(_mk("nucleos-antiguos", "system", "Kernels antiguos",
                 "Imagenes de kernel que ya no se usan (se conserva el actual y 1 anterior)",
                 "medio", _scan_nucleos_antiguos, _clean_nucleos_antiguos))
    c.append(_mk("registros", "system", "Registros del sistema",
                 "Historial del sistema (journald), conserva los ultimos %d dias" % JOURNAL_KEEP_DAYS,
                 "bajo", _scan_registros, _clean_registros))
    c.append(_mk("logs-antiguos", "system", "Logs rotados",
                 "Logs del sistema rotados de hace mas de %d dias" % OLD_DAYS,
                 "bajo", _scan_logs_antiguos, _clean_logs_antiguos))
    c.append(_mk("pip-cache", "system", "Cache de pip",
                 "Cache de Python/pip de todos los usuarios",
                 "bajo", _scan_pip_cache, _clean_pip_cache))
    return c


def by_id(cid):
    for c in catalog():
        if c["id"] == cid:
            return c
    return None


def user_categories():
    return [c for c in catalog() if c["scope"] == "user"]


def system_categories():
    return [c for c in catalog() if c["scope"] == "system"]


def all_categories():
    return list(catalog())