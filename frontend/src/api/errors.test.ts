import { describe, expect, it } from 'vitest'
import { AxiosError } from 'axios'

import { getErrorMessage } from './errors'

describe('getErrorMessage', () => {
  it('reads fastapi detail text from axios errors', () => {
    const error = new AxiosError('Request failed', '400', undefined, undefined, {
      data: { detail: '邀请码无效' },
      status: 400,
      statusText: 'Bad Request',
      headers: {},
      config: {} as never,
    })

    expect(getErrorMessage(error)).toBe('邀请码无效')
  })

  it('falls back to generic error message', () => {
    expect(getErrorMessage(new Error('network down'))).toBe('network down')
  })
})
