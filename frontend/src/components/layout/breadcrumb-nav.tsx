import { Link, useLocation } from "react-router-dom"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Fragment } from "react"

const labelMap: Record<string, string> = {
  knowledge: "知识库",
  agents: "智能体",
  settings: "设置",
}

export function BreadcrumbNav() {
  const { pathname } = useLocation()
  const segments = pathname.split("/").filter(Boolean)

  if (segments.length === 0) return null

  return (
    <Breadcrumb className="mb-4">
      <BreadcrumbList>
        {segments.map((seg, i) => {
          const path = "/" + segments.slice(0, i + 1).join("/")
          const label = labelMap[seg] ?? seg
          const isLast = i === segments.length - 1

          return (
            <Fragment key={path}>
              {i > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link to={path}>{label}</Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
