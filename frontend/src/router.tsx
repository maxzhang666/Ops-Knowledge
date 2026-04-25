import { createBrowserRouter, Navigate } from "react-router-dom"
import { ProtectedRoute } from "@/components/auth/protected-route"
import { AppLayout } from "@/components/layout/app-layout"
import LoginPage from "@/pages/login"
import LoginCallbackPage from "@/pages/login-callback"
import NotFoundPage from "@/pages/not-found"
import InitWizard from "@/pages/init"
import KnowledgePage from "@/pages/knowledge"
import KBDetailPage from "@/pages/knowledge/detail"
import AgentsPage from "@/pages/agents"
import AgentDetailPage from "@/pages/agents/detail"
import WorkflowEditorPage from "@/pages/workflow/editor"
import SettingsLayout from "@/pages/settings/layout"
import ModelsPage from "@/pages/settings/models"
import McpServersPage from "@/pages/settings/mcp-servers"
import DepartmentsPage from "@/pages/settings/departments"
import UsersPage from "@/pages/settings/users"
import SystemPage from "@/pages/settings/system"
import ProfilePage from "@/pages/settings/profile"
import ApiKeysPage from "@/pages/settings/api-keys"
import SsoSettingsPage from "@/pages/settings/sso"
import ObservabilityPage from "@/pages/settings/observability"
import CostsPage from "@/pages/settings/costs"
import CrossKBPage from "@/pages/settings/cross-kb"

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/login/callback", element: <LoginCallbackPage /> },
  { path: "/init", element: <InitWizard /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="/knowledge" replace /> },
          { path: "knowledge", element: <KnowledgePage /> },
          { path: "knowledge/:id", element: <KBDetailPage /> },
          { path: "agents", element: <AgentsPage /> },
          { path: "agents/:id", element: <AgentDetailPage /> },
          // /workflow/:id stays as a directly-navigable editor URL (useful for
          // deep-links and admin debugging), but there's no /workflow index —
          // per spec 12, workflows aren't first-class navigation items.
          { path: "workflow/:id", element: <WorkflowEditorPage /> },
          {
            path: "settings",
            element: <SettingsLayout />,
            children: [
              { index: true, element: <Navigate to="/settings/models" replace /> },
              { path: "models", element: <ModelsPage /> },
              { path: "mcp", element: <McpServersPage /> },
              { path: "departments", element: <DepartmentsPage /> },
              { path: "users", element: <UsersPage /> },
              { path: "sso", element: <SsoSettingsPage /> },
              { path: "observability", element: <ObservabilityPage /> },
              { path: "costs", element: <CostsPage /> },
              { path: "cross-kb", element: <CrossKBPage /> },
              { path: "system", element: <SystemPage /> },
              { path: "profile", element: <ProfilePage /> },
              { path: "api-keys", element: <ApiKeysPage /> },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
])
