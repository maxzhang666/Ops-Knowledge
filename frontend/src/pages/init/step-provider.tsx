import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

interface StepProps {
  onNext: () => void
  onBack?: () => void
}

export function StepProvider({ onNext, onBack }: StepProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI 提供商配置</CardTitle>
        <CardDescription>可稍后在设置中配置</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">此步骤可跳过，后续可在系统设置中添加 AI 提供商。</p>
        <div className="flex gap-2">
          {onBack && (
            <Button variant="outline" onClick={onBack}>
              上一步
            </Button>
          )}
          <Button onClick={onNext} className="flex-1">
            跳过
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
