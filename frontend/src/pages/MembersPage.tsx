import { motion } from "framer-motion";
import { Shield, UserCheck, UserMinus, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { useAuth } from "../contexts/AuthContext";

const API_BASE = "/api/v1";

interface Member {
  id: string;
  project_id: string;
  user_id: string;
  role: string;
  status: string;
  user_name: string | null;
  user_email: string | null;
}

interface UserInfo {
  id: string;
  name: string;
  email: string;
}

export function MembersPage({ projectId }: { projectId: string }) {
  const { token } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [allUsers, setAllUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showInvite, setShowInvite] = useState(false);
  const [inviteUserId, setInviteUserId] = useState("");
  const [inviteRole, setInviteRole] = useState("viewer");

  function headers() {
    return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
  }

  async function loadData() {
    setLoading(true);
    try {
      const [mRes, uRes] = await Promise.all([
        fetch(`${API_BASE}/projects/${projectId}/members`, { headers: headers() }),
        fetch(`${API_BASE}/auth/users`, { headers: headers() }),
      ]);
      if (mRes.ok) setMembers(await mRes.json());
      if (uRes.ok) setAllUsers(await uRes.json());
    } catch { /* ignore */ }
    setLoading(false);
  }

  useEffect(() => { loadData(); }, [projectId]);

  async function handleInvite() {
    if (!inviteUserId) return;
    setError("");
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}/invite`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ user_id: inviteUserId, role: inviteRole }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed" }))).detail);
      setShowInvite(false);
      setInviteUserId("");
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed");
    }
  }

  async function handleRemove(membershipId: string) {
    setError("");
    try {
      await fetch(`${API_BASE}/projects/members/${membershipId}`, {
        method: "DELETE",
        headers: headers(),
      });
      loadData();
    } catch { /* ignore */ }
  }

  async function handleChangeRole(membershipId: string, role: string) {
    setError("");
    try {
      await fetch(`${API_BASE}/projects/members/${membershipId}/role`, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify({ user_id: "", role }),
      });
      loadData();
    } catch { /* ignore */ }
  }

  const nonMembers = allUsers.filter(
    (u) => !members.some((m) => m.user_id === u.id)
  );

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Team Members</h2>
        <Button size="sm" onClick={() => setShowInvite(!showInvite)}>
          <UserPlus className="h-4 w-4" /> Invite
        </Button>
      </div>

      {error && (
        <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
      )}

      {showInvite && (
        <Card className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-surface-600 dark:text-surface-400 mb-1">User</label>
            <select
              value={inviteUserId}
              onChange={(e) => setInviteUserId(e.target.value)}
              className="w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
            >
              <option value="">Select user...</option>
              {nonMembers.map((u) => (
                <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-600 dark:text-surface-400 mb-1">Role</label>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <Button size="sm" onClick={handleInvite} disabled={!inviteUserId}>
            <UserPlus className="h-4 w-4" /> Send Invite
          </Button>
        </Card>
      )}

      {members.length === 0 ? (
        <p className="text-sm text-surface-400">No members yet.</p>
      ) : (
        <div className="space-y-2">
          {members.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="px-5 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                  <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
                      <UserCheck className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-surface-900 dark:text-surface-100">
                          {m.user_name ?? "Unknown"}
                        </span>
                        {m.status === "pending" && (
                          <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">pending</span>
                        )}
                        <span className="shrink-0 rounded-full bg-surface-100 px-2 py-0.5 text-[10px] font-medium text-surface-600 capitalize dark:bg-surface-700 dark:text-surface-300">{m.role}</span>
                      </div>
                      {m.user_email && (
                        <p className="mt-0.5 truncate text-xs text-surface-400">{m.user_email}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                  {m.role !== "owner" && (
                    <>
                      <select
                        value={m.role}
                        onChange={(e) => handleChangeRole(m.id, e.target.value)}
                        className="rounded-lg border border-surface-200 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                      >
                        <option value="viewer">Viewer</option>
                        <option value="editor">Editor</option>
                        <option value="editor">Editor</option>
                        <option value="admin">Admin</option>
                      </select>
                      <Button variant="ghost" size="sm" onClick={() => handleRemove(m.id)} title="Remove member">
                        <UserMinus className="h-4 w-4 text-accent-400 hover:text-accent-600" />
                      </Button>
                    </>
                  )}
                  {m.role === "owner" && (
                    <span className="flex items-center gap-1 text-xs text-surface-400">
                      <Shield className="h-3 w-3" /> Owner
                    </span>
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
