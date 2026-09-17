# LimpiaLinux

Aplicación de limpieza para **Zorin OS** y cualquier sistema basado en **Debian/Ubuntu**. Libera espacio en disco eliminando caches, papelera, paquetes huérfanos, kernels antiguos, registros del sistema y más, mediante una interfaz gráfica nativa (GTK3) y una línea de comandos.

Licencia **GPL-3.0-or-later**.

## Características

**Usuario (sin permisos de administrador):**

| Tarea | Descripción |
|-------|-------------|
| Papelera | Vacía la papelera de reciclaje del usuario actual |
| Cache de aplicaciones | Cache de todos los programas (`~/.cache`) |
| Miniaturas | Miniaturas de imágenes y documentos (`~/.cache/thumbnails`) |
| Caches de navegadores | Cache de Firefox, Chromium, Chrome, Edge, Brave… |
| Temporales de usuario | Ficheros temporales antiguos en `/tmp` y `/var/tmp` |

**Sistema (se eleva a administrador mediante pkexec/polkit, sin ejecutar la interfaz como root):**

| Tarea | Descripción |
|-------|-------------|
| Cache de apt | Paquetes `.deb` descargados por el gestor de paquetes |
| Descargas interrumpidas | Descargas incompletas en `partial/` |
| Paquetes huérfanos | Dependencias sin uso (`apt autoremove --purge`) |
| Kernels antiguos | Imágenes de kernel sin uso (se conservan el actual y el anterior) |
| Registros del sistema | Historial de journald (conserva los últimos 7 días) |
| Logs rotados | Logs de más de 7 días en `/var/log` |
| Cache de pip | Cache de Python/pip de todos los usuarios |

## Instalación

Descarga el paquete `.deb` desde [Releases](https://github.com/jmbernabeu/limpialinux/releases) y ejecuta:

```bash
sudo apt install ./limpialinux_1.0.0_all.deb
```

o con `dpkg`:

```bash
sudo dpkg -i limpialinux_1.0.0_all.deb
```

Dependencias necesarias (se instalan automáticamente): `python3`, `python3-gi`, `gir1.2-gtk-3.0` y `policykit-1`.

## Uso

Abre la aplicación desde el menú del sistema o ejecuta:

```bash
limpialinux                # interfaz gráfica
limpialinux --list         # lista las tareas
limpialinux --analyze      # analiza el espacio recuperable
limpialinux --clean papelera,cache-usuario
limpialinux --clean-all    # todas las tareas seguras
limpialinux --version
```

La primera vez que limpies tareas de **Sistema** se mostrará una pantalla de autenticación de administrador. La aplicación nunca se ejecuta como root.

## Compilar el paquete .deb

Desde este repositorio:

```bash
python3 build_deb.py               # genera dist/limpialinux_1.0.0_all.deb
python3 build_deb.py --version 1.1.0
```

No requiere `dpkg-deb` ni `debhelper`: se construye con la librería estándar de Python, por lo que se puede compilar en cualquier sistema.

## Estructura

```
├── core.py              # motor de limpieza (catálogo de tareas)
├── limpialinux.py       # interfaz gráfica (GTK3) y línea de comandos
├── root_helper.py       # helper privilegiado (pkexec), solo acepta tareas permitidas
├── build_deb.py         # generador del paquete .deb
├── assets/              # icono, lanzador .desktop y política polkit
└── .github/workflows/   # CI: compila y publica el .deb al hacer tag v*
```

## Seguridad

- La interfaz nunca se ejecuta como `root`; las tareas de sistema se elevan con `pkexec` y una política polkit propia.
- El helper privilegiado **solo acepta identificadores de tarea de una lista fija**, nunca rutas ni argumentos arbitrarios.
- Las tareas de riesgo medio (navegadores, autoremove, kernels) vienen desmarcadas por defecto.

## Repositorio

Código fuente y paquetes de release en [github.com/jmbernabeu/limpialinux](https://github.com/jmbernabeu/limpialinux).