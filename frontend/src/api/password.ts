import { request } from '@/utils/hertz_request'

// 修改密码接口参数
export interface ChangePasswordParams {
  old_password: string
  new_password: string
  confirm_password: string
}

// 重置密码接口参数
export interface ResetPasswordParams {
  email?: string
  username?: string
  email_code: string
  new_password: string
  confirm_password: string
}

// 修改密码
export const changePassword = (params: ChangePasswordParams) => {
  return request.post('/api/auth/password/change/', params)
}

// 重置密码
export const resetPassword = (params: ResetPasswordParams) => {
  return request.post('/api/auth/password/reset/', params)
}

// 查询账号绑定邮箱脱敏值
export const getResetPasswordEmail = (username: string) => {
  return request.post('/api/auth/password/reset/email/', { username })
}

// 发送重置密码邮箱验证码
export const sendResetPasswordCode = (email: string) => {
  // 后端统一走 /api/auth/email/code/，并通过 code_type 区分业务场景
  return request.post('/api/auth/email/code/', { email, code_type: 'reset_password' })
}

// 按账号发送重置密码验证码到绑定邮箱
export const sendResetPasswordCodeByUsername = (username: string) => {
  return request.post('/api/auth/password/reset/code/', { username })
}
