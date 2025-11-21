/**
 * API Types and Functions for Quiz Application
 *
 * This module defines all the types and API functions used to communicate
 * with the backend server for the quiz application.
 */

// -------------------------------
// Data Types
// -------------------------------

export type Quiz = {
  id: number
  box_height: number
  num_boxes: number
  can_reach: boolean | null // User's answer: whether robot can reach all boxes
  correct: boolean | null // Whether the user's answer was correct (auto-calculated)
}

export type Configuration = {
  id: number
  max_box_height: number // Maximum height of a box in millimeters
  robot_reach: number // Robot arm reach distance in millimeters
  timeout_seconds: number // Timeout in seconds for quiz answers
}

// -------------------------------
// State Machine Types
// -------------------------------

export enum StateMachineState {
  ready = "ready",
  generating = "QuizStates_generating", // Creating a new quiz problem
  grading = "QuizStates_grading", // Waiting for user response
  presenting = "QuizStates_presenting", // Displaying the problem to user
  fault = "fault", // System error state
}

export enum StateMachineTrigger {
  start = "start", // Start the quiz process
  problem_generated = "problem_generated", // Problem has been created
  answer_submitted = "answer_submitted", // User submitted their answer
  to_fault = "to_fault", // Transition to fault state
  reset = "reset", // Reset the system
}

export enum StateMachineUpdateTrigger {
  countdown = "countdown", // Timeout countdown update (internal trigger used by the state machine)
}

export type StateMachineUpdate = {
  old: StateMachineState // Previous state
  new: StateMachineState // New state
  trigger: StateMachineTrigger // Trigger that caused the state change
  time_remaining?: number // Seconds remaining for current question (only present in grading state)
}

// -------------------------------
// Configuration API Functions
// -------------------------------

/**
 * Fetch the current system configuration
 */
export async function getConfig(httpBaseUrl: string): Promise<Configuration> {
  const result = await fetch(`${httpBaseUrl}/config/`)
  if (!result.ok) throw new Error("Failed to fetch configuration")
  const data = await result.json()

  return data[0] // Configuration is stored as a single record
}

/**
 * Update the system configuration
 */
export async function updateConfig(id: number, httpBaseUrl: string, payload: Partial<Configuration>): Promise<Configuration> {
  const result = await fetch(`${httpBaseUrl}/config/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-User": "frontend" },
    body: JSON.stringify(payload),
  })
  if (!result.ok) {
    const errorMessage = await result.text()
    throw new Error(`Failed to update config: ${errorMessage}`)
  }

  return result.json()
}

// -------------------------------
// Quiz Data API Functions
// -------------------------------

/**
 * Update a quiz record with user's answer
 */
export async function updateQuiz(id: number, httpBaseUrl: string, payload: Partial<Quiz>): Promise<Quiz> {
  const result = await fetch(`${httpBaseUrl}/quiz/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-User": "frontend" },
    body: JSON.stringify(payload),
  })
  if (!result.ok) throw new Error("Failed to update quiz")

  return result.json()
}

/**
 * Get the most recent quiz problem
 */
export async function getLatestQuiz(httpBaseUrl: string): Promise<Quiz | null> {
  const result = await fetch(`${httpBaseUrl}/quiz/`)
  if (!result.ok) throw new Error("Failed to fetch latest quiz")
  const data = await result.json()

  if (data.length > 0) {
    return data[data.length - 1] // Return the most recent quiz
  }

  return null
}

// -------------------------------
// State Machine API Functions
// -------------------------------

/**
 * Trigger a state machine transition
 */
export async function triggerStateMachine(httpBaseUrl: string, trigger: StateMachineTrigger): Promise<void> {
  const result = await fetch(`${httpBaseUrl}/server/${trigger}`, { method: "POST" })
  if (!result.ok) throw new Error(`Failed to trigger ${trigger}`)
}

/**
 * Get the current state machine state and time remaining
 */
export async function getStateMachineState(httpBaseUrl: string): Promise<{ state: StateMachineState; time_remaining?: number }> {
  const result = await fetch(`${httpBaseUrl}/server/state`)
  if (!result.ok) throw new Error("Failed to fetch state machine state")

  return result.json()
}
