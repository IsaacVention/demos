import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react"
import { client } from "./client"
import type { Configuration, Quiz, StateChangeEvent } from "./gen/app_pb"

// ---------------------------------------------
// Context type
// ---------------------------------------------
interface AppContextValue {
  // Configuration
  config: Configuration | null
  refreshConfig: () => Promise<void>
  saveConfig: (payload: Partial<Configuration>) => Promise<void>

  // Quiz
  latestQuiz: Quiz | null

  // State machine
  state: string
  lastState: string | null
  timeRemaining: number | null
  isStreaming: boolean
  startStreaming: () => void
  stopStreaming: () => void
  triggerStart: () => Promise<void>
  triggerReset: () => Promise<void>
  triggerFault: () => Promise<void>
  triggerReady: () => Promise<void>
}

const AppContext = createContext<AppContextValue | null>(null)

// ---------------------------------------------
// Provider
// ---------------------------------------------
export const AppProvider = ({ children }: { children: ReactNode }) => {
  // Configuration
  const [config, setConfig] = useState<Configuration | null>(null)

  // Quiz
  const [latestQuiz, setLatestQuiz] = useState<Quiz | null>(null)

  // State machine
  const [state, setState] = useState("unknown")
  const [lastState, setLastState] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [abortController, setAbortController] = useState<AbortController | null>(null)
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null)

  // ----------------------------------------------------
  // CONFIGURATION MANAGEMENT
  // ----------------------------------------------------
  const refreshConfig = useCallback(async () => {
    try {
      const resp = await client.config_ListRecords({})
      setConfig(resp.records?.[0] ?? null)
    } catch (err) {
      console.error("Failed to load config:", err)
    }
  }, [])

  const getState = useCallback(async () => {
    const state = await client.getState({})
    setState(state.state)
    setLastState(state.lastState)
  }, [])

  useEffect(() => {
    getState()
    refreshLatestQuiz()
  }, [])

  useEffect(() => {
    startStreaming()
    return () => stopStreaming()
  }, [])

  useEffect(() => {
    async function fetchCountdown() {
      const stream = client.countdown({}, { signal: abortController?.signal })
      for await (const event of stream) {
        setTimeRemaining(event.timeRemaining)
      }
    }
    fetchCountdown()
  }, [abortController])

  const saveConfig = useCallback(
    async (payload: Partial<Configuration>) => {
      if (!config) return
      try {
        const updated = await client.config_UpdateRecord({
          recordId: config.id,
          record: { ...config, ...payload },
          actor: "frontend",
        })

        setConfig(updated.record ?? null)
      } catch (err) {
        console.error("Failed to save config:", err)
      }
    },
    [config]
  )

  // ----------------------------------------------------
  // QUIZ MANAGEMENT
  // ----------------------------------------------------
  const refreshLatestQuiz = useCallback(async () => {
    try {
      const res = await client.quiz_ListRecords({})
      if (res.records && res.records.length > 0) {
        // assume newest record is last
        setLatestQuiz(res.records[res.records.length - 1])
      }
    } catch (err) {
      console.error("Failed to fetch latest quiz:", err)
    }
  }, [])

  // ----------------------------------------------------
  // STATE MACHINE STREAM
  // ----------------------------------------------------
  const startStreaming = useCallback(() => {
    if (isStreaming) return
    const ac = new AbortController()
    setAbortController(ac)
    setIsStreaming(true)
    ;(async () => {
      try {
        const stream = client.state_change({}, { signal: ac.signal })
        for await (const event of stream) {
          const stateChangeEvent = event as StateChangeEvent
          setLastState(stateChangeEvent.oldState)
          setState(stateChangeEvent.newState)
          if (stateChangeEvent.newState === "QuizStates_grading") refreshLatestQuiz()
        }
      } catch (err) {
        if (err.name !== "AbortError") console.error("Stream error:", err)
      } finally {
        setIsStreaming(false)
      }
    })()
  }, [isStreaming, refreshLatestQuiz])

  const stopStreaming = useCallback(() => {
    abortController?.abort()
    setAbortController(null)
    setIsStreaming(false)
  }, [abortController])

  // ----------------------------------------------------
  // STATE MACHINE TRIGGERS
  // ----------------------------------------------------
  const triggerStart = useCallback(async () => {
    await client.trigger_Start({})
  }, [])
  const triggerReset = useCallback(async () => {
    await client.trigger_Reset({})
  }, [])
  const triggerFault = useCallback(async () => {
    await client.trigger_To_fault({})
  }, [])
  const triggerReady = useCallback(async () => {
    await client.trigger_To_ready({})
  }, [])

  // ----------------------------------------------------
  // INITIALIZATION
  // ----------------------------------------------------
  useEffect(() => {
    refreshConfig()
  }, [refreshConfig])

  // ----------------------------------------------------
  // VALUE
  // ----------------------------------------------------
  const value: AppContextValue = {
    config,
    refreshConfig,
    saveConfig,
    latestQuiz,
    state,
    lastState,
    timeRemaining,
    isStreaming,
    startStreaming,
    stopStreaming,
    triggerStart,
    triggerReset,
    triggerFault,
    triggerReady,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// ---------------------------------------------
// Hook
// ---------------------------------------------
export const useApp = () => {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp must be used within an AppProvider")
  return ctx
}