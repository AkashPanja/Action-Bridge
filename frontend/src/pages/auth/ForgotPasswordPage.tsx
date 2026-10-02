import { motion } from "framer-motion";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../contexts/AuthContext";

const steps = [
  { title: "Request a link", description: "Enter your account email" },
  { title: "Check your inbox", description: "Link expires in 1 hour" },
  { title: "Set new password", description: "Back to work in minutes" },
];

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const { user, isLoading, setupRequired, requestPasswordReset } = useAuth();

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
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      badge="Account recovery"
      headline="Locked out? No stress."
      subtext="Follow these simple steps to get back into your workspace."
      steps={steps}
      activeStep={sent ? 1 : 0}
      title={sent ? "Check your email" : "Forgot password"}
      subtitle={
        sent
          ? `If an account exists for ${email}, a reset link has been sent. It expires in 1 hour.`
          : "Enter your email and we'll send you a reset link"
      }
      footer={
        <p className="text-center text-sm text-surface-500">
          <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
            Back to sign in
          </Link>
        </p>
      }
    >
      {!sent ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Email"
            type="email"
            placeholder="admin@actioncenter.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            id="forgot-email"
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
            Send reset link
          </Button>
        </form>
      ) : (
        <Link to="/login">
          <Button size="lg" className="w-full">Back to sign in</Button>
        </Link>
      )}
    </AuthLayout>
  );
}
