import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'echotrace.hideNames'

interface HideNamesContextValue {
  hideNames: boolean
  setHideNames: (value: boolean) => void
}

const HideNamesContext = createContext<HideNamesContextValue | undefined>(undefined)

function readStoredPreference(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === null ? true : stored === 'true' // default ON, per DESIGN_SYSTEM §6
  } catch {
    return true
  }
}

export function HideNamesProvider({ children }: { children: ReactNode }) {
  const [hideNames, setHideNames] = useState<boolean>(readStoredPreference)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(hideNames))
    } catch {
      // localStorage unavailable; preference still held for this session.
    }
  }, [hideNames])

  return (
    <HideNamesContext.Provider value={{ hideNames, setHideNames }}>
      {children}
    </HideNamesContext.Provider>
  )
}

export function useHideNames(): HideNamesContextValue {
  const context = useContext(HideNamesContext)
  if (!context) {
    throw new Error('useHideNames must be used within a HideNamesProvider')
  }
  return context
}

/** `Submitter a3f9`-style display per DESIGN_SYSTEM §6, using the document's own hash. */
export function displaySubmitter(label: string, hideNames: boolean, hashHint: string): string {
  if (!hideNames) {
    return label
  }
  return `Submitter ${hashHint.slice(0, 4)}`
}
