"""Metadata about available tools for the executor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    acl_tag: str
    side_effect: bool = False
    idempotent: bool = True


TOOL_METADATA: Dict[str, ToolMetadata] = {
    "files.list": ToolMetadata("files.list", acl_tag="fs.read", side_effect=False, idempotent=True),
    "files.read": ToolMetadata("files.read", acl_tag="fs.read", side_effect=False, idempotent=True),
    "files.create": ToolMetadata("files.create", acl_tag="fs.write", side_effect=True, idempotent=False),
    "files.append": ToolMetadata("files.append", acl_tag="fs.write", side_effect=True, idempotent=False),
    "files.open": ToolMetadata("files.open", acl_tag="fs.desktop", side_effect=True, idempotent=False),
    "files.reveal": ToolMetadata("files.reveal", acl_tag="fs.desktop", side_effect=True, idempotent=False),
    "files.shortcut_to_desktop": ToolMetadata(
        "files.shortcut_to_desktop", acl_tag="fs.desktop", side_effect=True, idempotent=False
    ),
    "system.help": ToolMetadata("system.help", acl_tag="system", side_effect=False, idempotent=True),
    "system.config_get": ToolMetadata("system.config_get", acl_tag="system", side_effect=False, idempotent=True),
    "system.config_set": ToolMetadata("system.config_set", acl_tag="system", side_effect=True, idempotent=False),
}


def get_tool_metadata(name: str) -> ToolMetadata | None:
    return TOOL_METADATA.get(name)
