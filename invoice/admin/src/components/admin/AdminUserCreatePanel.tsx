import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { adminApi, type AdminUserResponse } from '../../api'
import { useToast } from '../../lib/toast'

export function AdminUserCreatePanel() {
  const showToast = useToast()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [createdThisSession, setCreatedThisSession] = useState<AdminUserResponse[]>([])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const trimmedUsername = username.trim()
    if (trimmedUsername.length < 3) {
      setError('Логин должен быть не короче 3 символов')
      return
    }
    if (password.length < 8) {
      setError('Пароль должен быть не короче 8 символов')
      return
    }
    if (password !== confirmPassword) {
      setError('Пароли не совпадают')
      return
    }
    setLoading(true)
    try {
      const created = await adminApi.createAdminUser({ username: trimmedUsername, password })
      setCreatedThisSession((prev) => [...prev, created])
      setUsername('')
      setPassword('')
      setConfirmPassword('')
      showToast(`Пользователь «${created.username}» создан`, 'success')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      setError(axiosErr.response?.data?.detail || 'Не удалось создать пользователя')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h3>Новый пользователь админки</h3>
      <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        Создаёт обычного администратора (без прав супер-админа). Список существующих пользователей пока
        недоступен через админку — только создание.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="row">
          <label>
            Логин
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
          </label>
          <label>
            Пароль
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                style={{ paddingRight: 36 }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                style={{
                  position: 'absolute',
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  color: '#6b7280',
                }}
                aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>
          <label>
            Повторите пароль
            <input
              type={showPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>
        </div>
        {error && <div className="error">{error}</div>}
        <div className="row" style={{ marginTop: 12 }}>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Создание…' : 'Создать пользователя'}
          </button>
        </div>
      </form>
      {createdThisSession.length > 0 && (
        <>
          <h3 style={{ marginTop: 20 }}>Созданы в этой сессии</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Логин</th>
                <th>ID</th>
              </tr>
            </thead>
            <tbody>
              {createdThisSession.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
