# Nexo

## Raíz y permisos de archivos

Al ejecutar la API directamente, la raíz predeterminada es la carpeta personal del usuario del sistema (`Path.home()`): normalmente `/home/usuario` en Linux y `C:\Users\usuario` en Windows. `.` en las herramientas representa esa carpeta. Se respetan los permisos del sistema operativo. Puedes elegir otra ruta con `WORKSPACE_ROOT=/mi_usuario/home` o `WORKSPACE_ROOT=C:/Users/usuario` en `.env`; también se admite `~`.

`WORKSPACE_SCOPE=shared` utiliza directamente esa raíz, compartida por las cuentas autenticadas de esta instalación. Para mantener espacios separados por cuenta, configura `WORKSPACE_SCOPE=per_user`: cada cuenta usa `<raíz>/<UUID>`. La carpeta personal corresponde al usuario que ejecuta la API, no al usuario del navegador.

Los listados omiten todos los archivos y carpetas cuyo nombre empieza con `.`, también al listar subcarpetas. Esta regla de presentación no modifica los permisos de acceso directo por ruta.

Los permisos se definen en `workspace_rules.json`, o en el archivo indicado por `WORKSPACE_RULES_FILE`. De forma predeterminada solo se permite listar y leer. Ejemplo para habilitar cambios en `Documents/ChatBot` y bloquear una carpeta privada:

```json
{
  "default_allow": ["list", "read"],
  "rules": [
    {"path": "Documents/ChatBot", "allow": ["create", "edit"]},
    {"path": "Documents/privado", "deny": ["list", "read", "create", "edit", "delete"]}
  ]
}
```

Las acciones válidas son `list`, `read`, `create`, `edit` y `delete`. Cada `path` es una ruta relativa exacta, escrita con `/` en ambos sistemas; se aplica también a todos sus descendientes. `.` aplica a toda la raíz. Los nombres deben coincidir con los reales (por ejemplo, `Documentos` en lugar de `Documents` si esa es tu carpeta). En Windows la comparación ignora mayúsculas. Una denegación tiene prioridad sobre cualquier permiso, sin importar el orden. No se utilizan patrones glob.

Las reglas se cargan en cada pedido y al confirmar una propuesta. Un archivo configurado ausente o inválido bloquea las herramientas. Crear, editar y eliminar siguen requiriendo confirmación en la interfaz; editar un archivo existente también requiere permiso de lectura para mostrar el diff. Una eliminación de carpeta valida todos sus descendientes. Las reglas no habilitan acceso fuera de la raíz, enlaces simbólicos, junctions de Windows, archivos protegidos ni modificaciones del propio archivo de reglas. No habilitan ejecución de comandos.

## Carpeta personal con Docker

La configuración habitual monta la carpeta personal del equipo en `/workspace`, usa el modo compartido y monta las reglas como solo lectura. Detecta `HOME` en Linux o `USERPROFILE` en Windows; `WORKSPACE_HOST_ROOT` permite elegir otra carpeta. Dentro del contenedor, `.` representa el contenido de esa carpeta personal.

En Linux, desde el directorio del proyecto:

```sh
export WORKSPACE_HOST_ROOT="$HOME"
export WORKSPACE_UID="$(id -u)"
export WORKSPACE_GID="$(id -g)"
docker compose up -d --build
```

En Windows con Docker Desktop y PowerShell:

```powershell
$env:WORKSPACE_HOST_ROOT = $env:USERPROFILE
docker compose up -d --build
```

Para usar `/mi_usuario/home`, sustituye el valor de `WORKSPACE_HOST_ROOT` por esa ruta. La carpeta debe existir y Docker debe tener acceso a ella. Puedes guardar `WORKSPACE_HOST_ROOT`, `WORKSPACE_UID` y `WORKSPACE_GID` en `.env` para conservarlos entre reinicios. Los cambios de reglas montadas se toman en el siguiente pedido sin reconstruir la imagen. `docker-compose.home.yml` se conserva como alternativa compatible con los comandos anteriores.

## Conversaciones

La barra lateral muestra los chats por su primer mensaje, ordenados por actividad reciente. Permite buscar por título y resalta la conversación activa. Los chats sin mensajes aparecen como «Nueva conversación».

Cada inicio de sesión abre una conversación nueva. Las conversaciones anteriores siguen disponibles en la barra lateral.

El historial agrupa los chats por fecha y recoge los chats vacíos anteriores en «Chats sin mensajes». La bienvenida ofrece ideas que se copian al campo de mensaje para editarlas antes de enviarlas. Los controles de recuerdos y cuenta están en secciones plegables. El tema se configura en `.streamlit/config.toml` y los ajustes de presentación en `ui.css`.

Las fechas se muestran en la zona horaria `America/Argentina/Buenos_Aires`. Para cambiarla, configura `UI_TIMEZONE` con un nombre de zona IANA. Los títulos se obtienen al consultar las conversaciones; no requieren una migración de base de datos.

## Legacy memory ownership

The initial schema stored `agent_memories.user_id` as free-form text (for example, `default_user`) and did not retain a trustworthy link to an authenticated account. The authentication migration therefore does not guess an owner: those rows are preserved for retention/audit, but the authenticated memory API only matches the UUID from the active user's JWT. Legacy rows remain intentionally inaccessible to user-scoped conversations until an explicit ownership mapping is supplied.

To verify this policy, inspect the legacy rows with `SELECT user_id, COUNT(*) FROM agent_memories GROUP BY user_id`; authenticated searches must use `WHERE user_id = '<active-user-uuid>'` and must not fall back to `default_user` or another textual identifier.
