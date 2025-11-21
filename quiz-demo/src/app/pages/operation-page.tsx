import React, { useState, useEffect } from "react"
import { Box, Typography } from "@mui/material"
import { VentionButton, VentionAlert, VentionSpinner, VentionProgressBar, VentionTabs } from "@ventionco/machine-ui"
import { tss } from "tss-react/mui"
import { useApp } from "../app-context"
import { client } from "../client"

export const OperationPage = () => {
  const { classes } = useStyles()

  // --- From app-context (streamed state + config + quiz) ---
  const { state, config, latestQuiz, timeRemaining } = useApp()

  // --- Local UI state ---
  const [answer, setAnswer] = useState<boolean>(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // --- Effect: reset local answer when quiz changes ---
  useEffect(() => {
    setAnswer(false)
  }, [latestQuiz])

  // --- Handler: submit quiz answer ---
  const submitAnswer = async () => {
    if (!latestQuiz) return
    try {
      setSubmitting(true)
      setError(null)
      
      await client.quiz_UpdateRecord({
        recordId: latestQuiz.id,
        record: { ...latestQuiz, canReach: answer ?? false },
        actor: "frontend",
      })

      // Trigger FSM transition
      await client.trigger_Answer_submitted({})
    } catch (err) {
      console.error("Failed to submit answer:", err)
      setError(err.message ?? "Failed to submit answer")
    } finally {
      setSubmitting(false)
    }
  }

  // --- Render UI ---
  return (
    <Box className={classes.root}>
      <Box className={classes.center}>
        {/* Generating State */}
        {state === "QuizStates_generating" && (
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

        {/* Grading State */}
        {state === "QuizStates_grading" && (
          <Box>
            {error && <VentionAlert severity="error" descriptionText={error} size="xx-large" isFullWidth />}

            {latestQuiz ? (
              <Box className={classes.quizCard}>
                <Typography className={classes.problemDescription}>{"Robot reach: " + config?.robotReach + " mm"}</Typography>
                <Typography className={classes.problemDescription}>{"Box height: " + latestQuiz.boxHeight + " mm"}</Typography>
                <Typography className={classes.problemDescription}>{"Number of layers: " + latestQuiz.numBoxes}</Typography>
                <Typography className={classes.problemDescription}>Can the robot reach the top of the stack?</Typography>

                <Box className={classes.answerRow}>
                  <VentionTabs tabOptions={["Yes", "No"]} value={answer ? 0 : 1} onChange={(_, index) => setAnswer(index === 0)} />
                  <VentionButton variant="filled-brand" size="large" onClick={submitAnswer} loading={submitting}>
                    Submit
                  </VentionButton>
                </Box>

                <VentionProgressBar value={((timeRemaining ?? 0) / (config?.timeoutSeconds || 10)) * 100} size="medium" />
              </Box>
            ) : (
              <VentionSpinner size="large" />
            )}
          </Box>
        )}

        {/* Fault State */}
        {state === "fault" && (
          <Box className={classes.center}>
            <VentionAlert
              severity="error"
              title="System is in FAULT"
              descriptionText="Click the RESET button to continue."
              size="xx-large"
            />
          </Box>
        )}

        {/* Ready State */}
        {state === "ready" && (
          <VentionAlert severity="info" title="Ready to start the quiz" descriptionText="Press PLAY to begin." size="xx-large" />
        )}
      </Box>
    </Box>
  )
}

// -------------------------------
// Styles
// -------------------------------
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

export default OperationPage