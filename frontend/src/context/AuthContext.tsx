import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  getAuthToken,
  setAuthToken,
  type User,
  type UserRole,
} from '../lib/api'

interface AuthContextType {
  user: User | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (credentials: { email: string; password: string }) => Promise<void>
  logout: () => Promise<void>
  hasRole: (role: UserRole | UserRole[]) => boolean
  isAdmin: boolean
  isReviewer: boolean
  isDataSteward: boolean
  isAuditor: boolean
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getAuthToken())
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  const refreshUser = useCallback(async () => {
    const currentToken = getAuthToken()
    if (!currentToken) {
      setUser(null)
      setIsLoading(false)
      return
    }

    try {
      const userData = await api.getMe()
      setUser(userData)
    } catch {
      // Token expired or invalid
      setAuthToken(null)
      setTokenState(null)
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshUser()
  }, [refreshUser])

  const login = async (credentials: { email: string; password: string }) => {
    setIsLoading(true)
    try {
      const response = await api.login(credentials)
      setAuthToken(response.access_token)
      setTokenState(response.access_token)
      setUser(response.user)
    } finally {
      setIsLoading(false)
    }
  }

  const logout = async () => {
    try {
      if (token) {
        await api.logout()
      }
    } catch {
      // ignore logout network errors
    } finally {
      setAuthToken(null)
      setTokenState(null)
      setUser(null)
    }
  }

  const hasRole = (role: UserRole | UserRole[]): boolean => {
    if (!user) return false
    if (user.role === 'admin') return true // admin has access to all role-gated items
    if (Array.isArray(role)) {
      return role.includes(user.role)
    }
    return user.role === role
  }

  const isAdmin = user?.role === 'admin'
  const isReviewer = user?.role === 'reviewer' || user?.role === 'admin'
  const isDataSteward = user?.role === 'data_steward' || user?.role === 'admin'
  const isAuditor = user?.role === 'auditor' || user?.role === 'admin'

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        hasRole,
        isAdmin,
        isReviewer,
        isDataSteward,
        isAuditor,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
