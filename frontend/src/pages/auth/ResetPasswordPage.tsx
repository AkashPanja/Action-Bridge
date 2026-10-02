import { motion } from "framer-motion";
import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../contexts/AuthContext";

const steps = [
  { title: "Open your email", description: "Click the reset link" },
  { title: "Choose a password", description: "Make it strong" },
  { title: "Sign in again", description: "Back to your queue" },
];

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
      <div className="flex h-screen items-center justify-center bg-[#23262b]">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/30 border-t-white" />
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
    <AuthLayout
      badge="Almost there"
      headline="Choose a new password."
      subtext="Pick something strong — at least 8 characters with a mix of letters and numbers."
      steps={steps}
      activeStep={done ? 2 : 1}
      title={done ? "Password reset" : "Set a new password"}
      subtitle={
        done
          ? "Your password has been updated. Sign in with your new password."
          : "Choose a strong new password"
      }
      footer={
        <p className="text-center text-sm text-surface-500">
          <Link to="/forgot-password" className="font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
            Request a new link
          </Link>
        </p>
      }
    >
      {!token ? (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl bg-accent-50 px-4 py-2.5 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400"
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
              className="rounded-xl bg-accent-50 px-4 py-2.5 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400"
            >
              {error}
            </motion.p>
          ) : null}

          <Button type="submit" size="lg" isLoading={loading} className="w-full">
            Reset password
          </Button>
        </form>
      ) : (
        <Link to="/login">
          <Button size="lg" className="w-full">Sign in</Button>
        </Link>
      )}
    </AuthLayout>
  );
}
