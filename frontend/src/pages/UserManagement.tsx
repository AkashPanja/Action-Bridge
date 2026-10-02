import { motion } from "framer-motion";
import { Plus, Shield, ShieldOff, Trash2, UserCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { useAuth } from "../contexts/AuthContext";
import type { User } from "../types";

const API_BASE = "/api/v1";

export function UserManagement() {
  const { token, user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState("viewer");
  const [creating, setCreating] = useState(false);

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };
  }

  async function loadUsers() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/users`, { headers: headers() });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed to load" }))).detail);
      setUsers(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadUsers(); }, []);

  async function toggleActive(u: User) {
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/users/${u.id}`, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify({ is_active: !u.is_active }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed" }))).detail);
      const updated: User = await res.json();
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
    }
  }

  async function changeRole(u: User, role: string) {
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/users/${u.id}`, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify({ role }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed" }))).detail);
      const updated: User = await res.json();
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/users`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ name: createName, email: createEmail, password: createPassword, role: createRole }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Create failed" }))).detail);
      setShowCreate(false);
      setCreateName(""); setCreateEmail(""); setCreatePassword("");
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
    setCreating(false);
  }

  async function handleDelete(u: User) {
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/users/${u.id}`, {
        method: "DELETE",
        headers: headers(),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Delete failed" }))).detail);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-surface-100">Users</h1>
          <p className="mt-1 text-sm text-surface-500">Manage user accounts and roles.</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> Create User
        </Button>
      </div>

      {error ? (
        <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
      ) : null}

      {showCreate && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Create New User</h3>
            <button onClick={() => setShowCreate(false)} className="text-surface-400 hover:text-surface-600"><X className="h-4 w-4" /></button>
          </div>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Name</label>
                <input required value={createName} onChange={(e) => setCreateName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100" />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Email</label>
                <input required type="email" value={createEmail} onChange={(e) => setCreateEmail(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100" />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Password</label>
                <input required type="password" minLength={8} value={createPassword} onChange={(e) => setCreatePassword(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100" />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Role</label>
                <select value={createRole} onChange={(e) => setCreateRole(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100">
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <Button type="submit" isLoading={creating}>
              <Plus className="h-4 w-4" /> Create User
            </Button>
          </form>
        </Card>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {users.map((u) => (
            <motion.div key={u.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="px-5 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                  <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${u.is_active ? "bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400" : "bg-surface-100 text-surface-400 dark:bg-surface-700"}`}>
                      <UserCheck className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-surface-900 dark:text-surface-100">{u.name}</span>
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${u.role === "admin" ? "bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300" : u.role === "editor" ? "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300" : "bg-surface-100 text-surface-600 dark:bg-surface-700 dark:text-surface-300"}`}>
                          {u.role}
                        </span>
                        {!u.is_active ? (
                          <span className="shrink-0 rounded-full bg-accent-100 px-2 py-0.5 text-[10px] font-medium text-accent-600 dark:bg-accent-900/30 dark:text-accent-400">inactive</span>
                        ) : null}
                      </div>
                      <p className="mt-0.5 truncate text-xs text-surface-400">{u.email}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                    <select
                      value={u.role}
                      onChange={(e) => changeRole(u, e.target.value)}
                      className="rounded-lg border border-surface-200 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                    >
                      <option value="admin">Admin</option>
                      <option value="editor">Editor</option>
                      <option value="viewer">Viewer</option>
                    </select>
                    <Button variant="ghost" size="sm" onClick={() => toggleActive(u)} title={u.is_active ? "Deactivate" : "Activate"}>
                      {u.is_active ? <ShieldOff className="h-4 w-4 text-accent-400" /> : <Shield className="h-4 w-4 text-emerald-400" />}
                    </Button>
                    {me?.id !== u.id && (
                      <Button variant="ghost" size="sm" onClick={() => handleDelete(u)} title="Delete user">
                        <Trash2 className="h-4 w-4 text-accent-400 hover:text-accent-600" />
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
