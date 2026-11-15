import axios from 'axios'
import type { ErrorResponse } from './types'

/** Normalized error shape every API call rejects with, so UI code never has
 * to branch on axios internals vs. the backend's `{error:{code,message}}` body. */
export class ApiError extends Error {
  code: string
  details: Record<string, unknown>
  status?: number

  constructor(code: string, message: string, details: Record<string, unknown> = {}, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.details = details
    this.status = status
  }
}

export const apiClient = axios.create({ baseURL: '/api' })

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const data = error.response?.data as ErrorResponse | undefined
      if (data?.error) {
        return Promise.reject(new ApiError(data.error.code, data.error.message, data.error.details ?? {}, error.response?.status))
      }
      if (!error.response) {
        return Promise.reject(
          new ApiError('NETWORK_ERROR', "Cannot connect to the server. Make sure it's running on port 8000.", {}),
        )
      }
      return Promise.reject(new ApiError('UNKNOWN_ERROR', error.message, {}, error.response.status))
    }
    return Promise.reject(error)
  },
)
