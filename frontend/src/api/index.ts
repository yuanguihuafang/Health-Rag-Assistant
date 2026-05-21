// API 统一出口文件（显式导出，避免 export * 的同名冲突）

// captcha
export { generateCaptcha, refreshCaptcha } from "./captcha";
export type { CaptchaResponse, CaptchaRefreshResponse } from "./captcha";

// auth
export { registerUser, loginUser, sendEmailCode, logoutUser } from "./auth";
export type { RegisterData, SendEmailCodeData, LoginData } from "./auth";

// user
export { userApi } from "./user";
export type {
  Role,
  User,
  UserListData,
  UserListResponse,
  UserListParams,
  AssignRolesParams,
} from "./user";

// department
export { departmentApi } from "./department";
export type {
  Department,
  DepartmentListData,
  DepartmentListResponse,
  DepartmentListParams,
  CreateDepartmentParams,
  UpdateDepartmentParams,
} from "./department";

// menu
export { menuApi } from "./menu";
export type {
  RawMenu,
  Menu,
  MenuListData,
  MenuListResponse,
  MenuListParams,
  CreateMenuParams,
  UpdateMenuParams,
  MenuTreeResponse,
} from "./menu";

// role
export { roleApi } from "./role";
export type {
  Permission,
  Role as SystemRole,
  RoleListData,
  RoleListResponse,
  RoleListParams,
  CreateRoleParams,
  UpdateRoleParams,
  AssignRolePermissionsParams,
  PermissionListResponse,
} from "./role";

// password
export {
  changePassword,
  resetPassword,
  sendResetPasswordCode,
} from "./password";
export type { ChangePasswordParams, ResetPasswordParams } from "./password";

// dashboard
export { dashboardApi } from "./dashboard";
export type {
  DashboardStats,
  RecentActivity,
  SystemStatus,
  VisitTrend,
  DashboardData,
} from "./dashboard";

// log
export { logApi } from "./log";
export type {
  LogListParams,
  OperationLogItem,
  LogListData,
  LogListResponse,
  OperationLogDetail,
  LogDetailResponse,
} from "./log";

// health rag（暂时停用）
// export { healthRagApi } from "./health_rag";
// export type {
//   HealthSourceRef,
//   HealthKnowledgeDocument,
//   HealthSessionItem,
//   HealthHistoryItem,
//   HealthTopicFocus,
//   HealthRecommendationItem,
// } from "./health_rag";
