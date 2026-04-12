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
import SettingsPage from "@/pages/settings"

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
          { path: "settings/*", element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
])
