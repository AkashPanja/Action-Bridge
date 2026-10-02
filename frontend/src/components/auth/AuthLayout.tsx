import { motion } from "framer-motion";
import { GitCompareArrows } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface AuthStep {
  title: string;
  description?: string;
}

interface AuthLayoutProps {
  badge: string;
  headline: string;
  subtext: string;
  steps: AuthStep[];
  activeStep?: number;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthLayout({
  badge,
  headline,
  subtext,
  steps,
  activeStep = 0,
  title,
  subtitle,
  children,
  footer,
}: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#23262b] p-4 dark:bg-black md:p-8">
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="grid w-full max-w-6xl overflow-hidden rounded-[2rem] bg-white shadow-2xl dark:bg-surface-900 md:grid-cols-2"
      >
        {/* Brand panel */}
        <div className="relative m-3 hidden flex-col overflow-hidden rounded-[1.5rem] bg-gradient-to-br from-[#1b2cc7] via-[#2f7de9] to-[#62cdf7] p-8 md:flex lg:p-10">
          <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-white/20 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-32 -right-16 h-80 w-80 rounded-full bg-[#1b2cc7]/40 blur-3xl" />
          <div className="pointer-events-none absolute left-1/3 top-1/3 h-56 w-56 rounded-full bg-sky-200/40 blur-3xl" />

          <div className="relative flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/20 backdrop-blur">
              <GitCompareArrows className="h-4 w-4 text-white" />
            </div>
            <span className="text-lg font-semibold tracking-tight text-white">Action Bridge</span>
          </div>

          <div className="relative mt-auto pt-16">
            <span className="inline-block rounded-full border border-white/30 bg-white/15 px-4 py-1.5 text-sm font-medium text-white backdrop-blur">
              {badge}
            </span>
            <h1 className="mt-4 text-4xl font-bold leading-[1.1] tracking-tight text-white lg:text-5xl">
              {headline}
            </h1>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-white/80">{subtext}</p>

            <div className="mt-8 grid grid-cols-3 gap-3">
              {steps.map((s, i) => {
                const isActive = i === activeStep;
                return (
                  <div
                    key={s.title}
                    className={cn(
                      "flex min-h-[132px] flex-col rounded-2xl p-4",
                      isActive
                        ? "bg-white shadow-lg"
                        : "border border-white/20 bg-white/15 backdrop-blur",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
                        isActive
                          ? "bg-[#2440f5] text-white"
                          : "border border-white/50 text-white",
                      )}
                    >
                      {i + 1}
                    </span>
                    <p
                      className={cn(
                        "mt-auto text-[13px] font-semibold leading-snug",
                        isActive ? "text-surface-900" : "text-white",
                      )}
                    >
                      {s.title}
                    </p>
                    {s.description && !isActive ? (
                      <p className="mt-0.5 text-[11px] leading-snug text-white/70">{s.description}</p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Form panel */}
        <div className="flex items-center justify-center p-8 sm:p-10 lg:p-12">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.1, ease: "easeOut" }}
            className="w-full max-w-sm"
          >
            <h2 className="text-center text-[26px] font-bold tracking-tight text-surface-900 dark:text-surface-100">
              {title}
            </h2>
            {subtitle ? (
              <p className="mt-2 text-center text-sm text-surface-500 dark:text-surface-400">
                {subtitle}
              </p>
            ) : null}

            <div className="mt-7">{children}</div>

            {footer ? <div className="mt-5">{footer}</div> : null}
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}
