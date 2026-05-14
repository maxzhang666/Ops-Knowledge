import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Bot, LogOut, MessageSquare, Monitor, Moon, Sun, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTheme } from "@/hooks/use-theme"
import { useAuthStore } from "@/stores/auth"
import { agentApi, type Agent } from "@/api/agent"
import { NotificationDropdown } from "@/components/layout/notification-dropdown"
import { ReviewBadge } from "@/components/layout/review-badge"
import { TaskFailureBadge } from "@/components/layout/task-failure-badge"
import { GlobalSearch } from "@/components/layout/global-search"

const themeIcon = { light: Sun, dark: Moon, system: Monitor } as const

export function Header() {
  const navigate = useNavigate()
  const { theme, cycleTheme } = useTheme()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const ThemeIcon = themeIcon[theme]
  const [agents, setAgents] = useState<Agent[]>([])

  // 收拢自 Header 的 QuickChatDropdown：用户菜单展开时拉前 5 个 agent，
  // 提供「快速对话」入口。完整列表仍在 /agents 主页。
  useEffect(() => {
    let cancelled = false
    agentApi.list({ page_size: "5" })
      .then((r) => { if (!cancelled) setAgents(r.items) })
      .catch(() => { /* silent */ })
    return () => { cancelled = true }
  }, [])

  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-2 border-b bg-background px-4">
      <GlobalSearch />
      <ReviewBadge />
      <TaskFailureBadge />
      <NotificationDropdown />
      <Button variant="ghost" size="icon" onClick={cycleTheme} title={`主题: ${theme}`}>
        <ThemeIcon className="h-4 w-4" />
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant="ghost" size="icon" className="rounded-full" />}
        >
          <Avatar className="h-7 w-7">
            <AvatarFallback className="text-xs">
              {user?.username?.charAt(0).toUpperCase() ?? "U"}
            </AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuItem disabled>
            <User className="mr-2 h-4 w-4" />
            {user?.username ?? "用户"}
          </DropdownMenuItem>

          <DropdownMenuSeparator />
          <DropdownMenuLabel className="flex items-center gap-1.5">
            <MessageSquare className="size-3" />快速对话
          </DropdownMenuLabel>
          {agents.length === 0 ? (
            <DropdownMenuItem
              className="text-xs text-muted-foreground"
              onClick={() => navigate("/agents")}
            >
              暂无智能体 · 去创建 →
            </DropdownMenuItem>
          ) : (
            <>
              {agents.map((a) => (
                <DropdownMenuItem
                  key={a.id}
                  onClick={() => navigate(`/agents/${a.id}`)}
                >
                  <Bot className="mr-2 h-4 w-4" />
                  <span className="truncate">{a.name}</span>
                </DropdownMenuItem>
              ))}
              <DropdownMenuItem
                className="justify-center text-xs text-muted-foreground"
                onClick={() => navigate("/agents")}
              >
                查看全部智能体 →
              </DropdownMenuItem>
            </>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={logout}>
            <LogOut className="mr-2 h-4 w-4" />
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
