import { createBrowserRouter, Navigate } from "react-router-dom"
import { ProtectedRoute } from "@/components/auth/protected-route"
import { AppLayout } from "@/components/layout/app-layout"
import LoginPage from "@/pages/login"
import NotFoundPage from "@/pages/not-found"
import InitWizard from "@/pages/init"
import KnowledgePage from "@/pages/knowledge"
import KBDetailPage from "@/pages/knowledge/detail"
import AgentsPage from "@/pages/agents"
import AgentDetailPage from "@/pages/agents/detail"
import SettingsLayout from "@/pages/settings/layout"
import ModelsPage from "@/pages/settings/models"
import DepartmentsPage from "@/pages/settings/departments"
import UsersPage from "@/pages/settings/users"
import SystemPage from "@/pages/settings/system"
import ProfilePage from "@/pages/settings/profile"
import ApiKeysPage from "@/pages/settings/api-keys"

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
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
          {
            path: "settings",
            element: <SettingsLayout />,
            children: [
              { index: true, element: <Navigate to="/settings/models" replace /> },
              { path: "models", element: <ModelsPage /> },
              { path: "departments", element: <DepartmentsPage /> },
              { path: "users", element: <UsersPage /> },
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
