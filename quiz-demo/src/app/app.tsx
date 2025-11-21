import { HashRouter, Routes, Route, Navigate } from "react-router-dom"
import { SettingsPage } from "./pages/settings-page"
import { OperationPage } from "./pages/operation-page"
import { Box, Theme, useTheme } from "@mui/material"
import { IconSettings, IconHome } from "@tabler/icons-react"
import { NavigationBar, StatusTopBar } from "@vention/machine-apps-components"
import { useEffect, useState } from "react"
import { useApp } from "./app-context"

export function App() {
  const { state, triggerStart, triggerReset, triggerFault } = useApp()
  const theme = useTheme()
  const [visibleButtons, setVisibleButtons] = useState<string[]>([])
  const [disabledButtons, setDisabledButtons] = useState<string[]>([])

  // ---------------------------------------------
  // Helpers for top-bar appearance
  // ---------------------------------------------
  const getStatusAndBackgroundColor = (applicationState: string, theme: Theme) => {
    switch (applicationState) {
      case "ready":
        return { statusColor: theme.palette.background.success, label: "Ready" }
      case "QuizStates_generating":
        return { statusColor: theme.palette.background.slate, label: "Generating" }
      case "QuizStates_grading":
        return { statusColor: theme.palette.background.warning, label: "Grading" }
      case "QuizStates_presenting":
        return { statusColor: theme.palette.background.blue, label: "Presenting" }
      case "fault":
        return { statusColor: theme.palette.background.destructive, label: "Fault" }
      default:
        return { statusColor: theme.palette.background.slate, label: "Unknown" }
    }
  }

  // ---------------------------------------------
  // Update visible / disabled buttons when FSM changes
  // ---------------------------------------------
  useEffect(() => {
    switch (state) {
      case "ready":
        setVisibleButtons(["start", "stop"])
        setDisabledButtons(["stop"])
        break
    case "QuizStates_generating":
      case "QuizStates_grading":
      case "QuizStates_presenting":
        setVisibleButtons(["start", "stop"])
        setDisabledButtons(["start"])
        break
      case "fault":
        setVisibleButtons(["start", "reset"])
        setDisabledButtons(["start"])
        break
      default:
        setVisibleButtons([])
        setDisabledButtons([])
    }
  }, [state])

  // ---------------------------------------------
  // Render
  // ---------------------------------------------
  return (
    <HashRouter>
      <Box sx={{ height: "100vh", overflow: "hidden" }}>
        <StatusTopBar
          statusLabel={getStatusAndBackgroundColor(state, theme).label}
          dotColor={getStatusAndBackgroundColor(state, theme).statusColor}
          visibleButtons={visibleButtons}
          disabledButtons={disabledButtons}
        >
          <StatusTopBar.Button
            id="start"
            label="Start"
            onClick={triggerStart}
            backgroundColor={theme.palette.background.blue}
            textColor="white"
          />
          <StatusTopBar.Button
            id="stop"
            label="Stop"
            onClick={triggerFault}
            backgroundColor={theme.palette.background.destructive}
            textColor="white"
          />
          <StatusTopBar.Button
            id="reset"
            label="Reset"
            onClick={triggerReset}
            backgroundColor={theme.palette.background.warning}
            textColor="white"
          />
        </StatusTopBar>

        <Box sx={{ paddingTop: "128px", height: "calc(100vh - 128px)", overflow: "hidden" }}>
          <Routes>
            <Route path="/" element={<Navigate to="/quiz" replace />} />
            <Route path="/quiz" element={<OperationPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/quiz" replace />} />
          </Routes>
        </Box>

        <NavigationBar>
          <NavigationBar.Item id="operation" label="Operation" path="/quiz" icon={<IconHome size={42} color="white" />} />
          <NavigationBar.Item id="settings" label="Settings" path="/settings" icon={<IconSettings size={42} color="white" />} />
        </NavigationBar>
      </Box>
    </HashRouter>
  )
}

export default App