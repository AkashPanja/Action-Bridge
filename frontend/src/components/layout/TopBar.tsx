import { Bell, KeyRound, Menu, Moon, Sun } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { useTheme } from "../../contexts/ThemeContext";
import { cn } from "../../lib/utils";

const API_BASE = "/api/v1";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  document_id: string | null;
  is_read: boolean;
  created_at: string;
}

export function TopBar({ onMenuClick = () => {} }: { onMenuClick?: () => void }) {
  const { dark, toggleTheme } = useTheme();
  const location = useLocation();
  const { token, user } = useAuth();
  const [companyName, setCompanyName] = useState("Action Bridge");
  const [companyLogo, setCompanyLogo] = useState("");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifs, setShowNotifs] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwSuccess, setPwSuccess] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    fetchNotifications();
    fetch(`${API_BASE}/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data?.company) {
          setCompanyName(data.company.name || "Action Bridge");
          setCompanyLogo(data.company.logo || "");
        }
      })
      .catch(() => {});
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [token]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifs(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function fetchNotifications() {
    try {
      const res = await fetch(`${API_BASE}/notifications?limit=10`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setNotifications(data);
        setUnreadCount(data.filter((n: Notification) => !n.is_read).length);
      }
    } catch { /* ignore */ }
  }

  async function markRead(id: string) {
    await fetch(`${API_BASE}/notifications/${id}/read`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchNotifications();
  }

  async function markAllRead() {
    await fetch(`${API_BASE}/notifications/mark-all-read`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchNotifications();
  }

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault();
    setPwError("");
    setPwSuccess("");
    setPwLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/me/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail);
      }
      setPwSuccess("Password changed successfully.");
      setOldPassword("");
      setNewPassword("");
      setTimeout(() => setShowPasswordModal(false), 1000);
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Failed");
    }
    setPwLoading(false);
  }

  const crumbs = location.pathname
    .split("/")
    .filter(Boolean)
    .map((seg, i, arr) => ({
      label: seg.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      href: "/" + arr.slice(0, i + 1).join("/"),
      current: i === arr.length - 1,
    }));

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-surface-200/60 bg-white/50 px-4 backdrop-blur-xl dark:border-surface-700/50 dark:bg-surface-900/50 md:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <button
          onClick={onMenuClick}
          className="shrink-0 rounded-xl p-2 text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700 dark:hover:text-surface-200 md:hidden"
          title="Open menu"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <nav className="flex min-w-0 items-center gap-2 overflow-hidden text-sm">
          <Link to="/" className="hidden shrink-0 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 sm:block">Home</Link>
          {crumbs.map((crumb) => (
            <span key={crumb.href} className={cn("flex min-w-0 items-center gap-2", !crumb.current && "hidden sm:flex")}>
              <span className="shrink-0 text-surface-300 dark:text-surface-600">/</span>
              <Link
                to={crumb.href}
                className={cn(
                  "truncate capitalize transition-colors",
                  crumb.current
                  ? "font-medium text-surface-900 dark:text-surface-100"
                  : "text-surface-400 hover:text-surface-600 dark:hover:text-surface-300",
              )}
            >
              {crumb.label}
            </Link>
          </span>
        ))}
        </nav>
      </div>

      <div className="absolute left-1/2 hidden max-w-[32vw] -translate-x-1/2 items-center gap-2 min-[500px]:flex">
        {companyLogo ? (
          <img src={companyLogo} alt={companyName} className="h-6 w-6 shrink-0 rounded object-contain" />
        ) : null}
        <span className="truncate text-sm font-semibold text-surface-800 dark:text-surface-200">{companyName}</span>
      </div>

      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        <button
          onClick={() => setShowPasswordModal(true)}
          className="rounded-xl p-2 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600 dark:hover:bg-surface-700 dark:hover:text-surface-300"
          title="Change Password"
        >
          <KeyRound className="h-4 w-4" />
        </button>

        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setShowNotifs(!showNotifs)}
            className="relative rounded-xl p-2 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600 dark:hover:bg-surface-700 dark:hover:text-surface-300"
            title="Notifications"
          >
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute right-1.5 top-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent-500 px-1 text-[10px] font-bold leading-none text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {showNotifs && (
            <div className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2.5rem)] rounded-xl border border-surface-200 bg-white shadow-lg backdrop-blur-xl dark:border-surface-700 dark:bg-surface-900">
              <div className="flex items-center justify-between border-b border-surface-200 px-4 py-3 dark:border-surface-700">
                <span className="text-sm font-semibold text-surface-900 dark:text-surface-100">Notifications</span>
                {unreadCount > 0 && (
                  <button onClick={markAllRead} className="text-xs font-medium text-accent-500 hover:text-accent-600">
                    Mark all read
                  </button>
                )}
              </div>
              <div className="max-h-72 overflow-y-auto">
                {notifications.length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-surface-400">No notifications</p>
                ) : (
                  notifications.map((n) => (
                    <button
                      key={n.id}
                      onClick={() => markRead(n.id)}
                      className={`w-full px-4 py-3 text-left text-sm transition-colors hover:bg-surface-50 dark:hover:bg-surface-800 ${
                        !n.is_read ? "bg-accent-50/50 dark:bg-accent-900/10" : ""
                      }`}
                    >
                      <p className="font-medium text-surface-900 dark:text-surface-100">{n.title}</p>
                      {n.message && <p className="mt-0.5 text-xs text-surface-500 line-clamp-2">{n.message}</p>}
                      <p className="mt-1 text-[10px] text-surface-400">
                        {new Date(n.created_at).toLocaleDateString()}
                      </p>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        <button
          onClick={toggleTheme}
          className="rounded-xl p-2 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600 dark:hover:bg-surface-700 dark:hover:text-surface-300"
        >
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>

      {showPasswordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-md max-h-[90vh] overflow-y-auto rounded-2xl border border-surface-200 bg-white p-6 shadow-xl dark:border-surface-700 dark:bg-surface-800">
            <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-100">Change Password</h2>
            <form onSubmit={handlePasswordChange} className="mt-4 space-y-4">
              {pwError && <p className="text-sm text-accent-500">{pwError}</p>}
              {pwSuccess && <p className="text-sm text-emerald-500">{pwSuccess}</p>}
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Current Password</label>
                <input
                  type="password"
                  required
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-700 dark:text-surface-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">New Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-700 dark:text-surface-100"
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={pwLoading}
                  className="flex-1 rounded-xl bg-accent-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-600 disabled:opacity-50"
                >
                  {pwLoading ? "Changing..." : "Change Password"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowPasswordModal(false); setPwError(""); setPwSuccess(""); }}
                  className="rounded-xl border border-surface-300 px-4 py-2 text-sm font-medium text-surface-600 transition-colors hover:bg-surface-50 dark:border-surface-600 dark:text-surface-400 dark:hover:bg-surface-700"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </header>
  );
}
