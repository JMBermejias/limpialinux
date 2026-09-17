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

Descarga el paquete `.deb` desde [Releases](https://github.com/JMBermejias/limpialinux/releases) y ejecuta:

```bash
sudo apt install ./limpialinux_1.0.0_all.deb
```

o con `dpkg`:

```bash
sudo dpkg -i limpialinux_1.0.0_all.deb
```

Dependencias necesarias (se instalan automáticamente): `python3`, `python3-gi`, `gir1.2-gtk-3.0` y `policykit-1`.

### Instalación desde menú visual o tienda

El paquete incluye metadatos **AppStream** (`org.jmbernabeu.LimpiaLinux.metainfo.xml`) con la **licencia GPL-3.0-or-later**, el desarrollador **Jose Manuel Bernabeu Mejias** y el icono propio. Por eso, al abrirlo con Zorin Software, Ubuntu Software o cualquier instalador de `.deb`, se muestra la licencia, el autor y el icono de forma correcta.

Se puede instalar abriendo el fichero `.deb` directamente:

```bash
gnome-software ./limpialinux_1.0.0_all.deb
```

### Repositorio apt oficial (firmado)

Para instalar y recibir actualizaciones desde un repositorio firmado (Zorin Software lo mostrará como fuente firmada):

```bash
sudo install -d -m 0755 /usr/share/keyrings
curl -fsSL https://JMBermejias.github.io/limpialinux/limpialinux.gpg \
  | sudo tee /usr/share/keyrings/limpialinux.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/limpialinux.gpg] https://JMBermejias.github.io/limpialinux/ stable main" \
  | sudo tee /etc/apt/sources.list.d/limpialinux.list >/dev/null
sudo apt update
sudo apt install limpialinux
```

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
python3 build_deb.py               # genera dist/limpialinux_1.0.0_all.deb firmado
python3 build_deb.py --no-sign     # sin firma gpg
python3 build_deb.py --version 1.1.0
```

No requiere `dpkg-deb` ni `debhelper`: se construye con la librería estándar de Python, por lo que se puede compilar en cualquier sistema.

## Autenticidad y firma

Cada `.deb` publicado está **firmado por Jose Manuel Bernabeu Mejias** con una firma embebida compatible con `dpkg-sig` (miembro `_gpgbuilder`, formato v4). La clave pública es `65E47AE0C97A8D837493584A82EDEF9F1E4AF32C`:

```bash
gpg --show-keys assets/pubkey.asc
```

Para verificar un paquete:

```bash
# con dpkg-sig (Debian/Ubuntu: sudo apt install dpkg-sig)
dpkg-sig --verify limpialinux_1.0.0_all.deb

# sin instalar nada más (usa gpg)
python3 verify_deb.py dist/limpialinux_1.0.0_all.deb
```

El repositorio apt firmado se regenera con:

```bash
python3 build_repo.py   # genera repo/ con Release, InRelease y Release.gpg firmados
```

## Estructura

```
├── core.py              # motor de limpieza (catálogo de tareas)
├── limpialinux.py       # interfaz gráfica (GTK3) y línea de comandos
├── root_helper.py       # helper privilegiado (pkexec), solo acepta tareas permitidas
├── build_deb.py         # generador del paquete .deb (firma gpg embebida)
├── build_repo.py        # generador del repositorio apt firmado
├── verify_deb.py        # comprobador de la firma de un .deb
├── bump_version.py      # incremento de versión (pyproject.toml + código)
├── assets/pubkey.asc    # clave pública del autor (firma)
└── .github/workflows/   # CI: build+release automáticos en cada cambio
```

## Solución de problemas

Si al pulsar el icono la aplicación no se abre, ejecútala desde un terminal para ver el error exacto:

```bash
limpialinux
```

- **`No se pudo cargar GTK`**: faltan dependencias. Instálalas con
  `sudo apt install python3-gi gir1.2-gtk-3.0` (renueva el `.deb` si lo
  instalaste con `dpkg -i` sin gestionar dependencias).
- El detalle de cualquier error de arranque queda registrado en
  `~/.cache/limpialinux/limpialinux.log`.

## Seguridad

- La interfaz nunca se ejecuta como `root`; las tareas de sistema se elevan con `pkexec` y una política polkit propia.
- El helper privilegiado **solo acepta identificadores de tarea de una lista fija**, nunca rutas ni argumentos arbitrarios.
- Las tareas de riesgo medio (navegadores, autoremove, kernels) vienen desmarcadas por defecto.

## Repositorio

Código fuente y paquetes de release en [github.com/JMBermejias/limpialinux](https://github.com/JMBermejias/limpialinux).