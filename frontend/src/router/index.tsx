import { Suspense, lazy } from "react";
import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "../components/auth/ProtectedRoute";
import { AppShell } from "../components/layout/AppShell";
import { LoginPage } from "../pages/auth/LoginPage";
import { ForgotPasswordPage } from "../pages/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "../pages/auth/ResetPasswordPage";
import { NotFound } from "../pages/NotFound";
import { ProjectList } from "../pages/projects/ProjectList";
import { SetupPage } from "../pages/auth/SetupPage";

// Heavy routes split into separate chunks so first paint stays light.
const ProjectDetail = lazy(() =>
  import("../pages/projects/ProjectDetail").then((m) => ({ default: m.ProjectDetail })),
);
const DocumentDetail = lazy(() =>
  import("../pages/documents/DocumentDetail").then((m) => ({ default: m.DocumentDetail })),
);
const ApiKeys = lazy(() =>
  import("../pages/ApiKeys").then((m) => ({ default: m.ApiKeys })),
);
const SettingsPage = lazy(() =>
  import("../pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const ValidationPatternsPage = lazy(() =>
  import("../pages/ValidationPatternsPage").then((m) => ({ default: m.ValidationPatternsPage })),
);
const UserManagement = lazy(() =>
  import("../pages/UserManagement").then((m) => ({ default: m.UserManagement })),
);

function withSuspense(element: React.ReactNode) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full min-h-[40vh] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-500 border-t-transparent" />
        </div>
      }
    >
      {element}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/setup",
    element: <SetupPage />,
  },
  {
    path: "/forgot-password",
    element: <ForgotPasswordPage />,
  },
  {
    path: "/reset-password",
    element: <ResetPasswordPage />,
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <ProjectList /> },
      { path: "projects/:projectId", element: withSuspense(<ProjectDetail />) },
      { path: "projects/:projectId/documents/:docId", element: withSuspense(<DocumentDetail />) },
      { path: "projects/:projectId/api-keys", element: withSuspense(<ApiKeys />) },
      { path: "users", element: withSuspense(<UserManagement />) },
      { path: "settings", element: withSuspense(<SettingsPage />) },
      { path: "validation-patterns", element: withSuspense(<ValidationPatternsPage />) },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
