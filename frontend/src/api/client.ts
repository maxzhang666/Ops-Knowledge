const BASE_URL = "/api/v1"

class HttpError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = "HttpError"
    this.status = status
  }
}

class ApiClient {
  private refreshPromise: Promise<boolean> | null = null

  private getToken(): string | null {
    return localStorage.getItem("access_token")
  }

  private getRefreshToken(): string | null {
    return localStorage.getItem("refresh_token")
  }

  private setTokens(access: string, refresh: string) {
    localStorage.setItem("access_token", access)
    localStorage.setItem("refresh_token", refresh)
  }

  private clearTokens() {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
  }

  private async refreshAccessToken(): Promise<boolean> {
    const refreshToken = this.getRefreshToken()
    if (!refreshToken) return false

    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!res.ok) return false

      const data = await res.json()
      this.setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    }
  }

  private async request<T>(
    method: string,
    path: string,
    options: { body?: unknown; params?: Record<string, string>; isFormData?: boolean } = {},
  ): Promise<T> {
    const url = new URL(`${BASE_URL}${path}`, window.location.origin)
    if (options.params) {
      for (const [k, v] of Object.entries(options.params)) {
        url.searchParams.set(k, v)
      }
    }

    const headers: Record<string, string> = {}
    const token = this.getToken()
    if (token) headers["Authorization"] = `Bearer ${token}`

    let body: BodyInit | undefined
    if (options.isFormData) {
      body = options.body as FormData
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json"
      body = JSON.stringify(options.body)
    }

    let res = await fetch(url.toString(), { method, headers, body })

    if (res.status === 401 && token) {
      if (!this.refreshPromise) {
        this.refreshPromise = this.refreshAccessToken().finally(() => {
          this.refreshPromise = null
        })
      }
      const refreshed = await this.refreshPromise
      if (refreshed) {
        headers["Authorization"] = `Bearer ${this.getToken()}`
        res = await fetch(url.toString(), { method, headers, body })
      } else {
        this.clearTokens()
        window.location.href = "/login"
        throw new HttpError(401, "Session expired")
      }
    }

    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new HttpError(res.status, text)
    }

    if (res.status === 204) return undefined as T
    return res.json()
  }

  get<T>(path: string, params?: Record<string, string>) {
    return this.request<T>("GET", path, { params })
  }

  post<T>(path: string, body?: unknown) {
    return this.request<T>("POST", path, { body })
  }

  put<T>(path: string, body?: unknown) {
    return this.request<T>("PUT", path, { body })
  }

  patch<T>(path: string, body?: unknown) {
    return this.request<T>("PATCH", path, { body })
  }

  delete<T>(path: string) {
    return this.request<T>("DELETE", path)
  }

  upload<T>(path: string, formData: FormData) {
    return this.request<T>("POST", path, { body: formData, isFormData: true })
  }
}

export const api = new ApiClient()
export { HttpError }
