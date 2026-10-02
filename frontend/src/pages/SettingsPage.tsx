import { AlertTriangle, Building2, KeyRound, Mail, Save, Send, Trash2, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { LogoCropper } from "../components/settings/LogoCropper";
import { useAuth } from "../contexts/AuthContext";

const API_BASE = "/api/v1";

type Tab = "company" | "smtp" | "password" | "danger";

interface CompanySettings {
  name: string;
  logo: string;
}

interface SmtpConfig {
  host: string;
  port: number;
  username: string;
  password: string;
  from_email: string;
  use_tls: boolean;
}

interface PasswordPolicy {
  min_length: number;
  require_uppercase: boolean;
  require_lowercase: boolean;
  require_numbers: boolean;
  require_symbols: boolean;
}

interface AppSettings {
  company: CompanySettings;
  smtp: SmtpConfig;
  password_policy: PasswordPolicy;
}

const DEFAULTS: AppSettings = {
  company: { name: "Action Bridge", logo: "" },
  smtp: { host: "", port: 587, username: "", password: "", from_email: "", use_tls: true },
  password_policy: { min_length: 8, require_uppercase: true, require_lowercase: true, require_numbers: true, require_symbols: false },
};

export function SettingsPage() {
  const { token, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("company");
  const [settings, setSettings] = useState<AppSettings>(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Danger zone state
  const [confirmText, setConfirmText] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  // Logo state
  const [cropSrc, setCropSrc] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }

  async function saveSettings() {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const body: Record<string, unknown> = {};
      if (tab === "company") body.company = settings.company;
      if (tab === "smtp") body.smtp = { ...settings.smtp };
      if (tab === "password") body.password_policy = settings.password_policy;

      const res = await fetch(`${API_BASE}/settings`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Save failed" }));
        throw new Error(err.detail);
      }
      const updated = await res.json();
      setSettings(updated);
      setSuccess("Settings saved successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
    setSaving(false);
  }

  async function sendTestEmail() {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const res = await fetch(`${API_BASE}/settings/test-email`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed" }))).detail);
      setSuccess("Test email sent!");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send test email");
    }
    setSaving(false);
  }

  const MAX_LOGO_BYTES = 2 * 1024 * 1024;

  function handleLogoSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    setSuccess("");
    if (!file.type.startsWith("image/")) {
      setError("Please choose an image file (PNG or JPG).");
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      setError("Logo must be under 2 MB. Please compress or crop it first.");
      return;
    }
    if (cropSrc) URL.revokeObjectURL(cropSrc);
    setCropSrc(URL.createObjectURL(file));
  }

  function closeCropper() {
    if (cropSrc) URL.revokeObjectURL(cropSrc);
    setCropSrc(null);
  }

  async function handleCroppedLogo(blob: Blob, width: number, height: number) {
    const url = cropSrc;
    setCropSrc(null);
    if (url) URL.revokeObjectURL(url);
    setLogoUploading(true);
    setError("");
    setSuccess("");
    try {
      const fd = new FormData();
      fd.append("file", new File([blob], "logo.png", { type: "image/png" }));
      const res = await fetch(`${API_BASE}/settings/logo`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Logo upload failed" }));
        throw new Error(err.detail || "Logo upload failed");
      }
      const data = await res.json();
      setSettings((prev) => ({ ...prev, company: { ...prev.company, logo: data.logo } }));
      setSuccess(`Logo uploaded (${width} × ${height} px).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
    setLogoUploading(false);
  }

  async function handleReset() {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Reset failed" }));
        throw new Error(err.detail);
      }
      logout();
      navigate("/setup", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
      setLoading(false);
    }
  }

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "company", label: "Company", icon: <Building2 className="h-4 w-4" /> },
    { key: "smtp", label: "SMTP", icon: <Mail className="h-4 w-4" /> },
    { key: "password", label: "Password Policy", icon: <KeyRound className="h-4 w-4" /> },
    { key: "danger", label: "Danger Zone", icon: <Trash2 className="h-4 w-4" /> },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-bold text-surface-900 dark:text-surface-100">Settings</h1>
        <p className="mt-1 text-sm text-surface-500">Manage system configuration.</p>
      </div>

      <div className="flex gap-1 overflow-x-auto rounded-xl bg-surface-100 p-1 dark:bg-surface-800">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all sm:px-4 ${
              tab === t.key
                ? "bg-white text-surface-900 shadow-sm dark:bg-surface-700 dark:text-surface-100"
                : "text-surface-500 hover:text-surface-700 dark:text-surface-400 dark:hover:text-surface-200"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
      )}
      {success && (
        <p className="rounded-xl bg-emerald-50 px-4 py-2 text-sm text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400">{success}</p>
      )}

      {tab === "company" && (
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-surface-900 dark:text-surface-100">Company Settings</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Company Name</label>
              <input
                value={settings.company.name}
                onChange={(e) => setSettings((p) => ({ ...p, company: { ...p.company, name: e.target.value } }))}
                className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Logo</label>
              <p className="mt-1 text-xs leading-relaxed text-surface-400 dark:text-surface-500">
                PNG with a transparent background works best. Recommended: square 512 × 512 px
                or wide 1024 × 256 px. Max file size 2 MB. After choosing a file you can crop
                it before uploading.
              </p>
              <div className="mt-2 flex items-center gap-4">
                {settings.company.logo && (
                  <img src={settings.company.logo} alt="Logo" className="h-12 w-12 shrink-0 rounded-lg object-contain border border-surface-200 dark:border-surface-600" />
                )}
                <label className="cursor-pointer rounded-lg border border-surface-300 px-4 py-2 text-sm text-surface-600 hover:bg-surface-50 dark:border-surface-600 dark:text-surface-400 dark:hover:bg-surface-700">
                  <Upload className="inline h-4 w-4 mr-1" />
                  {logoUploading ? "Uploading..." : settings.company.logo ? "Replace Logo" : "Upload Logo"}
                  <input type="file" accept="image/png,image/jpeg" className="hidden" onChange={handleLogoSelect} />
                </label>
              </div>
              {cropSrc && (
                <LogoCropper
                  imageSrc={cropSrc}
                  open={true}
                  onClose={closeCropper}
                  onConfirm={handleCroppedLogo}
                />
              )}
            </div>

            <Button onClick={saveSettings} isLoading={saving}>
              <Save className="h-4 w-4" /> Save Company Settings
            </Button>
          </div>
        </Card>
      )}

      {tab === "smtp" && (
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-surface-900 dark:text-surface-100">SMTP Configuration</h2>
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Host</label>
                <input
                  value={settings.smtp.host}
                  onChange={(e) => setSettings((p) => ({ ...p, smtp: { ...p.smtp, host: e.target.value } }))}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Port</label>
                <input
                  type="number"
                  value={settings.smtp.port}
                  onChange={(e) => setSettings((p) => ({ ...p, smtp: { ...p.smtp, port: parseInt(e.target.value) || 587 } }))}
                  className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Username</label>
              <input
                value={settings.smtp.username}
                onChange={(e) => setSettings((p) => ({ ...p, smtp: { ...p.smtp, username: e.target.value } }))}
                className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Password</label>
              <input
                type="password"
                value={settings.smtp.password}
                onChange={(e) => setSettings((p) => ({ ...p, smtp: { ...p.smtp, password: e.target.value } }))}
                className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">From Email</label>
              <input
                type="email"
                value={settings.smtp.from_email}
                onChange={(e) => setSettings((p) => ({ ...p, smtp: { ...p.smtp, from_email: e.target.value } }))}
                className="mt-1 w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
              />
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={settings.smtp.use_tls}
                onChange={(e) => setSettings((p) => ({ ...p, smtp: { ...p.smtp, use_tls: e.target.checked } }))}
                className="rounded border-surface-300 text-accent-500 focus:ring-accent-500 dark:border-surface-600 dark:bg-surface-800"
              />
              <span className="text-sm text-surface-700 dark:text-surface-300">Use TLS</span>
            </label>
            <div className="flex gap-2">
              <Button onClick={saveSettings} isLoading={saving}>
                <Save className="h-4 w-4" /> Save SMTP Settings
              </Button>
              <Button variant="outline" onClick={sendTestEmail} isLoading={saving} disabled={!settings.smtp.host}>
                <Send className="h-4 w-4" /> Send Test Email
              </Button>
            </div>
          </div>
        </Card>
      )}

      {tab === "password" && (
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-surface-900 dark:text-surface-100">Password Policy</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">Minimum Length</label>
              <input
                type="number"
                min={4}
                max={128}
                value={settings.password_policy.min_length}
                onChange={(e) => setSettings((p) => ({ ...p, password_policy: { ...p.password_policy, min_length: parseInt(e.target.value) || 8 } }))}
                className="mt-1 w-32 rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
              />
            </div>
            <div className="space-y-2">
              {([
                ["require_uppercase", "Require Uppercase (A-Z)"],
                ["require_lowercase", "Require Lowercase (a-z)"],
                ["require_numbers", "Require Numbers (0-9)"],
                ["require_symbols", "Require Symbols (!@#$%...)"],
              ] as const).map(([key, label]) => (
                <label key={key} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={settings.password_policy[key as keyof PasswordPolicy] as boolean}
                    onChange={(e) => setSettings((p) => ({ ...p, password_policy: { ...p.password_policy, [key]: e.target.checked } }))}
                    className="rounded border-surface-300 text-accent-500 focus:ring-accent-500 dark:border-surface-600 dark:bg-surface-800"
                  />
                  <span className="text-sm text-surface-700 dark:text-surface-300">{label}</span>
                </label>
              ))}
            </div>
            <Button onClick={saveSettings} isLoading={saving}>
              <Save className="h-4 w-4" /> Save Password Policy
            </Button>
          </div>
        </Card>
      )}

      {tab === "danger" && (
        <Card>
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-100 text-accent-600 dark:bg-accent-900/30 dark:text-accent-400">
              <Trash2 className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Reset System</h2>
              <p className="mt-1 text-sm text-surface-500">
                Deletes all data and returns the system to a fresh state.
              </p>
              <div className="mt-4">
                {showConfirm ? (
                  <div className="space-y-3 rounded-xl border border-accent-200 bg-accent-50 p-4 dark:border-accent-800 dark:bg-accent-900/20">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-500" />
                      <p className="text-sm font-medium text-accent-700 dark:text-accent-300">
                        This action cannot be undone. Type <strong>reset</strong> to confirm.
                      </p>
                    </div>
                    <input
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value)}
                      placeholder="Type 'reset' to confirm"
                      className="w-full rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                    />
                    <div className="flex gap-2">
                      <Button variant="danger" size="sm" onClick={handleReset} isLoading={loading} disabled={confirmText !== "reset"}>
                        <Trash2 className="h-4 w-4" /> Reset Everything
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => { setShowConfirm(false); setConfirmText(""); }}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => setShowConfirm(true)}>
                    <Trash2 className="h-4 w-4" /> Reset System
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
