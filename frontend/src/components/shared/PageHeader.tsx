import { motion } from "framer-motion";
import { cn } from "../../lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, action, className }: PageHeaderProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn("mb-8 flex flex-wrap items-start justify-between gap-4", className)}
    >
      <div className="min-w-0">
        <h1 className="break-words text-2xl font-bold text-surface-900 dark:text-surface-100">{title}</h1>
        {description ? (
          <p className="mt-1 text-sm text-surface-500 dark:text-surface-400">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </motion.div>
  );
}
