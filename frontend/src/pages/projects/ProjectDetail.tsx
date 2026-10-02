import { AnimatePresence, motion } from "framer-motion";
import { FileType, Inbox, Key, LayoutDashboard, ScanSearch, Users, Workflow } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { AnimatedPage } from "../../components/shared/AnimatedPage";
import { PageHeader } from "../../components/shared/PageHeader";
import { useAuth } from "../../contexts/AuthContext";
import { useProject } from "../../hooks/useProjects";
import { can } from "../../lib/rbac";
import { ApiKeys } from "../ApiKeys";
import { DocumentInbox } from "../documents/DocumentInbox";
import { DocumentTypeList } from "../document-types/DocumentTypeList";
import { MembersPage } from "../MembersPage";
import { ProjectDashboard } from "../ProjectDashboard";
import { JobsPage } from "../extraction/JobsPage";
import { ProfilesPage } from "../extraction/ProfilesPage";

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams] = useSearchParams();
  const { data: project } = useProject(projectId!);
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState(searchParams.get("tab") || "dashboard");

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "documents", label: "Documents", icon: Inbox },
    { id: "document-types", label: "Document Types", icon: FileType },
    { id: "members", label: "Members", icon: Users },
    { id: "jobs", label: "Jobs", icon: Workflow },
    ...(user && (user.role === "admin" || user.role === "editor")
      ? [{ id: "profiles", label: "Extraction", icon: ScanSearch }]
      : []),
    ...(user && can(user.role, "api_keys:manage")
      ? [{ id: "api-keys", label: "API Keys", icon: Key }]
      : []),
  ];

  return (
    <AnimatedPage>
      <PageHeader
        title={project?.name ?? "Project"}
        description={project?.description ?? ""}
      />

      <div className="mb-6 flex gap-1 overflow-x-auto rounded-xl bg-surface-100 p-1 dark:bg-surface-800">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex shrink-0 items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 ${
                activeTab === tab.id
                  ? "bg-white text-surface-900 shadow-sm dark:bg-surface-700 dark:text-surface-100"
                  : "text-surface-500 hover:text-surface-700 dark:text-surface-400 dark:hover:text-surface-200"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
        >
          {activeTab === "dashboard" ? (
            <ProjectDashboard projectId={projectId!} />
          ) : activeTab === "documents" ? (
            <DocumentInbox projectId={projectId!} />
          ) : activeTab === "document-types" ? (
            <DocumentTypeList projectId={projectId} />
          ) : activeTab === "members" ? (
            <MembersPage projectId={projectId!} />
          ) : activeTab === "jobs" ? (
            <JobsPage projectId={projectId!} />
          ) : activeTab === "profiles" ? (
            <ProfilesPage projectId={projectId!} />
          ) : (
            <ApiKeys />
          )}
        </motion.div>
      </AnimatePresence>
    </AnimatedPage>
  );
}
