import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

interface StepProps {
  onNext: () => void
  onBack?: () => void
}

export function StepKnowledge({ onNext, onBack }: StepProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>创建知识库</CardTitle>
        <CardDescription>可稍后在主界面创建</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">此步骤可跳过，后续可在知识库页面创建。</p>
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
