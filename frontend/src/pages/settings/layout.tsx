import { NavLink, Outlet } from "react-router-dom"
import {
  Activity, Building2, Coins, Cpu, Database, Key, Layers, Plug, Settings, ShieldCheck, UserCircle, Users,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuthStore } from "@/stores/auth"

const allNavItems = [
  { to: "/settings/models", icon: Cpu, label: "模型供应商", adminOnly: false },
  { to: "/settings/mcp", icon: Plug, label: "MCP 服务器", adminOnly: true },
  { to: "/settings/departments", icon: Building2, label: "部门管理", adminOnly: true },
  { to: "/settings/users", icon: Users, label: "用户管理", adminOnly: true },
  { to: "/settings/sso", icon: ShieldCheck, label: "SSO 认证", adminOnly: true },
  { to: "/settings/observability", icon: Activity, label: "可观测性", adminOnly: true },
  { to: "/settings/costs", icon: Coins, label: "成本", adminOnly: true },
  { to: "/settings/cross-kb", icon: Layers, label: "跨库治理", adminOnly: true },
  { to: "/settings/milvus", icon: Database, label: "Milvus 治理", adminOnly: true },
  { to: "/settings/system", icon: Settings, label: "系统管理", adminOnly: true },
  { to: "/settings/profile", icon: UserCircle, label: "个人设置", adminOnly: false },
  { to: "/settings/api-keys", icon: Key, label: "API 密钥", adminOnly: false },
]

export default function SettingsLayout() {
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.role === "system_admin"
  const navItems = allNavItems.filter((item) => !item.adminOnly || isAdmin)

  return (
    <div className="flex gap-6">
      <aside className="w-48 shrink-0">
        <nav className="flex flex-col gap-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent",
                  isActive && "bg-accent font-medium",
                )
              }
            >
              <Icon className="size-4 shrink-0" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  )
}
