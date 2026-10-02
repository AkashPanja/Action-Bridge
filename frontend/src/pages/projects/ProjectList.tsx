import { motion } from "framer-motion";
import { FolderKanban, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { can } from "../../lib/rbac";
import { Card } from "../../components/ui/Card";
import { CardSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { Input } from "../../components/ui/Input";
import { PageHeader } from "../../components/shared/PageHeader";
import { AnimatedPage } from "../../components/shared/AnimatedPage";
import { useBulkDeleteProjects, useDeleteProject, useProjects } from "../../hooks/useProjects";
import { formatDate } from "../../lib/utils";
import { Badge } from "../../components/ui/Badge";
import { ProjectCreateDialog } from "./ProjectCreate";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" } },
};

export function ProjectList() {
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { data: projects, isLoading } = useProjects(search);
  const { user } = useAuth();
  const navigate = useNavigate();
  const deleteProject = useDeleteProject();
  const bulkDelete = useBulkDeleteProjects();

  const canWrite = user && can(user.role, "projects:write");

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (!projects) return;
    if (selected.size === projects.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(projects.map((p) => p.id)));
    }
  }

  function handleBulkDelete() {
    if (selected.size === 0) return;
    if (confirm(`Delete ${selected.size} project${selected.size > 1 ? "s" : ""}? This will remove all associated data.`)) {
      bulkDelete.mutate(Array.from(selected), {
        onSuccess: () => setSelected(new Set()),
      });
    }
  }

  return (
    <AnimatedPage>
      <PageHeader
        title="Projects"
        description="Manage your document processing projects"
        action={canWrite ? (
          <button
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-brand-500/25 transition-all hover:bg-brand-600 hover:shadow-brand-500/40 active:scale-[0.98]"
          >
            <Plus className="h-4 w-4" />
            New Project
          </button>
        ) : undefined}
      />

      <div className="relative mb-6 max-w-sm">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" />
        <Input
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <>
          <motion.div
            variants={container}
            initial="hidden"
            animate="show"
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          >
            {projects.map((project) => (
              <motion.div key={project.id} variants={item}>
                <Card
                  hover
                  onClick={() => navigate(`/projects/${project.id}`)}
                  className="group relative overflow-hidden"
                >
                  <div className="mb-3 flex items-center gap-3">
                    {canWrite ? (
                      <input
                        type="checkbox"
                        checked={selected.has(project.id)}
                        onChange={() => toggle(project.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-4 w-4 shrink-0 rounded border-surface-300 text-brand-500 focus:ring-brand-500 dark:border-surface-600"
                      />
                    ) : null}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
                      <FolderKanban className="h-5 w-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="truncate text-sm font-semibold text-surface-900 dark:text-surface-100">
                        {project.name}
                      </h3>
                      <p className="text-xs text-surface-400">
                        {formatDate(project.created_at)}
                      </p>
                    </div>
                    <Badge variant="primary" className="shrink-0">
                      Active
                    </Badge>
                    {canWrite ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm("Delete this project? This will remove all associated data.")) {
                            deleteProject.mutate(project.id);
                          }
                        }}
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-surface-400 transition-all hover:bg-accent-50 hover:text-accent-500 dark:hover:bg-accent-900/20"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </div>
                  {project.description ? (
                    <p className="line-clamp-2 text-sm text-surface-500 dark:text-surface-400">
                      {project.description}
                    </p>
                  ) : (
                    <p className="text-sm italic text-surface-400 dark:text-surface-500">
                      No description
                    </p>
                  )}
                  <div className="absolute inset-x-0 bottom-0 h-1 translate-y-full bg-gradient-to-r from-brand-500 to-brand-400 transition-transform group-hover:translate-y-0" />
                </Card>
              </motion.div>
            ))}
          </motion.div>

          {canWrite && selected.size > 0 ? (
            <div className="fixed bottom-8 left-1/2 z-50 max-w-[calc(100vw-2rem)] -translate-x-1/2">
              <div className="flex items-center gap-3 rounded-2xl border border-surface-300 bg-white px-5 py-3 shadow-xl dark:border-surface-600 dark:bg-surface-800">
                <span className="text-sm font-medium text-surface-700 dark:text-surface-200">
                  {selected.size} selected
                </span>
                <div className="h-5 w-px bg-surface-300 dark:bg-surface-600" />
                <button
                  onClick={handleBulkDelete}
                  disabled={bulkDelete.isPending}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-accent-500 px-3.5 py-1.5 text-sm font-medium text-white transition-all hover:bg-accent-600 active:scale-[0.97] disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {bulkDelete.isPending ? "Deleting..." : "Delete Selected"}
                </button>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <EmptyState
          icon={<FolderKanban className="h-8 w-8" />}
          title="No projects yet"
          description="Create your first project to start managing document types and processing documents."
          action={{ label: "Create Project", onClick: () => setCreateOpen(true) }}
        />
      )}

      <ProjectCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </AnimatedPage>
  );
}
