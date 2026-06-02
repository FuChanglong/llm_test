import { describe, expect, it } from 'vitest'

import { getPasswordScore, validateAuthForm } from './authValidation'

describe('validateAuthForm', () => {
  it('rejects mismatched confirmation passwords during register', () => {
    expect(validateAuthForm('register', 'alice', 'password123', 'a@example.com', 'Alice', 'password456')).toEqual({
      canSubmit: false,
      error: '两次输入的密码不一致。',
    })
  })

  it('accepts login with username and password', () => {
    expect(validateAuthForm('login', 'alice', 'password123', '', '', '')).toEqual({
      canSubmit: true,
      error: null,
    })
  })
})

describe('getPasswordScore', () => {
  it('returns strong score for mixed passwords', () => {
    expect(getPasswordScore('Abc123!!').percent).toBe(100)
  })
})
