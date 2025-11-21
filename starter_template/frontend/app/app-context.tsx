/**
 * Application Context and State Management
 *
 * This module provides React context for managing application state,
 * including configuration, quiz data, and state machine interactions.
 */

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react"
import {
  Configuration,
  Quiz,
  StateMachineState,
  StateMachineTrigger,
  StateMachineUpdate,
  getConfig,
  updateConfig,
  getLatestQuiz,
  getStateMachineState,
  triggerStateMachine,
} from "./api"

// -------------------------------
// URL Configuration
// -------------------------------

const PROCESS_NAME = "quiz"

/**
 * Determine the HTTP base URL for API calls based on the current environment
 */
function getExecutionEngineHttpUrl() {
  const { href, port, hostname, origin } = window.location
  const pathParts = new URL(href).pathname.split("/").filter(Boolean)

  // Find sessionId either after "passthrough" or before "hmi"
  const passthroughIndex = pathParts.indexOf("passthrough")
  const hmiIndex = pathParts.indexOf("hmi")

  const sessionId =
    passthroughIndex >= 0 && passthroughIndex < pathParts.length - 1
      ? pathParts[passthroughIndex + 1]
      : hmiIndex > 0
        ? pathParts[hmiIndex - 1]
        : ""

  const basePath = `/digital-twin/machine-motion/passthrough/${sessionId}/80/v1/machineCode/services/${PROCESS_NAME}`

  // Use external digital twin URL in dev, current origin in production
  const isDev = port === "5173" || hostname === "localhost"
  const baseOrigin = isDev ? "https://digital-twin.vention.foo" : origin

  return `${baseOrigin}${basePath}`
}

// Determine if running on edge device or in development
const isOnEdge = window.location.hostname.startsWith("192.168") || window.location.hostname.startsWith("localhost")
const httpBaseUrl = isOnEdge ? `http://${window.location.hostname}:8000` : getExecutionEngineHttpUrl()

// -------------------------------
// Context Type Definitions
// -------------------------------

/**
 * Complete application context value containing all state and functions
 */
type AppContextValue = {
  // Configuration management
  config: Configuration | null
  configError: string | null
  refreshConfig: () => Promise<void>
  saveConfig: (payload: Partial<Configuration>) => Promise<void>

  // Quiz data
  latestQuiz: Quiz | null

  // State machine management
  stateMachineState: StateMachineState
  lastStateMachineUpdate: StateMachineUpdate | null
  triggerStateMachineAction: (name: StateMachineTrigger) => Promise<void>

  // API configuration
  httpBaseUrl: string
}

// -------------------------------
// Context and Provider
// -------------------------------

const AppContext = createContext<AppContextValue | undefined>(undefined)

/**
 * Main application provider that manages all application state
 */
export function AppProvider({ children }: { children: ReactNode }) {
  // -------------------------------
  // State Management
  // -------------------------------

  // Configuration state
  const [config, setConfig] = useState<Configuration | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)

  // Quiz data state
  const [latestQuiz, setLatestQuiz] = useState<Quiz | null>(null)

  // State machine state
  const [stateMachineState, setStateMachineState] = useState<StateMachineState>(StateMachineState.ready)
  const [lastStateMachineUpdate, setLastStateMachineUpdate] = useState<StateMachineUpdate | null>(null)
  const [isUserActionInProgress, setIsUserActionInProgress] = useState(false)

  // -------------------------------
  // Configuration Management Functions
  // -------------------------------

  /**
   * Load configuration from the server
   */
  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await getConfig(httpBaseUrl)
      setConfig(cfg)
      setConfigError(null)
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : "Failed to load config")
      console.error("Failed to load config", err)
    }
  }, [])

  /**
   * Save configuration changes to the server
   */
  const saveConfig = useCallback(
    async (payload: Partial<Configuration>) => {
      if (!config) return
      const updated = await updateConfig(config.id, httpBaseUrl, { ...config, ...payload })
      setConfig(updated)
    },
    [config]
  )

  // -------------------------------
  // State Machine Management Functions
  // -------------------------------

  /**
   * Trigger a state machine transition with immediate UI feedback
   */
  const triggerStateMachineAction = useCallback(
    async (name: StateMachineTrigger) => {
      try {
        // Prevent polling conflicts during user actions
        setIsUserActionInProgress(true)

        // Send trigger to server
        await triggerStateMachine(httpBaseUrl, name)

        // Get updated state immediately for responsive UI
        const stateData = await getStateMachineState(httpBaseUrl)
        const newState = stateData.state as StateMachineState

        // Update state if it changed
        if (newState !== stateMachineState) {
          setStateMachineState(newState)

          // Create state update record
          const update: StateMachineUpdate = {
            old: stateMachineState,
            new: newState,
            trigger: name,
            time_remaining: stateData.time_remaining,
          }
          setLastStateMachineUpdate(update)

          // Load latest quiz when entering grading state
          if (newState === StateMachineState.grading) {
            getLatestQuiz(httpBaseUrl)
              .then(quiz => {
                if (quiz) {
                  setLatestQuiz(quiz)
                }
              })
              .catch(err => console.error("Failed to fetch latest quiz", err))
          }
        }
      } catch (err) {
        console.error("Failed to trigger state machine action", err)
      } finally {
        // Re-enable polling after user action completes
        setTimeout(() => setIsUserActionInProgress(false), 500)
      }
    },
    [stateMachineState]
  )

  // -------------------------------
  // Initialization and Polling
  // -------------------------------

  useEffect(() => {
    // Load initial configuration
    refreshConfig()

    // Initialize state machine state
    const initializeState = async () => {
      try {
        const stateData = await getStateMachineState(httpBaseUrl)
        setStateMachineState(stateData.state as StateMachineState)
      } catch (err) {
        console.error("Failed to fetch initial state", err)
      }
    }
    initializeState()

    // Set up automatic polling for state machine updates
    const pollInterval = setInterval(async () => {
      // Skip polling during user actions to prevent conflicts
      if (isUserActionInProgress) {
        return
      }

      try {
        const stateData = await getStateMachineState(httpBaseUrl)
        const newState = stateData.state as StateMachineState

        // Handle state changes
        if (newState !== stateMachineState) {
          setStateMachineState(newState)

          // Create state update record
          const update: StateMachineUpdate = {
            old: stateMachineState,
            new: newState,
            trigger: "polling" as StateMachineTrigger,
            time_remaining: stateData.time_remaining,
          }
          setLastStateMachineUpdate(update)

          // Load quiz data when entering grading state
          if (newState === StateMachineState.grading) {
            getLatestQuiz(httpBaseUrl)
              .then(quiz => {
                if (quiz) {
                  setLatestQuiz(quiz)
                }
              })
              .catch(err => console.error("Failed to fetch latest quiz", err))
          }
        } else if (stateData.time_remaining !== undefined) {
          // Update countdown timer if state hasn't changed
          setLastStateMachineUpdate(prev => (prev ? { ...prev, time_remaining: stateData.time_remaining } : null))
        }
      } catch (err) {
        console.error("Failed to poll state machine state", err)
      }
    }, 1000) // Poll every second for real-time updates

    return () => {
      clearInterval(pollInterval)
    }
  }, [refreshConfig, stateMachineState, isUserActionInProgress])

  // -------------------------------
  // Context Value and Provider
  // -------------------------------

  const value: AppContextValue = {
    // Configuration management
    config,
    configError,
    refreshConfig,
    saveConfig,

    // Quiz data
    latestQuiz,

    // State machine management
    stateMachineState,
    lastStateMachineUpdate,
    triggerStateMachineAction,

    // API configuration
    httpBaseUrl,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// -------------------------------
// Context Hooks
// -------------------------------

/**
 * Main hook for accessing the complete application context
 */
export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp must be used inside AppProvider")

  return ctx
}

/**
 * Hook for configuration management
 */
export function useConfig() {
  const { config, configError, refreshConfig, saveConfig } = useApp()

  return { config, error: configError, refresh: refreshConfig, save: saveConfig }
}

/**
 * Hook for quiz data access
 */
export function useQuiz() {
  const { latestQuiz } = useApp()

  return { latest: latestQuiz }
}

/**
 * Hook for state machine management
 */
export function useStateMachine() {
  const { stateMachineState, lastStateMachineUpdate, triggerStateMachineAction } = useApp()

  return {
    state: stateMachineState,
    lastUpdate: lastStateMachineUpdate,
    trigger: triggerStateMachineAction,
  }
}
