import { useState } from "react"
import { cn } from "@/lib/utils"
import { StepAdmin } from "./step-admin"
import { StepProvider } from "./step-provider"
import { StepKnowledge } from "./step-knowledge"
import { StepTest } from "./step-test"

const steps = [
  { label: "创建管理员", component: StepAdmin },
  { label: "AI 提供商", component: StepProvider },
  { label: "知识库", component: StepKnowledge },
  { label: "完成", component: StepTest },
]

export default function InitWizard() {
  const [current, setCurrent] = useState(0)
  const StepComponent = steps[current].component

  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg">
        <h1 className="mb-8 text-center text-2xl font-semibold">系统初始化</h1>

        {/* Progress bar */}
        <div className="mb-8 flex items-center gap-2">
          {steps.map((step, i) => (
            <div key={step.label} className="flex flex-1 flex-col items-center gap-1">
              <div
                className={cn(
                  "h-2 w-full rounded-full transition-colors",
                  i <= current ? "bg-primary" : "bg-muted",
                )}
              />
              <span className={cn("text-xs", i <= current ? "text-foreground" : "text-muted-foreground")}>
                {step.label}
              </span>
            </div>
          ))}
        </div>

        <StepComponent
          onNext={() => setCurrent((c) => Math.min(c + 1, steps.length - 1))}
          onBack={current > 0 ? () => setCurrent((c) => c - 1) : undefined}
        />
      </div>
    </div>
  )
}
