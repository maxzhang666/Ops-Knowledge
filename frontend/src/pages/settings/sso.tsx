import { SsoConfigCard } from "@/components/settings/sso-config-card"


/**
 * Dedicated SSO settings page. Previously this card lived at the bottom of
 * /settings/system — too deep to discover. Promoted to a top-level nav item
 * (admin-only) so operators can find it in two clicks.
 */
export default function SsoSettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">SSO 认证</h1>
        <p className="text-sm text-muted-foreground">
          配置 OIDC 单点登录（Keycloak / Azure AD / Okta / 任意 OIDC 兼容 IdP）。
          保存后登录页会自动出现"使用 SSO 登录"按钮。
        </p>
      </div>
      <SsoConfigCard />
    </div>
  )
}
