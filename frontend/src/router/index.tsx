import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "../components/auth/ProtectedRoute";
import { AppShell } from "../components/layout/AppShell";
import { ApiKeys } from "../pages/ApiKeys";
import { DocumentDetail } from "../pages/documents/DocumentDetail";
import { LoginPage } from "../pages/auth/LoginPage";
import { ForgotPasswordPage } from "../pages/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "../pages/auth/ResetPasswordPage";
import { NotFound } from "../pages/NotFound";
import { ProjectDetail } from "../pages/projects/ProjectDetail";
import { ProjectList } from "../pages/projects/ProjectList";
import { SettingsPage } from "../pages/SettingsPage";
import { ValidationPatternsPage } from "../pages/ValidationPatternsPage";
import { SetupPage } from "../pages/auth/SetupPage";
import { UserManagement } from "../pages/UserManagement";

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
      { path: "projects/:projectId", element: <ProjectDetail /> },
      { path: "projects/:projectId/documents/:docId", element: <DocumentDetail /> },
      { path: "projects/:projectId/api-keys", element: <ApiKeys /> },
      { path: "users", element: <UserManagement /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "validation-patterns", element: <ValidationPatternsPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
