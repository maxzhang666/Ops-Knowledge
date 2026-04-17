import { Component, type ReactNode } from "react"
import { AlertCircle, RefreshCcw } from "lucide-react"

import { Button } from "@/components/ui/button"

interface Props {
  children: ReactNode
  fallback?: (error: Error, reset: () => void) => ReactNode
}

interface State {
  error: Error | null
}

/**
 * Catches render-time errors in descendant components. Without this an
 * uncaught exception unmounts the whole React tree and the user sees a
 * blank page. With this, errors are contained and the user can retry.
 *
 * Intentionally a class component — Error Boundaries have no Hook API.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    // Surface to console for dev debugging; production should pipe to a
    // telemetry sink (Sentry, etc.) here.
    console.error("[ErrorBoundary] caught", error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (error) {
      if (this.props.fallback) return this.props.fallback(error, this.reset)
      return <DefaultFallback error={error} onRetry={this.reset} />
    }
    return this.props.children
  }
}

function DefaultFallback({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center gap-3 p-8 text-center">
      <AlertCircle className="size-10 text-destructive" />
      <h2 className="text-lg font-semibold">页面出错了</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        {error.message || "发生未预期的错误。刷新页面通常可以恢复。"}
      </p>
      <div className="mt-2 flex gap-2">
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCcw className="mr-1.5 size-3.5" /> 重试
        </Button>
        <Button size="sm" onClick={() => window.location.reload()}>
          刷新页面
        </Button>
      </div>
    </div>
  )
}
