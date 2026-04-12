import { Bell, Sun, Moon, Monitor, LogOut, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTheme } from "@/hooks/use-theme"
import { useAuthStore } from "@/stores/auth"
import { QuickChatDropdown } from "@/features/chat/components/quick-chat-dropdown"

const themeIcon = { light: Sun, dark: Moon, system: Monitor } as const

export function Header() {
  const { theme, cycleTheme } = useTheme()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const ThemeIcon = themeIcon[theme]

  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-2 border-b bg-background px-4">
      <QuickChatDropdown />
      <Button variant="ghost" size="icon" title="通知">
        <Bell className="h-4 w-4" />
      </Button>
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
        <DropdownMenuContent align="end">
          <DropdownMenuItem disabled>
            <User className="mr-2 h-4 w-4" />
            {user?.username ?? "用户"}
          </DropdownMenuItem>
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
