/**
 * Quiz Operation Page
 *
 * This component handles the main quiz interaction, displaying problems
 * and allowing users to submit answers with real-time feedback.
 */

import React, { useState, useEffect } from "react"
import { Box, Typography } from "@mui/material"
import { VentionButton, VentionAlert, VentionSpinner, VentionProgressBar, VentionTabs } from "@ventionco/machine-ui"
import { tss } from "tss-react/mui"

import { useStateMachine, useQuiz, useConfig, useApp } from "../app-context"
import { StateMachineState, StateMachineTrigger, updateQuiz } from "../api"

export const OperationPage = () => {
  // -------------------------------
  // Component State and Hooks
  // -------------------------------

  const { classes } = useStyles()
  const { state, trigger, lastUpdate } = useStateMachine()
  const { latest } = useQuiz()
  const { config } = useConfig()
  const { httpBaseUrl } = useApp()

  // Local component state
  const [answer, setAnswer] = useState<boolean>(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null)

  // -------------------------------
  // Effect Handlers
  // -------------------------------

  useEffect(() => {
    // Update countdown timer from state machine updates
    if (lastUpdate?.time_remaining !== undefined) {
      setTimeRemaining(lastUpdate.time_remaining)
    } else if (state !== StateMachineState.grading) {
      setTimeRemaining(null)
    }
  }, [lastUpdate, state])

  // -------------------------------
  // Event Handlers
  // -------------------------------

  /**
   * Submit the user's answer to the current quiz question
   */
  async function submitAnswer() {
    if (!latest) return

    try {
      setSubmitting(true)
      setError(null)

      // Update quiz with user's answer
      await updateQuiz(latest.id, httpBaseUrl, { can_reach: answer || false })

      // Trigger state machine transition
      await trigger(StateMachineTrigger.answer_submitted)

      // Reset answer for next question
      setAnswer(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit answer")
    } finally {
      setSubmitting(false)
    }
  }

  // -------------------------------
  // Component Render
  // -------------------------------

  return (
    <Box className={classes.root}>
      <Box className={classes.center}>
        {/* Generating State: Show loading spinner */}
        {state === StateMachineState.generating && (
          <VentionAlert
            severity="warn"
            title="Generating new problem..."
            descriptionText={
              <Box className={classes.center} sx={{ pt: 1, pb: 1 }}>
                <VentionSpinner size="large" />
              </Box>
            }
            size="xx-large"
          />
        )}

        {/* Grading State: Show quiz question and answer interface */}
        {state === StateMachineState.grading && (
          <Box>
            {error && <VentionAlert severity="error" descriptionText={error} size="xx-large" isFullWidth />}

            {latest ? (
              <Box className={classes.quizCard}>
                <Typography className={classes.problemDescription}>{"Robot reach: " + config?.robot_reach + " mm"}</Typography>
                <Typography className={classes.problemDescription}>{"Box height: " + latest.box_height + " mm"}</Typography>
                <Typography className={classes.problemDescription}>{"Number of layers: " + latest.num_boxes}</Typography>
                <Typography className={classes.problemDescription}>Can the robot reach the top of the stack?</Typography>
                <Box className={classes.answerRow}>
                  <VentionTabs
                    tabOptions={["Yes", "No"]}
                    value={answer ? 0 : 1}
                    onChange={(_, index) => setAnswer(index === 0 ? true : false)}
                  />
                  <VentionButton variant="filled-brand" size="large" onClick={submitAnswer} loading={submitting}>
                    Submit
                  </VentionButton>
                </Box>
                <VentionProgressBar value={(timeRemaining / (config?.timeout_seconds || 10)) * 100} size="medium" />
              </Box>
            ) : (
              <VentionSpinner size="large" />
            )}
          </Box>
        )}

        {/* Fault State: Show error message */}
        {state === StateMachineState.fault && (
          <Box className={classes.center}>
            <VentionAlert
              severity="error"
              title="System is in FAULT"
              descriptionText="Click the RESET button to continue."
              size="xx-large"
            />
          </Box>
        )}

        {/* Ready State: Show start message */}
        {state === StateMachineState.ready && (
          <VentionAlert severity="info" title="Ready to start the quiz" descriptionText="Press PLAY to begin." size="xx-large" />
        )}
      </Box>
    </Box>
  )
}

const useStyles = tss.create(({ theme }) => ({
  root: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  center: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "80%",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: theme.spacing(4),
  },
  quizCard: {
    display: "flex",
    flexDirection: "column",
    gap: theme.spacing(3),
    maxWidth: "1000px",
  },
  problemDescription: {
    fontSize: "2rem",
    fontWeight: 500,
    marginBottom: theme.spacing(5),
    marginTop: theme.spacing(5),
    textAlign: "center",
  },
  answerRow: {
    display: "flex",
    gap: theme.spacing(2),
    justifyContent: "center",
  },
}))
