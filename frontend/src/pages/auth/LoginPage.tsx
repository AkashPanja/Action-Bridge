import { motion } from "framer-motion";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../contexts/AuthContext";

const steps = [
  { title: "Sign in securely", description: "Your workspace is protected" },
  { title: "Pick a project", description: "Jump back where you left off" },
  { title: "Review documents", description: "Approve with confidence" },
];

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { user, isLoading, setupRequired, login } = useAuth();
  const navigate = useNavigate();

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
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      badge="Welcome back"
      headline="Review with confidence."
      subtext="Sign in to pick up your review queue, inspect bot submissions, and keep documents moving."
      steps={steps}
      activeStep={0}
      title="Sign in"
      subtitle="Access your Action Bridge workspace"
      footer={
        <p className="text-center text-xs leading-relaxed text-surface-400 dark:text-surface-500">
          Protected by role-based access. Contact your administrator if you
          cannot access your account.
        </p>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          placeholder="admin@actioncenter.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          id="email"
        />
        <div>
          <Input
            label="Password"
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            id="password"
          />
          <div className="mt-2 text-right">
            <Link to="/forgot-password" className="text-[13px] font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
              Forgot password?
            </Link>
          </div>
        </div>

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
          Sign In
        </Button>
      </form>
    </AuthLayout>
  );
}
