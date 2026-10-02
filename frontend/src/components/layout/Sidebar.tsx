import { Bell, FileCode, FolderKanban, GitCompareArrows, LogOut, Plus, Settings, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { useProjects } from "../../hooks/useProjects";
import { can } from "../../lib/rbac";
import { cn } from "../../lib/utils";

const API_BASE = "/api/v1";

export function Sidebar({ open = true, onClose = () => {} }: { open?: boolean; onClose?: () => void }) {
  const { projectId } = useParams();
  const { data: projects } = useProjects();
  const { user, logout, token } = useAuth();
  const [pendingInvites, setPendingInvites] = useState(0);

  useEffect(() => {
    if (!token) return;
    async function fetchInvites() {
      try {
        const res = await fetch(`${API_BASE}/invitations`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setPendingInvites(data.length);
        }
      } catch { /* ignore */ }
    }
    fetchInvites();
    const interval = setInterval(fetchInvites, 30000);
    return () => clearInterval(interval);
  }, [token]);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex h-full w-64 shrink-0 flex-col border-r border-surface-200/60 bg-white backdrop-blur-xl transition-transform duration-300",
        "dark:border-surface-700/50 dark:bg-surface-900",
        open ? "translate-x-0" : "-translate-x-full",
        "md:static md:z-auto md:translate-x-0 md:bg-white/50 md:dark:bg-surface-900/50",
      )}
      onClick={onClose}
    >
      <div className="flex items-center gap-2.5 border-b border-surface-200/60 px-5 py-3 dark:border-surface-700/50" onClick={onClose}>
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-[#1b2cc7] to-[#2f7de9] shadow-md shadow-brand-600/25">
          <GitCompareArrows className="h-4 w-4 text-white" />
        </div>
        <span className="text-sm font-bold text-surface-900 dark:text-surface-100">
          Action Bridge
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        <div className="mb-2 flex items-center justify-between px-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500">
            Projects
          </span>
        </div>

        <nav className="space-y-0.5">
          {projects?.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                "text-surface-600 hover:bg-surface-100 hover:text-surface-900",
                "dark:text-surface-400 dark:hover:bg-surface-700/50 dark:hover:text-surface-100",
                projectId === project.id &&
                  "bg-brand-50 text-brand-700 hover:bg-brand-50 hover:text-brand-700 dark:bg-brand-900/20 dark:text-brand-300 dark:hover:bg-brand-900/20 dark:hover:text-brand-300",
              )}
            >
              <FolderKanban className="h-4 w-4 shrink-0" />
              <span className="truncate">{project.name}</span>
            </Link>
          ))}
        </nav>
      </div>

      <div className="border-t border-surface-200/60 p-3 space-y-1 dark:border-surface-700/50">
        <Link
          to="/"
          className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700/50 dark:hover:text-surface-200"
        >
          <Plus className="h-4 w-4" />
          All Projects
        </Link>
        {user && can(user.role, "users:manage") ? (
          <>
            <Link
              to="/users"
              className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700/50 dark:hover:text-surface-200"
            >
              <Users className="h-4 w-4" />
              Users
            </Link>
            <Link
              to="/settings"
              className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700/50 dark:hover:text-surface-200"
            >
              <Settings className="h-4 w-4" />
              Settings
            </Link>
            <Link
              to="/validation-patterns"
              className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700/50 dark:hover:text-surface-200"
            >
              <FileCode className="h-4 w-4" />
              Validation Patterns
            </Link>
          </>
        ) : null}

        {user ? (
          <div className="rounded-xl bg-surface-100/50 px-3 py-2 dark:bg-surface-700/30">
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-xs font-medium text-surface-700 dark:text-surface-200">
                    {user.name}
                  </p>
                  {pendingInvites > 0 && (
                    <span className="flex items-center gap-1 rounded-full bg-accent-100 px-2 py-0.5 text-[9px] font-medium text-accent-600 dark:bg-accent-900/30 dark:text-accent-400">
                      <Bell className="h-2.5 w-2.5" />
                      {pendingInvites}
                    </span>
                  )}
                </div>
                <p className="truncate text-xs text-surface-400 capitalize">{user.role}</p>
              </div>
              <button
                onClick={logout}
                className="rounded-lg p-1.5 text-surface-400 transition-colors hover:bg-surface-200 hover:text-accent-500 dark:hover:bg-surface-600"
                title="Logout"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
