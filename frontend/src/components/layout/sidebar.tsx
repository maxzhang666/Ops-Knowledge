import { NavLink } from "react-router-dom"
import { BookOpen, Bot, Settings, ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useUiStore } from "@/stores/ui"

// Spec 12 §Phase 1b: "No separate Workflow navigation — accessed through Agent".
// Workflow Agents create + edit their workflow entirely inside the Agent
// Workbench, so the top-level nav stays knowledge / agents / settings.
const navItems = [
  { to: "/knowledge", icon: BookOpen, label: "知识库" },
  { to: "/agents", icon: Bot, label: "智能体" },
  { to: "/settings", icon: Settings, label: "设置" },
]

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed)
  const toggle = useUiStore((s) => s.toggleSidebar)

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200",
        collapsed ? "w-[60px]" : "w-[220px]",
      )}
    >
      <div className="flex h-14 items-center justify-center border-b px-3">
        {!collapsed && <span className="text-sm font-semibold tracking-tight">Ops Knowledge</span>}
      </div>

      <nav className="flex flex-1 flex-col gap-1 p-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent",
                isActive && "bg-sidebar-accent text-sidebar-accent-foreground font-medium",
                collapsed && "justify-center px-0",
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="border-t p-2">
        <Button variant="ghost" size="icon" className="w-full" onClick={toggle}>
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
    </aside>
  )
}
