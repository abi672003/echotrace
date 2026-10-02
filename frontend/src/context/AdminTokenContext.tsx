import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { setAdminToken } from '../api/client'

const STORAGE_KEY = 'echotrace.adminToken'

interface AdminTokenContextValue {
  token: string
  setToken: (token: string) => void
}

const AdminTokenContext = createContext<AdminTokenContextValue | undefined>(undefined)

function readStoredToken(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function AdminTokenProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string>(readStoredToken)

  useEffect(() => {
    setAdminToken(token || null)
    try {
      if (token) {
        localStorage.setItem(STORAGE_KEY, token)
      } else {
        localStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      // localStorage unavailable (e.g. private browsing); token still held for this session.
    }
  }, [token])

  return (
    <AdminTokenContext.Provider value={{ token, setToken: setTokenState }}>
      {children}
    </AdminTokenContext.Provider>
  )
}

export function useAdminToken(): AdminTokenContextValue {
  const context = useContext(AdminTokenContext)
  if (!context) {
    throw new Error('useAdminToken must be used within an AdminTokenProvider')
  }
  return context
}
