import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export type OperationKind = 'upload' | 'matching' | 'cnmcMatching' | 'generateMappings'

interface OperationContextValue {
  isActive: (op: OperationKind) => boolean
  begin: (op: OperationKind) => void
  end: (op: OperationKind) => void
}

const OperationContext = createContext<OperationContextValue | null>(null)

export function OperationProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<Record<OperationKind, boolean>>({
    upload: false,
    matching: false,
    cnmcMatching: false,
    generateMappings: false,
  })

  const value = useMemo<OperationContextValue>(
    () => ({
      isActive: (op) => active[op],
      begin: (op) => setActive((prev) => ({ ...prev, [op]: true })),
      end: (op) => setActive((prev) => ({ ...prev, [op]: false })),
    }),
    [active],
  )

  return <OperationContext.Provider value={value}>{children}</OperationContext.Provider>
}

export function useOperation(): OperationContextValue {
  const ctx = useContext(OperationContext)
  if (!ctx) {
    throw new Error('useOperation must be used inside OperationProvider')
  }
  return ctx
}
