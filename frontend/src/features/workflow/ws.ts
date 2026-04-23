/**
 * Execution event WebSocket client.
 *
 * JWT is passed via `?token=` query param because browsers can't attach
 * Authorization headers to WS handshakes. Backend (plan 15 + 20) authenticates
 * BEFORE accept() and closes with 4401 on invalid token.
 *
 * Auto-reconnect with exponential backoff up to 5 attempts, then gives up
 * silently (the workflow likely finished and bus is gone).
 */

export interface WsEvent {
  type:
    | "workflow_start"
    | "workflow_end"
    | "node_start"
    | "node_output"
    | "node_error"
    | "node_end"
    | "stream_chunk"
    | "waiting_input"
    | "error"
  node_id: string | null
  data: Record<string, unknown>
  ts: string
}

export function connectExecutionEvents(
  wfId: string,
  execId: string,
  onEvent: (ev: WsEvent) => void,
): () => void {
  const token = localStorage.getItem("access_token") ?? ""
  const proto = window.location.protocol === "https:" ? "wss" : "ws"
  const url = `${proto}://${window.location.host}/api/v1/workflow/${wfId}/executions/${execId}/events?token=${encodeURIComponent(token)}`

  let ws: WebSocket | null = null
  let attempts = 0
  let closed = false
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function open() {
    ws = new WebSocket(url)

    ws.addEventListener("open", () => {
      attempts = 0
    })

    ws.addEventListener("message", (m) => {
      try {
        onEvent(JSON.parse(m.data))
      } catch {
        // Drop malformed frames silently.
      }
    })

    ws.addEventListener("close", () => {
      if (closed || attempts >= 5) return
      attempts += 1
      const delay = Math.min(1000 * 2 ** attempts, 10000)
      retryTimer = setTimeout(open, delay)
    })
  }

  open()

  return () => {
    closed = true
    if (retryTimer) clearTimeout(retryTimer)
    try {
      ws?.close()
    } catch {
      // ignore — socket may already be closed
    }
  }
}
