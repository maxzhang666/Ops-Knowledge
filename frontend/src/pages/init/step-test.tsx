import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

interface StepProps {
  onNext: () => void
  onBack?: () => void
}

export function StepTest({ onBack }: StepProps) {
  const navigate = useNavigate()

  return (
    <Card>
      <CardHeader>
        <CardTitle>初始化完成</CardTitle>
        <CardDescription>系统已准备就绪</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">您可以开始使用系统了。点击下方按钮前往登录。</p>
        <div className="flex gap-2">
          {onBack && (
            <Button variant="outline" onClick={onBack}>
              上一步
            </Button>
          )}
          <Button onClick={() => navigate("/login", { replace: true })} className="flex-1">
            前往登录
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
