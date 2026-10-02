import { motion } from "framer-motion";
import { ArrowLeft, CircleCheck, GitCompareArrows } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../contexts/AuthContext";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const { user, isLoading, setupRequired, confirmPasswordReset } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-500 border-t-transparent" />
      </div>
    );
  }

  if (setupRequired) return <Navigate to="/setup" replace />;
  if (user) return <Navigate to="/" replace />;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[rgb(var(--color-bg))] p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="rounded-2xl border border-surface-200/60 bg-white p-8 shadow-xl dark:border-surface-700/50 dark:bg-surface-800">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-500">
              {done ? <CircleCheck className="h-6 w-6 text-white" /> : <GitCompareArrows className="h-6 w-6 text-white" />}
            </div>
            <h1 className="text-xl font-bold text-surface-900 dark:text-surface-100">
              {done ? "Password reset" : "Set a new password"}
            </h1>
            <p className="mt-1 text-sm text-surface-500 dark:text-surface-400">
              {done ? "Your password has been updated. Sign in with your new password." : "Choose a strong new password"}
            </p>
          </div>

          {!token ? (
            <motion.p
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400"
            >
              This reset link is invalid or missing its token. Request a new one below.
            </motion.p>
          ) : !done ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="New password"
                type="password"
                placeholder="At least 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                id="new-password"
              />
              <Input
                label="Confirm password"
                type="password"
                placeholder="Repeat your new password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                id="confirm-password"
              />

              {error ? (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400"
                >
                  {error}
                </motion.p>
              ) : null}

              <Button type="submit" isLoading={loading} className="w-full">
                Reset password
              </Button>
            </form>
          ) : (
            <Link to="/login">
              <Button className="w-full">Sign in</Button>
            </Link>
          )}

          <p className="mt-4 text-center text-sm text-surface-500">
            <Link to="/forgot-password" className="flex items-center justify-center gap-1 text-accent-500 hover:text-accent-600">
              <ArrowLeft className="h-3.5 w-3.5" />
              Request a new link
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
