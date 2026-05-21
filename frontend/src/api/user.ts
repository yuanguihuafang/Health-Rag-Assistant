import { request } from "@/utils/hertz_request";

// 角色接口类型定义
export interface Role {
  role_id: number;
  role_name: string;
  role_code: string;
  role_ids?: string;
}

// 用户接口类型定义（匹配后端实际数据结构）
export interface User {
  user_id: number;
  username: string;
  email: string;
  phone?: string;
  real_name?: string;
  avatar?: string;
  gender: number;
  birthday?: string;
  department_id?: number;
  status: number;
  last_login_time?: string;
  last_login_ip?: string;
  created_at: string;
  updated_at: string;
  roles: Role[];
}

// API响应基础结构
export interface ApiResponse<T> {
  success: boolean;
  code: number;
  message: string;
  data: T;
}

// 用户列表数据结构
export interface UserListData {
  list: User[];
  total: number;
  page: number;
  page_size: number;
}

// 用户列表响应类型
export type UserListResponse = ApiResponse<UserListData>;

// 用户列表查询参数
export interface UserListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: number;
  role_ids?: string;
}

// 分配角色参数
export interface AssignRolesParams {
  user_id: number;
  role_ids: number[]; // 角色ID数组
}

// 用户API
export const userApi = {
  // 获取用户列表
  getUserList: (params?: UserListParams): Promise<UserListResponse> => {
    return request.get("/api/users/", { params });
  },

  // 获取单个用户
  getUser: (id: number): Promise<ApiResponse<User>> => {
    return request.get(`/api/users/${id}/`);
  },

  // 创建用户
  createUser: (data: Partial<User>): Promise<ApiResponse<User>> => {
    return request.post("/api/users/create/", data);
  },

  // 更新用户
  updateUser: (id: number, data: Partial<User>): Promise<ApiResponse<User>> => {
    return request.put(`/api/users/${id}/update/`, data);
  },

  // 删除用户
  deleteUser: (id: number): Promise<ApiResponse<any>> => {
    return request.delete(`/api/users/${id}/delete/`);
  },

  // 批量删除用户
  batchDeleteUsers: (ids: number[]): Promise<ApiResponse<any>> => {
    if (!ids.length) {
      return Promise.resolve({
        success: true,
        code: 200,
        message: "无需删除",
        data: { success_ids: [], failed_ids: [] },
      });
    }

    // 后端当前仅提供单删接口，这里做前端兼容批量删除
    return Promise.allSettled(
      ids.map((id) => request.delete(`/api/users/${id}/delete/`)),
    ).then((results) => {
      const success_ids: number[] = [];
      const failed_ids: number[] = [];
      const errors: Array<{ id: number; reason: unknown }> = [];

      results.forEach((result, index) => {
        const id = ids[index];
        if (result.status === "fulfilled") {
          success_ids.push(id);
        } else {
          failed_ids.push(id);
          errors.push({ id, reason: result.reason });
        }
      });

      return {
        success: failed_ids.length === 0,
        code: failed_ids.length === 0 ? 200 : 207,
        message: failed_ids.length === 0 ? "批量删除成功" : "部分删除失败",
        data: { success_ids, failed_ids, errors },
      };
    });
  },

  // 获取当前用户信息
  getUserInfo: (): Promise<ApiResponse<User>> => {
    return request.get("/api/auth/user/info/");
  },

  // 更新当前用户信息
  updateUserInfo: (data: Partial<User>): Promise<ApiResponse<User>> => {
    return request.put("/api/auth/user/info/update/", data);
  },

  uploadAvatar: (file: File): Promise<ApiResponse<User>> => {
    const formData = new FormData();
    formData.append("avatar", file);
    return request.upload("/api/auth/user/avatar/upload/", formData);
  },

  // 分配用户角色
  assignRoles: (data: AssignRolesParams): Promise<ApiResponse<any>> => {
    return request.post("/api/users/assign-roles/", data);
  },

  // 获取所有角色列表
  getRoleList: (): Promise<ApiResponse<Role[]>> => {
    return request.get("/api/roles/");
  },
};
