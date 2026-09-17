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

"""LimpiaLinux: limpieza de Zorin OS y sistemas basados en Debian.

Linea de comandos:
    limpialinux                abre la interfaz grafica
    limpialinux --list         lista las tareas de limpieza
    limpialinux --analyze      analiza el espacio recuperable
    limpialinux --clean ID,... limpia solo las tareas indicadas
    limpialinux --clean-all    limpia todas las tareas seguras
    limpialinux --version      muestra la version

Las tareas de "sistema" (cache de apt, kernels antiguos, registros...)
requieren permisos de administrador y se elevan mediante pkexec/polkit,
de modo que la interfaz nunca se ejecuta como root.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import core

APP_NAME = "LimpiaLinux"
APP_ID = "org.jmbernabeu.LimpiaLinux"
VERSION = "1.0.6"
HOMEPAGE = "https://github.com/JMBermejias/limpialinux"
AUTHOR = "Jose Manuel Bernabeu Mejias"
AUTHOR_ADDRESS = ("Calle Médico Rafael Navarro 2 2C, Novelda 03660 "
                  "(Alicante), España")
LICENSE_PATH = "/usr/share/doc/limpialinux/LICENSE"

ROOT_HELPER = "/usr/lib/limpialinux/root_helper.py"

HELP_TEXT = (
    "<b>Cómo funciona %s</b>\n\n"
    "1. Pulsa <b>Analizar</b> para ver el espacio que se puede liberar.\n"
    "2. Marca las tareas que quieras. Las de <b>Sistema</b> pedirán el "
    "permiso de administrador al limpiar.\n"
    "3. Pulsa <b>Limpiar</b> para ejecutarlas.\n\n"
    "<b>Usuario (sin permisos):</b> papelera, cache de aplicaciones, "
    "miniaturas, caches de navegadores y temporales.\n"
    "<b>Sistema (con administrador):</b> cache de apt, descargas "
    "interrumpidas, paquetes huérfanos, kernels antiguos, registros del "
    "sistema, logs rotados y cache de pip. Se elevan con pkexec/polkit; la "
    "interfaz nunca se ejecuta como root.\n\n"
    "También puedes usarla por terminal:\n"
    "  <tt>limpialinux --list</tt>  lista las tareas\n"
    "  <tt>limpialinux --analyze</tt>  analiza el espacio recuperable\n"
    "  <tt>limpialinux --clean papelera,cache-usuario</tt>  limpia tareas\n"
    "  <tt>limpialinux --clean-all</tt>  limpia todas las seguras\n"
    "  <tt>limpialinux --version</tt>"
) % APP_NAME


def _license_text():
    """Devuelve el texto completo de la GPLv3 (instalado o del repo)."""
    candidates = (
        LICENSE_PATH,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "LICENSE"),
    )
    for p in candidates:
        try:
            with open(p) as f:
                return f.read()
        except OSError:
            continue
    return ("Licencia GPL-3.0-or-later.\n"
            "No se pudo leer el texto completo de la licencia.")


def _gui_excepthook(exc_type, exc, tb):
    """Captura excepciones en los manejadores de GTK (sino pasan desapercibidas)."""
    try:
        import traceback as _tb
        msg = "Fallo interno de la interfaz:\n%s" % exc
        log_error(msg)
        for line in "".join(_tb.format_exception(exc_type, exc, tb)).splitlines():
            log_error("  " + line)
        show_error(msg + "\n\nDetalle en: %s" % _error_log_path())
    except Exception:
        pass


def _error_log_path():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "limpialinux", "limpialinux.log")


def log_error(msg):
    """Escribe el error en ~/.cache/limpialinux/limpialinux.log."""
    try:
        os.makedirs(os.path.dirname(_error_log_path()), exist_ok=True)
        with open(_error_log_path(), "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def show_error(msg):
    """Muestra el error de forma visible (zenity/kdialog/notify) o por consola."""
    log_error(msg)
    tools = [
        (["zenity", "--error", "--text=%s" % msg], "zenity --error"),
        (["kdialog", "--error", msg], "kdialog --error"),
        (["notify-send", "--urgency=critical", APP_NAME, msg], "notify-send"),
    ]
    for args, name in tools:
        if shutil.which(name.split()[0]):
            try:
                subprocess.run(args, stdin=subprocess.DEVNULL,
                               timeout=8, check=False)
                return
            except Exception:
                pass
    print(msg, file=sys.stderr)


def _run(argv, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.STDOUT)
    kw.setdefault("env", dict(os.environ))
    return subprocess.run(argv, **kw)


def pkexec_available():
    return shutil.which("pkexec") is not None and os.path.exists(ROOT_HELPER)


def pkexec_run(argv, **kw):
    return _run(["pkexec", ROOT_HELPER] + argv, **kw)


# ------------------------------------------------------------- parte CLI

def _print_section(title, cats):
    print("== %s ==" % title)
    for c in cats:
        print("  %-24s %s" % (c["id"], c["nombre"]))
    print()


def cmd_list():
    print("Tareas de limpieza de %s:\n" % APP_NAME)
    _print_section("Usuario (sin permisos)", core.user_categories())
    _print_section("Sistema (requiere administrador)", core.system_categories())


def cmd_analyze():
    print("Analizando espacio recuperable...\n")
    total = 0
    rows = []
    for c in core.all_categories():
        try:
            size, count, det = c["scan"](None)
        except Exception as e:
            size, count, det = 0, 0, "error: %s" % e
        total += size
        rows.append((c, size, count, det))
        print("  %-24s %10s  %s" % (c["id"], core.fmt_size(size), c["nombre"]))
    print("\nTotal recuperable: %s" % core.fmt_size(total))
    return rows


def _clean_categories(cats, verbose=True):
    user = [c for c in cats if c["scope"] == "user"]
    system = [c for c in cats if c["scope"] == "system"]
    freed = 0
    for c in user:
        size, count, det = c["clean"](None)
        freed += size
        if verbose:
            print("  [ok] %s: %s (%s)" % (c["id"], det, core.fmt_size(size)))
    if system:
        if not pkexec_available():
            print("No se pudo elevar permisos (falta polkit o el helper).")
            return freed, 1
        ids = ",".join(c["id"] for c in system)
        if verbose:
            print("Solicitando permisos de administrador...")
        out = pkexec_run(["clean", ids])
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                if verbose:
                    print(" ", line)
                continue
            if obj.get("ok"):
                freed += int(obj.get("bytes", 0))
                if verbose:
                    print("  [ok] %s: %s (%s)" % (obj["id"], obj.get("detail", ""),
                                                  core.fmt_size(obj.get("bytes", 0))))
            else:
                if verbose:
                    print("  [!!] %s: %s" % (obj["id"], obj.get("detail", "error")))
    return freed, 0


def cmd_clean(ids, all_=False):
    cats = []
    if all_:
        for c in core.all_categories():
            if c["predeterminada"]:
                cats.append(c)
    else:
        for i in ids:
            c = core.by_id(i.strip())
            if c is None:
                print("Tarea desconocida: %s" % i.strip())
                continue
            cats.append(c)
    if not cats:
        print("No hay tareas seleccionadas.")
        return 1
    freed, code = _clean_categories(cats)
    print("\nEspacio liberado: %s" % core.fmt_size(freed))
    return code


# ------------------------------------------------------------ parte GUI

def run_gui(Gtk, Glib, Gio):
    class LimpiaWindow(Gtk.ApplicationWindow):
        def __init__(self, app):
            Gtk.ApplicationWindow.__init__(self, application=app,
                                           title=APP_NAME, default_width=780,
                                           default_height=660)
            self.set_border_width(0)
            self._busy = False
            self._rows = {}
            self._status_lbl = None
            self._disk_bar = None
            self._disk_txt = None
            self._progress = None
            self._log_buf = None

            self._build_header()
            self._build_body()
            # GTK3 no muestra los hijos por defecto: sin esto la ventana
            # aparece vacia.
            self.show_all()
            self.connect("delete-event", self._on_close)

        # --- construccion

        def _build_header(self):
            hb = Gtk.HeaderBar()
            hb.set_show_close_button(True)
            hb.props.title = APP_NAME
            hb.props.subtitle = "Limpieza de Zorin OS y Debian"
            self.set_titlebar(hb)

            clean = Gtk.Button.new_with_label("Limpiar")
            clean.get_style_context().add_class("suggested-action")
            clean.connect("clicked", self._on_clean_clicked)
            hb.pack_end(clean)

            for label, handler in (("Ayuda", self._on_help_clicked),
                                   ("Licencia", self._on_license_clicked),
                                   ("Autor", self._on_about_clicked)):
                btn = Gtk.Button.new_with_label(label)
                btn.connect("clicked", handler)
                hb.pack_end(btn)

        def _build_body(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_border_width(12)
            self.add(box)

            self._disk_txt = Gtk.Label(xalign=0)
            self._disk_txt.set_markup("<b>Disco:</b> analizando...")
            box.pack_start(self._disk_txt, False, False, 2)

            self._disk_bar = Gtk.ProgressBar()
            self._disk_bar.set_show_text(True)
            box.pack_start(self._disk_bar, False, False, 0)

            self._list = Gtk.ListBox()
            self._list.set_selection_mode(Gtk.SelectionMode.NONE)
            self._list.set_margin_top(6)
            self._add_section("Usuario (sin permisos)")
            for c in core.user_categories():
                self._add_row(c)
            self._add_section("Sistema (requiere administrador)")
            for c in core.system_categories():
                self._add_row(c)

            sc = Gtk.ScrolledWindow()
            sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sc.add(self._list)
            box.pack_start(sc, True, True, 0)

            exp = Gtk.Expander(label="Detalle de la operacion")
            self._log = Gtk.TextView()
            self._log.set_editable(False)
            self._log.set_cursor_visible(False)
            self._log_buf = self._log.get_buffer()
            log_sc = Gtk.ScrolledWindow()
            log_sc.set_min_content_height(130)
            log_sc.add(self._log)
            exp.add(log_sc)
            box.pack_start(exp, False, False, 0)

            self._progress = Gtk.ProgressBar()
            self._progress.set_pulse_step(0.05)
            box.pack_start(self._progress, False, False, 0)

            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self._status_lbl = Gtk.Label(xalign=0)
            bar.pack_start(self._status_lbl, True, True, 0)
            analyze = Gtk.Button.new_with_label("Analizar")
            analyze.connect("clicked", self._on_analyze_clicked)
            bar.pack_end(analyze, False, False, 0)
            box.pack_start(bar, False, False, 0)

            self._log_line("Bienvenido a %s. Selecciona tareas y pulsa Analizar." % APP_NAME)
            self._refresh_disk()
            Glib.idle_add(self.analyze)

        def _add_section(self, title):
            lbl = Gtk.Label(label=title)
            lbl.set_margin_top(10)
            lbl.set_xalign(0)
            lbl.get_style_context().add_class("dim-label")
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.add(lbl)
            self._list.add(row)

        def _add_row(self, c):
            main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            main.set_margin_top(6)
            main.set_margin_bottom(6)
            main.set_margin_start(10)
            main.set_margin_end(12)

            check = Gtk.CheckButton()
            check.set_active(c["predeterminada"])
            main.pack_start(check, False, False, 0)

            txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            name_lbl = Gtk.Label(xalign=0)
            name_lbl.set_markup("<b>%s</b>" % c["nombre"])
            desc = Gtk.Label(xalign=0, wrap=True, label=c["descripcion"])
            desc.get_style_context().add_class("dim-label")
            txt.pack_start(name_lbl, False, False, 0)
            txt.pack_start(desc, False, False, 0)
            main.pack_start(txt, True, True, 0)

            risk = Gtk.Label(label="")
            if c["riesgo"] == "medio":
                risk.set_markup('<span foreground="#b26a00">medio</span>')
            risk.set_margin_start(10)
            main.pack_start(risk, False, False, 0)

            size_lbl = Gtk.Label(label="?")
            size_lbl.set_width_chars(11)
            size_lbl.set_xalign(1)
            size_lbl.set_margin_start(8)
            main.pack_start(size_lbl, False, False, 0)

            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.add(main)
            row.show_all()
            self._list.add(row)
            self._rows[c["id"]] = {"check": check, "size": size_lbl,
                                   "cat": c, "state": "pending"}

        # --- utilidades

        def _log_line(self, msg):
            self._log_buf.insert(self._log_buf.get_end_iter(), msg + "\n")
            adj = self._log.get_vadjustment()
            Glib.idle_add(lambda: adj.set_value(adj.get_upper()))

        def _set_status(self, text, busy=False):
            self._status_lbl.set_text(text)
            if busy:
                self._progress.show()
                if getattr(self, "_busy_timer", None) is None:
                    self._busy_timer = Glib.timeout_add(80, self._pulse)
            else:
                self._progress.hide()
                timer = getattr(self, "_busy_timer", None)
                if timer is not None:
                    Glib.source_remove(timer)
                    self._busy_timer = None

        def _pulse(self):
            self._progress.pulse()
            return True

        def _selected(self):
            out = []
            for row in self._rows.values():
                if row["check"].get_active():
                    out.append(row["cat"])
            return out

        def _set_all_sizes(self, results):
            for cid, (size, count, ok) in results.items():
                row = self._rows.get(cid)
                if not row:
                    continue
                if not ok:
                    row["size"].set_text("?")
                    row["state"] = "error"
                else:
                    row["size"].set_text(core.fmt_size(size))
                    row["state"] = "done"

        def _refresh_disk(self):
            def work():
                try:
                    return shutil.disk_usage("/")
                except Exception:
                    return None

            def done(u):
                if not u:
                    self._disk_txt.set_text("No se pudo leer el disco.")
                    return
                total, used, free = u
                frac = used / total if total else 0

                def _f(n):
                    return core.fmt_size(n)

                self._disk_txt.set_markup(
                    "<b>Disco %s</b>  %s usados de %s  (libres: %s)" %
                    ("/", _f(used), _f(total), _f(free)))
                self._disk_bar.set_fraction(frac)
                self._disk_bar.set_text("%.0f%% usado" % (frac * 100))

            self._start_worker(work, done, "Disco")

        # ----------------------------------------------------------------

        def analyze(self):
            if self._busy:
                return
            self._busy = True
            self._set_status("Analizando espacio recuperable...", busy=True)
            for row in self._rows.values():
                row["size"].set_text("...")
                row["state"] = "pending"

            def work():
                results = {}
                for c in core.all_categories():
                    try:
                        size, count, det = c["scan"](None)
                        results[c["id"]] = (size, count, True)
                    except Exception as e:
                        results[c["id"]] = (0, 0, False)
                return results

            def done(results):
                self._set_all_sizes(results)
                total = sum(size for size, _c, ok in results.values() if ok)
                self._set_status("Analisis completado. Espacio recuperable: %s" %
                                 core.fmt_size(total))
                self._busy = False

            self._start_worker(work, done, "Analizar")

        def _start_worker(self, work, done, label):
            def wrapper():
                try:
                    res = work()
                    Glib.idle_add(done, res)
                except Exception as e:
                    def _fail():
                        self._set_status("Error en %s: %s" % (label, e))
                        self._busy = False
                    Glib.idle_add(_fail)

            threading.Thread(target=wrapper, daemon=True).start()

        def _on_analyze_clicked(self, _w):
            self.analyze()

        def _on_clean_clicked(self, _w):
            if self._busy:
                return
            cats = self._selected()
            if not cats:
                Gtk.MessageDialog(self, 0, Gtk.MessageType.WARNING,
                                  Gtk.ButtonsType.OK,
                                  "No hay nada seleccionado",
                                  "Marca al menos una tarea para limpiar.").run()
                return
            self._busy = True
            self._set_status("Limpiando...", busy=True)
            self._log_line("--- Iniciando limpieza ---")

            def work():
                return _clean_categories(cats, verbose=False)

            def done(res):
                freed, code = res
                self._set_status("Limpieza completada: %s liberados" %
                                 core.fmt_size(freed))
                self._log_line("Espacio liberado: %s" % core.fmt_size(freed))
                self._busy = False
                self.analyze()
                dlg = Gtk.MessageDialog(
                    self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                    "Limpieza completada",
                    "Se liberaron %s." % core.fmt_size(freed))
                dlg.run()
                dlg.destroy()

            self._start_worker(work, done, "Limpiar")

        def _on_help_clicked(self, _w):
            dlg = Gtk.MessageDialog(
                self, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO,
                Gtk.ButtonsType.OK, "Ayuda de %s" % APP_NAME)
            dlg.format_secondary_markup(HELP_TEXT)
            dlg.run()
            dlg.destroy()

        def _on_license_clicked(self, _w):
            dlg = Gtk.Dialog(title="Licencia de %s" % APP_NAME,
                             transient_for=self, modal=True)
            dlg.add_button("Cerrar", Gtk.ResponseType.CLOSE)
            box = dlg.get_content_area()
            box.set_border_width(12)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            sw.set_size_request(640, 460)
            tv = Gtk.TextView()
            tv.set_editable(False)
            tv.set_wrap_mode(Gtk.WrapMode.WORD)
            tv.set_left_margin(4)
            tv.set_right_margin(4)
            tv.get_buffer().set_text(_license_text())
            sw.add(tv)
            box.pack_start(sw, True, True, 0)
            box.show_all()
            dlg.set_default_size(660, 500)
            dlg.run()
            dlg.destroy()

        def _on_about_clicked(self, _w):
            dlg = Gtk.AboutDialog()
            dlg.set_transient_for(self)
            dlg.set_modal(True)
            dlg.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
            dlg.set_program_name(APP_NAME)
            dlg.set_version(VERSION)
            dlg.set_logo_icon_name(APP_NAME.lower())
            dlg.set_comments(
                "Limpieza de Zorin OS y sistemas basados en Debian.\n\n"
                "Creado por: %s\n%s\ncopyright (C) 2026 %s"
                % (AUTHOR, AUTHOR_ADDRESS, AUTHOR))
            dlg.set_copyright("Copyright (C) 2026 %s" % AUTHOR)
            dlg.set_website(HOMEPAGE)
            dlg.set_website_label("GitHub")
            dlg.set_authors([AUTHOR])
            dlg.set_license_type(Gtk.License.GPL_3_0_OR_LATER)
            dlg.run()
            dlg.destroy()

        def _on_close(self, *_):
            return False

    class LimpiaApp(Gtk.Application):
        def __init__(self):
            Gtk.Application.__init__(self, application_id=APP_ID)

        def do_startup(self):
            Gtk.Application.do_startup(self)
            Gtk.Window.set_default_icon_name(APP_NAME.lower())

        def do_activate(self):
            win = self.get_active_window()
            if win is None:
                win = LimpiaWindow(self)
            win.present()

    return LimpiaApp


# ------------------------------------------------------------ main

def build_parser():
    p = argparse.ArgumentParser(
        prog=APP_NAME.lower(),
        description="Limpieza de Zorin OS y sistemas basados en Debian.")
    p.add_argument("--gui", action="store_true", help="abre la interfaz grafica")
    p.add_argument("--list", action="store_true", help="lista las tareas")
    p.add_argument("--analyze", action="store_true",
                   help="analiza el espacio recuperable")
    p.add_argument("--clean", metavar="ID,ID,...",
                   help="limpia las tareas indicadas")
    p.add_argument("--clean-all", action="store_true",
                   help="limpia todas las tareas seguras")
    p.add_argument("--version", action="store_true", help="muestra la version")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.version:
        print("%s %s" % (APP_NAME, VERSION))
        return 0
    if args.list:
        return cmd_list() or 0
    if args.analyze:
        cmd_analyze()
        return 0
    if args.clean:
        return cmd_clean(args.clean.split(","))
    if args.clean_all:
        return cmd_clean([], all_=True)

    # GUI por defecto
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib, Gio
    except Exception as e:
        log_error("No se pudo cargar GTK (python3-gi/gir1.2-gtk-3.0): %s" % e)
        show_error(
            "No se pudo iniciar la interfaz grafica de %s.\n\n"
            "Motivo: %s\n\n"
            "Instala las dependencias y vuelve a intentarlo:\n"
            "  sudo apt install python3-gi gir1.2-gtk-3.0\n\n"
            "Detalle en: %s"
            % (APP_NAME, e, _error_log_path()))
        return 1

    sys.excepthook = _gui_excepthook

    try:
        app = run_gui(Gtk, GLib, Gio)()
        return app.run(sys.argv)
    except Exception as e:
        log_error("Fallo al iniciar la interfaz grafica: %s" % e)
        try:
            import traceback
        except Exception:
            traceback = None
        if traceback is not None:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                log_error("  " + line)
        show_error(
            "Fallo al iniciar la interfaz grafica de %s.\n\n"
            "Motivo: %s\n\n"
            "Detalle en: %s" % (APP_NAME, e, _error_log_path()))
        return 1


if __name__ == "__main__":
    sys.exit(main())