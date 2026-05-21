<template>
  <div class="login-container">
    <div class="bg-layer" aria-hidden="true">
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
      <span class="orb orb-c"></span>
    </div>

    <div class="left-section">
      <div class="welcome-content">
        <div class="brand-badge">PYTHON STUDIO</div>
        <h1 class="welcome-title">欢迎使用</h1>
        <h2 class="system-name">基于RAG的身体健康智慧问答助手的设计与实现</h2>
        <p class="welcome-description">
          为健康问答、知识库管理与健康知识推荐提供统一入口
        </p>
        <div class="feature-list">
          <div class="feature-item">RAG 健康问答</div>
          <div class="feature-item">知识库管理</div>
          <div class="feature-item">问答历史与推荐</div>
        </div>
      </div>
    </div>

    <div class="right-section">
      <div class="login-card">
        <div class="card-top-line"></div>
        <div class="login-header">
          <h1 class="login-title">{{ $t('login.title') }}</h1>
          <p class="login-subtitle">请输入账号信息并完成验证码校验</p>
        </div>

        <a-form
          :model="form"
          :rules="rules"
          @finish="handleLogin"
          layout="vertical"
          class="login-form"
        >
          <a-form-item
            :label="$t('login.username')"
            name="username"
          >
            <a-input
              v-model:value="form.username"
              :placeholder="$t('login.username')"
              size="large"
            >
              <template #prefix>
                <UserOutlined />
              </template>
            </a-input>
          </a-form-item>

          <a-form-item
            :label="$t('login.password')"
            name="password"
          >
            <a-input-password
              v-model:value="form.password"
              :placeholder="$t('login.password')"
              size="large"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item
            label="验证码"
            name="captcha"
          >
            <a-row :gutter="8">
              <a-col :span="16">
                <a-input
                  v-model:value="form.captcha"
                  placeholder="请输入验证码"
                  size="large"
                >
                  <template #prefix>
                    <SafetyOutlined />
                  </template>
                </a-input>
              </a-col>
              <a-col :span="8">
                <div class="captcha-container">
                  <img
                    v-if="captchaData?.image_data"
                    :src="captchaData.image_data"
                    alt="验证码"
                    class="captcha-image"
                    @click="handleRefreshCaptcha"
                  />
                  <a-button
                    v-else
                    size="large"
                    :loading="captchaLoading"
                    @click="handleRefreshCaptcha"
                    block
                  >
                    获取验证码
                  </a-button>
                </div>
              </a-col>
            </a-row>
          </a-form-item>

          <a-form-item>
            <div class="login-options">
              <a-checkbox v-model:checked="form.remember">
                {{ $t('login.rememberMe') }}
              </a-checkbox>
              <a href="#" class="forgot-password" @click.prevent="openResetPasswordModal">
                {{ $t('login.forgotPassword') }}
              </a>
            </div>
          </a-form-item>

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              :loading="loading"
              block
              class="login-button"
            >
              {{ $t('login.login') }}
            </a-button>
          </a-form-item>

          <div class="register-link">
            还没有账户？
            <a @click="goToRegister">立即注册</a>
          </div>
        </a-form>
      </div>
    </div>

    <a-modal
      v-model:visible="resetPasswordVisible"
      title="重置密码"
      :confirm-loading="resetSubmitting"
      ok-text="确认重置"
      cancel-text="取消"
      @ok="handleResetPassword"
      @cancel="closeResetPasswordModal"
    >
      <a-form layout="vertical" class="reset-form">
        <a-form-item label="登录账号" required>
          <a-input v-model:value="resetForm.username" disabled />
        </a-form-item>
        <a-form-item label="绑定邮箱" required>
          <div class="masked-email-box">
            <span>{{ resetForm.email_masked || "正在读取绑定邮箱..." }}</span>
          </div>
          <div class="reset-hint">验证码将发送到该账号绑定邮箱，邮箱地址已脱敏保护。</div>
        </a-form-item>
        <a-form-item label="邮箱验证码" required>
          <a-input
            v-model:value="resetForm.email_code"
            placeholder="请输入验证码"
          >
            <template #addonAfter>
              <a-button
                type="link"
                size="small"
                :loading="resetCodeSending"
                :disabled="resetCountdown > 0"
                @click="sendResetCode"
              >
                {{ resetCountdown > 0 ? `${resetCountdown}s` : "获取验证码" }}
              </a-button>
            </template>
          </a-input>
        </a-form-item>
        <a-form-item label="新密码" required>
          <a-input-password
            v-model:value="resetForm.new_password"
            placeholder="请输入新密码，至少6位"
          />
        </a-form-item>
        <a-form-item label="确认新密码" required>
          <a-input-password
            v-model:value="resetForm.confirm_password"
            placeholder="请再次输入新密码"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/hertz_user'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import {
  UserOutlined,
  LockOutlined,
  SafetyOutlined
} from '@ant-design/icons-vue'
import { useCaptcha } from '@/utils/hertz_captcha'
import { loginUser } from '@/api'
import {
  getResetPasswordEmail,
  resetPassword,
  sendResetPasswordCodeByUsername,
} from '@/api/password'
import { errorHandler, handleSuccess } from '@/utils/hertz_error_handler'

const router = useRouter()
const userStore = useUserStore()
const { t } = useI18n()

// 初始化错误处理器的i18n实例
errorHandler.setI18n({ t })

const loading = ref(false)
const resetPasswordVisible = ref(false)
const resetSubmitting = ref(false)
const resetCodeSending = ref(false)
const resetCountdown = ref(0)
let resetTimer: number | undefined

// 验证码相关
const { captchaData, captchaLoading, generateCaptcha, refreshCaptcha } = useCaptcha()

const form = reactive({
  username: '',
  password: '',
  captcha: '',
  remember: false,
})

const resetForm = reactive({
  username: '',
  email_masked: '',
  email_code: '',
  new_password: '',
  confirm_password: '',
})

const rules = {
  username: [
    { required: true, message: t('error.usernameRequired'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('error.passwordRequired'), trigger: 'blur' },
  ],
  captcha: [
    { required: true, message: t('error.captchaRequired'), trigger: 'blur' },
  ],
}

const handleLogin = async () => {
  if (loading.value) return

  // 验证表单
  if (!form.username || !form.password || !form.captcha) {
    message.error(t('error.requiredFieldMissing'))
    return
  }

  // 检查验证码数据是否存在
  if (!captchaData.value?.captcha_id) {
    message.error(t('error.captchaExpired'))
    await handleRefreshCaptcha()
    return
  }

  loading.value = true

  try {
    // 构建登录数据 - 严格按照API接口定义
    const loginData = {
      username: form.username,
      password: form.password,
      captcha_code: form.captcha.trim(),
      captcha_key: captchaData.value.captcha_id
    }

    const response = await loginUser(loginData)

    // 设置用户状态到store
    if (response.data) {
      // 设置token - 使用后端返回的access_token
      if (response.data.access_token) {
        userStore.token = response.data.access_token
        localStorage.setItem('token', response.data.access_token)
      }

      // 设置用户信息
      if (response.data.user_info) {
        userStore.userInfo = response.data.user_info
        userStore.isLoggedIn = true
        localStorage.setItem('userInfo', JSON.stringify(response.data.user_info))
      }
    }

    handleSuccess('login')

    // 根据用户角色跳转到对应首页
    const userRole = response.data?.user_info?.roles?.[0]?.role_code

    // 仅管理员角色进入管理端，其余（含未定义）进入用户端
    const adminRoles = ['admin', 'system_admin', 'super_admin']
    const isAdmin = adminRoles.includes(userRole as any)
    if (isAdmin) {
      router.push('/admin')
    } else {
      router.push('/dashboard')
    }

  } catch (error: any) {
    console.error('登录失败:', error)

    // 清除敏感字段
    form.password = ''
    form.captcha = ''

    // 刷新验证码
    await handleRefreshCaptcha()
  } finally {
    loading.value = false
  }
}

const handleRefreshCaptcha = async () => {
  try {
    await refreshCaptcha()
    // 清空验证码输入
    form.captcha = ''
  } catch (error) {
    message.error('刷新验证码失败')
  }
}

const goToRegister = () => {
  router.push('/register')
}

const openResetPasswordModal = async () => {
  const username = form.username.trim()
  if (!username) {
    message.warning('请先输入登录账号，再重置密码')
    return
  }

  resetForm.username = username
  resetForm.email_masked = ''
  resetPasswordVisible.value = true

  try {
    const response: any = await getResetPasswordEmail(username)
    if (response?.success === false) {
      message.error(response.message || '绑定邮箱读取失败')
      closeResetPasswordModal()
      return
    }
    resetForm.email_masked = response?.data?.email_masked || ''
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || '绑定邮箱读取失败')
    closeResetPasswordModal()
  }
}

const closeResetPasswordModal = () => {
  resetPasswordVisible.value = false
  resetForm.username = ''
  resetForm.email_masked = ''
  resetForm.email_code = ''
  resetForm.new_password = ''
  resetForm.confirm_password = ''
  resetCountdown.value = 0
  if (resetTimer) {
    window.clearInterval(resetTimer)
    resetTimer = undefined
  }
}

const startResetCountdown = () => {
  resetCountdown.value = 60
  if (resetTimer) {
    window.clearInterval(resetTimer)
  }
  resetTimer = window.setInterval(() => {
    resetCountdown.value -= 1
    if (resetCountdown.value <= 0 && resetTimer) {
      window.clearInterval(resetTimer)
      resetTimer = undefined
    }
  }, 1000)
}

const sendResetCode = async () => {
  const username = resetForm.username.trim()
  if (!username) {
    message.warning('请先输入登录账号')
    return
  }
  resetCodeSending.value = true
  try {
    const response: any = await sendResetPasswordCodeByUsername(username)
    if (response?.success === false) {
      message.error(response.message || '验证码发送失败')
      return
    }
    resetForm.email_masked = response?.data?.email_masked || resetForm.email_masked
    message.success(response?.message || '验证码已发送，请查收邮箱')
    startResetCountdown()
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || '验证码发送失败')
  } finally {
    resetCodeSending.value = false
  }
}

const handleResetPassword = async () => {
  if (!resetForm.username.trim() || !resetForm.email_code.trim()) {
    message.warning('请填写账号和验证码')
    return
  }
  if (!resetForm.new_password || resetForm.new_password.length < 6) {
    message.warning('新密码至少6位')
    return
  }
  if (resetForm.new_password !== resetForm.confirm_password) {
    message.warning('两次输入的新密码不一致')
    return
  }
  resetSubmitting.value = true
  try {
    const response: any = await resetPassword({
      username: resetForm.username.trim(),
      email_code: resetForm.email_code.trim(),
      new_password: resetForm.new_password,
      confirm_password: resetForm.confirm_password,
    })
    if (response?.success === false) {
      message.error(response.message || '密码重置失败')
      return
    }
    message.success(response?.message || '密码重置成功，请重新登录')
    closeResetPasswordModal()
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || '密码重置失败')
  } finally {
    resetSubmitting.value = false
  }
}

// 页面加载时生成验证码
onMounted(() => {
  generateCaptcha()
})

onUnmounted(() => {
  if (resetTimer) {
    window.clearInterval(resetTimer)
  }
})
</script>

<style scoped lang="scss">
.login-container {
  --ink-strong: #0f2b46;
  --ink-soft: #4f6f92;
  --panel-bg: rgba(255, 255, 255, 0.82);
  --panel-border: rgba(121, 165, 214, 0.52);
  --field-bg: rgba(255, 255, 255, 0.92);
  --field-border: #b8d3ee;
  --accent: #2b8cff;
  --accent-strong: #1f6fff;
  --page-a: #f3f9ff;
  --page-b: #e4f0ff;
  --page-c: #cfe6ff;

  position: relative;
  overflow: hidden;
  display: flex;
  min-height: 100vh;
  background: linear-gradient(125deg, var(--page-a) 0%, var(--page-b) 46%, var(--page-c) 100%);
}

.bg-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;

  .orb {
    position: absolute;
    border-radius: 999px;
    filter: blur(6px);
    opacity: 0.45;
    animation: float 11s ease-in-out infinite;
  }

  .orb-a {
    width: 440px;
    height: 440px;
    left: -120px;
    top: -120px;
    background: radial-gradient(circle at 35% 35%, rgba(64, 154, 255, 0.48), rgba(64, 154, 255, 0.06) 70%);
  }

  .orb-b {
    width: 520px;
    height: 520px;
    right: -150px;
    top: 14%;
    background: radial-gradient(circle at 50% 50%, rgba(43, 140, 255, 0.42), rgba(43, 140, 255, 0.05) 72%);
    animation-delay: -3s;
  }

  .orb-c {
    width: 360px;
    height: 360px;
    left: 38%;
    bottom: -140px;
    background: radial-gradient(circle at 50% 50%, rgba(125, 211, 252, 0.4), rgba(125, 211, 252, 0.05) 70%);
    animation-delay: -6s;
  }
}

.left-section {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 72px 64px;
}

.welcome-content {
  max-width: 560px;
}

.brand-badge {
  display: inline-block;
  margin-bottom: 22px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid rgba(43, 140, 255, 0.34);
  background: rgba(255, 255, 255, 0.68);
  color: #2f628f;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.welcome-title {
  font-size: 28px;
  font-weight: 500;
  color: #4f6f92;
  margin-bottom: 10px;
}

.system-name {
  margin: 0 0 20px;
  font-size: 34px;
  font-weight: 700;
  line-height: 1.35;
  color: #0e406f;
  letter-spacing: -0.02em;
  white-space: normal;
  word-break: break-word;
}

.welcome-description {
  margin: 0;
  max-width: 440px;
  font-size: 17px;
  color: var(--ink-soft);
  line-height: 1.8;
}

.feature-list {
  margin-top: 32px;
  display: flex;
  flex-direction: column;
  gap: 10px;

  .feature-item {
    position: relative;
    padding-left: 18px;
    color: #335982;
    font-size: 14px;
    letter-spacing: 0.01em;

    &::before {
      content: "";
      position: absolute;
      left: 0;
      top: 50%;
      width: 8px;
      height: 8px;
      border-radius: 999px;
      transform: translateY(-50%);
      background: linear-gradient(135deg, #7dd3fc, #38bdf8);
      box-shadow: 0 0 8px rgba(43, 140, 255, 0.45);
    }
  }
}

.right-section {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 56px;
}

.login-card {
  position: relative;
  background: var(--panel-bg);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  padding: 42px 38px 34px;
  border-radius: 22px;
  width: 100%;
  max-width: 460px;
  border: 1px solid var(--panel-border);
  box-shadow: 0 24px 64px rgba(31, 102, 181, 0.22);
}

.card-top-line {
  position: absolute;
  left: 26px;
  right: 26px;
  top: 0;
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(147, 197, 253, 0.95), rgba(43, 140, 255, 0.82), rgba(96, 165, 250, 0.82));
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-title {
  font-size: 30px;
  font-weight: 700;
  color: var(--ink-strong);
  margin: 0 0 8px;
  letter-spacing: 0.01em;
}

.login-subtitle {
  color: #5b7da1;
  font-size: 14px;
  margin: 0;
}

.login-form {
  width: 100%;
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.forgot-password {
  color: #2f79d0;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;
}

.forgot-password:hover {
  color: #1f5fa8;
}

.masked-email-box {
  min-height: 42px;
  display: flex;
  align-items: center;
  padding: 0 14px;
  border: 1px solid #b8d3ee;
  border-radius: 12px;
  background: #f4f8ff;
  color: #1f4368;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.reset-hint {
  margin-top: 8px;
  color: #6c86a5;
  font-size: 12px;
  line-height: 1.6;
}

.register-link {
  text-align: center;
  margin-top: 24px;
  color: #5f7fa2;
  font-size: 14px;
}

.register-link a {
  color: #2f79d0;
  text-decoration: none;
  margin-left: 4px;
  cursor: pointer;
  transition: color 0.2s;
}

.register-link a:hover {
  color: #1f5fa8;
}

:deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: #2b4f76;
  font-size: 14px;
}

:deep(.ant-input-affix-wrapper),
:deep(.ant-input-password),
:deep(.ant-input) {
  border-radius: 12px;
  border: 1px solid var(--field-border);
  background: var(--field-bg);
  color: #1f4368;
  transition: all 0.2s;
}

:deep(.ant-input-affix-wrapper:focus),
:deep(.ant-input-affix-wrapper-focused) {
  border-color: #67b1ff;
  box-shadow: 0 0 0 3px rgba(52, 144, 255, 0.18);
}

:deep(.ant-input) {
  border: none !important;
  font-size: 14px;
  background: transparent !important;
  color: #1f4368;
}

:deep(.ant-input::placeholder),
:deep(.ant-input-password input::placeholder) {
  color: #83a0bf;
}

:deep(.ant-input-prefix) {
  color: #7295bc;
  margin-right: 8px;
}

:deep(.ant-btn-primary) {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
  border-color: transparent;
  border-radius: 12px;
  height: 46px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
  transition: all 0.25s ease;
  box-shadow: 0 10px 24px rgba(22, 119, 255, 0.35);
}

:deep(.ant-btn-primary:hover) {
  transform: translateY(-1px);
  box-shadow: 0 14px 30px rgba(22, 119, 255, 0.45);
}

:deep(.ant-checkbox-wrapper) {
  font-size: 14px;
  color: #5f7fa2;
}

:deep(.ant-checkbox-checked .ant-checkbox-inner) {
  background-color: #2b8cff;
  border-color: #2b8cff;
}

:deep(.ant-checkbox-inner) {
  background: #ffffff;
  border-color: #8eb3d8;
}

:deep(.ant-form-item) {
  margin-bottom: 20px;
}

.captcha-container {
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.captcha-image {
  width: 172px;
  max-width: 100%;
  height: 46px;
  border-radius: 10px;
  border: 1px solid var(--field-border);
  cursor: pointer;
  transition: border-color 0.2s;
  object-fit: contain;
  background: #ffffff;
  image-rendering: auto;
}

.captcha-image:hover {
  border-color: #67b1ff;
}

.captcha-container :deep(.ant-btn) {
  width: 172px;
  max-width: 100%;
  height: 46px;
  border-radius: 12px;
  border-color: var(--field-border);
  background: var(--field-bg);
  color: #37618b;
}

.captcha-container :deep(.ant-btn:hover) {
  border-color: #67b1ff;
  color: #1f4f7b;
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0px);
  }
  50% {
    transform: translateY(14px);
  }
}

@media (max-width: 1080px) {
  .left-section {
    display: none;
  }

  .right-section {
    flex: 1 1 100%;
    padding: 28px;
  }

  .login-card {
    max-width: 520px;
  }
}

@media (max-width: 640px) {
  .right-section {
    padding: 18px;
  }

  .login-card {
    padding: 30px 20px 24px;
    border-radius: 16px;
  }

  .login-title {
    font-size: 26px;
  }
}
</style>
