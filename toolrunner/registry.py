from typing import Callable, Dict, Any

from toolrunner.tools.files import (
    cmd_files_list,
    cmd_files_read,
    cmd_files_create,
    cmd_files_append,
    cmd_files_open,
    cmd_files_reveal,
    cmd_files_shortcut,
)
from toolrunner.tools.system import (
    cmd_system_help,
    cmd_system_config_get,
    cmd_system_config_set,
)

# Белый список команд (контролируется тут же)
ALLOWED_COMMANDS = {
    "files.list",
    "files.read",
    "files.create",
    "files.append",
    "files.open",
    "files.reveal",
    "files.shortcut_to_desktop",
    "system.help",
    "system.config_get",
    "system.config_set",
}

# Реестр: имя команды -> функция (args, config) -> Any
REGISTRY: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {
    "files.list": cmd_files_list,
    "files.read": cmd_files_read,
    "files.create": cmd_files_create,
    "files.append": cmd_files_append,
    "files.open": cmd_files_open,
    "files.reveal": cmd_files_reveal,
    "files.shortcut_to_desktop": cmd_files_shortcut,
    "system.help": cmd_system_help,
    "system.config_get": cmd_system_config_get,
    "system.config_set": cmd_system_config_set,
}
