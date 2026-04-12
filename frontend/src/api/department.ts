import { api } from "./client"

export interface Department {
  id: string
  name: string
  parent_id: string | null
  children?: Department[]
  member_count: number
  created_at: string
}

export interface Member {
  id: string
  user_id: string
  username: string
  email: string
  role: string
  joined_at: string
}

interface CreateDepartmentPayload {
  name: string
  parent_id?: string
}

interface AddMemberPayload {
  user_id: string
  role?: string
}

export const departmentApi = {
  list() {
    return api.get<Department[]>("/departments")
  },

  create(data: CreateDepartmentPayload) {
    return api.post<Department>("/departments", data)
  },

  delete(id: string) {
    return api.delete<void>(`/departments/${id}`)
  },

  listMembers(deptId: string) {
    return api.get<Member[]>(`/departments/${deptId}/members`)
  },

  addMember(deptId: string, data: AddMemberPayload) {
    return api.post<Member>(`/departments/${deptId}/members`, data)
  },

  removeMember(deptId: string, memberId: string) {
    return api.delete<void>(`/departments/${deptId}/members/${memberId}`)
  },
}
