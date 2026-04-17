import { api } from "./client"

export interface Department {
  id: string
  name: string
  description: string | null
  parent_department_id: string | null
  member_count?: number  // optional — backend may or may not populate
  created_at: string
}

export interface DepartmentTree extends Department {
  children: DepartmentTree[]
}

export interface Member {
  id: string
  user_id: string
  username: string
  email: string
  role: "dept_admin" | "editor" | "viewer"
  is_primary: boolean
}

export interface ResourceShareRecord {
  id: string
  department_id: string
  resource_type: string
  resource_id: string
  access_level: "view" | "edit" | "use" | "full"
  shared_by: string | null
}

interface CreateDepartmentPayload {
  name: string
  description?: string
  parent_department_id?: string
}

interface UpdateDepartmentPayload {
  name?: string
  description?: string
}

interface AddMemberPayload {
  user_id: string
  role?: "dept_admin" | "editor" | "viewer"
  is_primary?: boolean
}

interface UpdateMemberPayload {
  role: "dept_admin" | "editor" | "viewer"
}

interface ShareResourcePayload {
  resource_type: string
  resource_id: string
  access_level: "view" | "edit" | "use" | "full"
}

export const departmentApi = {
  list() {
    return api.get<DepartmentTree[]>("/departments")
  },

  get(id: string) {
    return api.get<Department>(`/departments/${id}`)
  },

  create(data: CreateDepartmentPayload) {
    return api.post<Department>("/departments", data)
  },

  update(id: string, data: UpdateDepartmentPayload) {
    return api.post<Department>(`/departments/${id}/update`, data)
  },

  delete(id: string) {
    return api.post<void>(`/departments/${id}/delete`)
  },

  // Members
  listMembers(deptId: string) {
    return api.get<Member[]>(`/departments/${deptId}/members`)
  },

  addMember(deptId: string, data: AddMemberPayload) {
    return api.post<Member>(`/departments/${deptId}/members`, data)
  },

  updateMemberRole(deptId: string, userId: string, data: UpdateMemberPayload) {
    return api.post<Member>(`/departments/${deptId}/members/${userId}/update`, data)
  },

  removeMember(deptId: string, userId: string) {
    return api.post<void>(`/departments/${deptId}/members/${userId}/delete`)
  },

  // Resource Sharing
  shareResource(deptId: string, data: ShareResourcePayload) {
    return api.post<ResourceShareRecord>(`/departments/${deptId}/resources`, data)
  },

  unshareResource(deptId: string, resourceType: string, resourceId: string) {
    return api.post<void>(`/departments/${deptId}/resources/${resourceType}/${resourceId}/unshare`)
  },
}
