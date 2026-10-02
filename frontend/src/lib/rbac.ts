const GLOBAL_PERMISSION_MAP: Record<string, string[]> = {
  "projects:read": ["admin", "editor", "viewer"],
  "projects:write": ["admin"],
  "document_types:read": ["admin", "editor", "viewer"],
  "document_types:write": ["admin"],
  "documents:read": ["admin", "editor", "viewer"],
  "documents:write": ["admin", "editor"],
  "documents:approve": ["admin", "editor"],
  "api_keys:manage": ["admin"],
  "users:manage": ["admin"],
  "settings:read": ["admin"],
  "settings:write": ["admin"],
  "credentials:manage": ["admin"],
  "providers:manage": ["admin"],
  "processing:manage": ["admin"],
  "jobs:read": ["admin", "editor", "viewer"],
  "jobs:write": ["admin"],
};

export function can(role: string | undefined, permission: string): boolean {
  if (!role) return false;
  return GLOBAL_PERMISSION_MAP[permission]?.includes(role) ?? false;
}

const PROJECT_PERMISSION_MAP: Record<string, string[]> = {
  "projects:read": ["owner", "editor", "approver", "viewer"],
  "projects:write": ["owner", "editor"],
  "projects:delete": ["owner"],
  "document_types:read": ["owner", "editor", "approver", "viewer"],
  "document_types:write": ["owner", "editor"],
  "documents:read": ["owner", "editor", "approver", "viewer"],
  "documents:write": ["owner", "editor"],
  "documents:submit": ["owner", "editor"],
  "documents:approve": ["owner", "editor", "approver"],
  "documents:delete": ["owner", "editor"],
  "members:manage": ["owner", "editor"],
  "api_keys:manage": ["owner", "editor"],
  "subscriptions:manage": ["owner", "editor", "approver", "viewer"],
};

export function canOnProject(
  accessLevel: string | undefined,
  permission: string,
): boolean {
  if (!accessLevel) return false;
  return PROJECT_PERMISSION_MAP[permission]?.includes(accessLevel) ?? false;
}

export type Role = "admin" | "editor" | "viewer";
export type ProjectAccessLevel = "owner" | "editor" | "approver" | "viewer";
