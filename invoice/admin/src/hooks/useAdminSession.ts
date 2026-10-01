import { useEffect, useState } from 'react'
import { adminApi, setAuthToken, type AdminUserResponse } from '../api'

const TOKEN_KEY = 'admin_token'

interface UseAdminSessionResult {
  token: string | null
  adminUser: AdminUserResponse | null
  isSuper: boolean
  loginError: string
  loginLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export function useAdminSession(): UseAdminSessionResult {
  const [token, setToken] = useState<string | null>(localStorage.getItem(TOKEN_KEY))
  const [adminUser, setAdminUser] = useState<AdminUserResponse | null>(null)
  const [loginError, setLoginError] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)

  const fetchMe = async () => {
    try {
      const me = await adminApi.me()
      setAdminUser(me)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } }
      if (axiosErr.response?.status === 401) {
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setAuthToken(null)
      }
      setAdminUser(null)
    }
  }

  useEffect(() => {
    if (token) {
      setAuthToken(token)
      void fetchMe()
    } else {
      setAdminUser(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const login = async (username: string, password: string) => {
    setLoginError('')
    setLoginLoading(true)
    try {
      const data = await adminApi.login(username, password)
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setAuthToken(data.access_token)
      setToken(data.access_token)
      await fetchMe()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number }; message?: string }
      if (!axiosErr.response) {
        setLoginError('Нет связи с API. Проверьте адрес сервера и доступность API.')
      } else if (axiosErr.response.status === 401) {
        setLoginError('Неверный логин или пароль')
      } else {
        setLoginError(`Ошибка сервера (${axiosErr.response.status})`)
      }
    } finally {
      setLoginLoading(false)
    }
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setAuthToken(null)
    setAdminUser(null)
  }

  return {
    token,
    adminUser,
    isSuper: Boolean(adminUser?.is_super),
    loginError,
    loginLoading,
    login,
    logout,
  }
}
