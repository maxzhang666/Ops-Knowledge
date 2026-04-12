import { Link } from "react-router-dom"
import { buttonVariants } from "@/components/ui/button"

export default function NotFoundPage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-background">
      <h1 className="text-6xl font-bold text-muted-foreground">404</h1>
      <p className="text-muted-foreground">页面不存在</p>
      <Link to="/" className={buttonVariants()}>
        返回首页
      </Link>
    </div>
  )
}
