import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../contexts/AuthContext";

const steps = [
  { title: "Create your admin account", description: "You manage everything" },
  { title: "Name your workspace", description: "Company branding" },
  { title: "Connect email", description: "Optional notifications" },
  { title: "Review and finish", description: "Confirm and launch" },
];

export function SetupPage() {
  const { user, isLoading, setupRequired, completeSetup } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [companyName, setCompanyName] = useState("Action Bridge");
  const [smtpEnabled, setSmtpEnabled] = useState(false);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpFromEmail, setSmtpFromEmail] = useState("");
  const [smtpUseTls, setSmtpUseTls] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleFinish() {
    setError("");
    setLoading(true);
    try {
      const smtp = smtpEnabled
        ? {
            smtp_host: smtpHost,
            smtp_port: parseInt(smtpPort) || 587,
            smtp_username: smtpUsername || undefined,
            smtp_password: smtpPassword || undefined,
            smtp_from_email: smtpFromEmail || undefined,
            smtp_use_tls: smtpUseTls,
          }
        : undefined;
      await completeSetup(name, email, password, smtp, companyName);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  function nextStep() {
    setError("");
    if (step === 0) {
      if (!name.trim()) { setError("Name is required"); return; }
      if (!email.trim()) { setError("Email is required"); return; }
      if (password.length < 4) { setError("Password must be at least 4 characters"); return; }
      if (password !== confirmPassword) { setError("Passwords do not match"); return; }
    }
    if (step === 2 && smtpEnabled) {
      if (!smtpHost.trim()) { setError("SMTP host is required"); return; }
    }
    setStep((s) => Math.min(s + 1, steps.length - 1));
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#23262b]">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/30 border-t-white" />
      </div>
    );
  }

  if (!setupRequired) {
    return <Navigate to={user ? "/" : "/login"} replace />;
  }

  return (
    <AuthLayout
      badge="First-time setup"
      headline="Start your journey."
      subtext="Follow these simple steps to set up your workspace."
      steps={steps}
      activeStep={step}
      title="Welcome to Action Bridge"
      subtitle={`Step ${step + 1} of ${steps.length} — ${steps[step].title}`}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.2 }}
        >
          {step === 0 ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Input label="Your Name" placeholder="Jane Doe" value={name} onChange={(e) => setName(e.target.value)} required id="name" />
                <Input label="Email Address" type="email" placeholder="admin@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required id="email" />
              </div>
              <Input label="Password" type="password" placeholder="At least 4 characters" value={password} onChange={(e) => setPassword(e.target.value)} required id="password" />
              <p className="-mt-2 text-xs text-surface-400 dark:text-surface-500">
                At least 4 characters. You can enforce a stronger policy later in Settings.
              </p>
              <Input label="Confirm Password" type="password" placeholder="Repeat password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required id="confirm-password" />
            </div>
          ) : step === 1 ? (
            <div className="space-y-4">
              <Input label="Company Name" placeholder="Action Bridge" value={companyName} onChange={(e) => setCompanyName(e.target.value)} id="company-name" />
            </div>
          ) : step === 2 ? (
            <div className="space-y-4">
              <label className="flex items-center gap-2 text-sm font-medium text-surface-700 dark:text-surface-300">
                <input
                  type="checkbox"
                  checked={smtpEnabled}
                  onChange={(e) => setSmtpEnabled(e.target.checked)}
                  className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
                />
                Configure email notifications (optional)
              </label>
              {smtpEnabled ? (
                <div className="space-y-4">
                  <Input label="SMTP Host" placeholder="smtp.gmail.com" value={smtpHost} onChange={(e) => setSmtpHost(e.target.value)} id="smtp-host" />
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Input label="Port" type="number" placeholder="587" value={smtpPort} onChange={(e) => setSmtpPort(e.target.value)} id="smtp-port" />
                    <div className="flex items-end pb-2">
                      <label className="flex items-center gap-2 text-sm font-medium text-surface-700 dark:text-surface-300">
                        <input
                          type="checkbox"
                          checked={smtpUseTls}
                          onChange={(e) => setSmtpUseTls(e.target.checked)}
                          className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
                        />
                        Use TLS
                      </label>
                    </div>
                  </div>
                  <Input label="SMTP Username" placeholder="admin@example.com" value={smtpUsername} onChange={(e) => setSmtpUsername(e.target.value)} id="smtp-username" />
                  <Input label="SMTP Password" type="password" placeholder="App password" value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} id="smtp-password" />
                  <Input label="From Email" type="email" placeholder="noreply@example.com" value={smtpFromEmail} onChange={(e) => setSmtpFromEmail(e.target.value)} id="smtp-from" />
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="divide-y divide-surface-100 rounded-xl bg-surface-100/70 dark:divide-surface-700 dark:bg-surface-800">
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-surface-500">Name</span>
                  <span className="text-sm font-medium text-surface-900 dark:text-surface-100">{name}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-surface-500">Email</span>
                  <span className="text-sm font-medium text-surface-900 dark:text-surface-100">{email}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-surface-500">Company</span>
                  <span className="text-sm font-medium text-surface-900 dark:text-surface-100">{companyName}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-surface-500">Email notifications</span>
                  <span className="text-sm font-medium text-surface-900 dark:text-surface-100">
                    {smtpEnabled ? `Enabled (${smtpHost})` : "Disabled"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {error ? (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 rounded-xl bg-accent-50 px-4 py-2.5 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400"
        >
          {error}
        </motion.p>
      ) : null}

      <div className="mt-6 flex justify-between">
        {step > 0 ? (
          <Button type="button" variant="ghost" onClick={() => setStep((s) => s - 1)}>
            Back
          </Button>
        ) : (
          <div />
        )}
        {step < steps.length - 1 ? (
          <Button size="lg" onClick={nextStep}>
            Continue <ChevronRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button size="lg" onClick={handleFinish} isLoading={loading}>
            Finish Setup
          </Button>
        )}
      </div>
    </AuthLayout>
  );
}
