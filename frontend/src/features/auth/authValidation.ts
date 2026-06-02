export interface AuthValidationState {
  canSubmit: boolean
  error: string | null
}

export function validateAuthForm(
  mode: 'login' | 'register',
  username: string,
  password: string,
  email: string,
  displayName: string,
  confirmPassword: string,
): AuthValidationState {
  const cleanUsername = username.trim()
  const cleanEmail = email.trim()
  const cleanDisplayName = displayName.trim()

  if (cleanUsername.length < 3) {
    return { canSubmit: false, error: '用户名至少需要 3 个字符。' }
  }
  if (password.length < 6) {
    return { canSubmit: false, error: '密码至少需要 6 个字符。' }
  }
  if (mode === 'login') {
    return { canSubmit: true, error: null }
  }
  if (!cleanDisplayName) {
    return { canSubmit: false, error: '注册时请填写显示名称。' }
  }
  if (cleanEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
    return { canSubmit: false, error: '邮箱格式看起来不正确。' }
  }
  if (password !== confirmPassword) {
    return { canSubmit: false, error: '两次输入的密码不一致。' }
  }
  return { canSubmit: true, error: null }
}

export function getPasswordScore(password: string) {
  const score = [
    password.length >= 8,
    /[A-Z]/.test(password),
    /[0-9]/.test(password),
    /[^A-Za-z0-9]/.test(password),
  ].filter(Boolean).length
  if (score <= 1) return { percent: 34, label: '密码强度偏弱', color: '#d92d20' }
  if (score === 2) return { percent: 66, label: '密码强度中等', color: '#d89614' }
  return { percent: 100, label: '密码强度良好', color: '#12805c' }
}
