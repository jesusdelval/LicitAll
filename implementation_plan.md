# Plan de Implementación — Publicación en GitHub y Auto-Actualizador (estilo ProfitAll)

## 1. Objetivo del cambio

Preparar **LicitAll** para publicarlo en tu cuenta de GitHub (`jesusdelval/LicitAll`) e incorporar el mismo sistema de **lanzador visual (Splash Screen) + comprobación y despliegue automático de actualizaciones desde GitHub** que utiliza **ProfitAll**, preservando siempre tus datos locales (`licitall.db`) y archivos de configuración.

---

## 2. Archivos afectados

- `.gitignore` — Excluir `licitall.db`, `__pycache__/`, `.pytest_cache/`, ficheros `.XLSX`, `github_sync_config.json` y logs locales para no subir datos personales ni secretos a GitHub.
- `version.json` — Registro de la versión actual de la aplicación (`1.0.0`).
- `github_sync_config.example.json` — Plantilla de configuración del actualizador (`repo: "jesusdelval/LicitAll"`, `branch: "main"`, `token: ""` opcional si el repo es privado).
- `scripts/actualizar.py` — Comprobador y descargador automático desde GitHub (soporte para repositorio público o privado con token y fallback con proxy corporativo vía PowerShell, respetando `licitall.db` y `github_sync_config.json`).
- `scripts/launcher.py` — Lanzador visual sin consola negra (`pythonw.exe`) con barra magenta corporativa que al abrir:
  1. Comprueba si hay una versión/commit más reciente en GitHub.
  2. Si hay actualización, descarga y despliega los archivos nuevos automáticamente (o pide confirmación).
  3. Arranca el servidor local de LicitAll y abre el navegador.
- `LicitAll.bat` — Actualizado para lanzar `scripts/launcher.py` con `pythonw.exe` (sin ventana negra de terminal).

---

## 3. Fases del trabajo

1. **Fase 1: Preparación del repositorio Git local**
   - Crear `.gitignore` y `version.json`, inicializar el repositorio Git local (`git init` en rama `main`) y realizar el commit inicial limpio con el código de LicitAll.
2. **Fase 2: Motor de actualización desde GitHub (`scripts/actualizar.py`)**
   - Adaptar el actualizador de ProfitAll para `LicitAll` (soporte para repo público sin token y repo privado con token en `github_sync_config.json`), excluyendo `licitall.db` y ficheros locales al desplegar el ZIP de GitHub.
3. **Fase 3: Lanzador visual (`scripts/launcher.py` y `LicitAll.bat`)**
   - Crear la pantalla de arranque corporativa (Tkinter) que muestra el estado (*Comprobando actualización...*, *Descargando actualización...*, *Iniciando servidor local...*) y arranca `run.py` en segundo plano.
4. **Fase 4: Verificación y subida a GitHub**
   - Ejecutar `pytest` y probar el arranque del lanzador y la comprobación de versión.
   - Conectar el remoto `origin` a `https://github.com/jesusdelval/LicitAll.git` y hacer `git push -u origin main` una vez creado el repositorio en GitHub.

---

## 4. Criterios de aceptación

- El repositorio local tiene un `.gitignore` válido que excluye `licitall.db`, Excel locales y credenciales.
- Al abrir `LicitAll.bat`, se muestra el splash visual sin consola negra, comprueba actualizaciones en `jesusdelval/LicitAll`, despliega cambios si los hay y abre el portal en el navegador.
- La base de datos `licitall.db` (licitaciones, favoritas y filtros guardados) permanece intacta tras una actualización.
- Las pruebas automáticas (`python -m pytest -v`) siguen pasando al 100%.
