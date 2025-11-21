import { HashRouter, Routes, Route, Navigate } from "react-router-dom"
import { SettingsPage } from "./pages/settings-page"
import { OperationPage } from "./pages/operation-page"
import { Box, Theme, useTheme } from "@mui/material"
import { IconSettings, IconHome } from "@tabler/icons-react"
import { NavigationBar, StatusTopBar } from "@vention/machine-apps-components"
import { useEffect, useState } from "react"
import { useStateMachine } from "./app-context"
import { StateMachineState, StateMachineTrigger } from "./api"

export function App() {
  const { state, trigger } = useStateMachine()
  const theme = useTheme()
  const [visibleButtons, setVisibleButtons] = useState<string[]>([])
  const [disabledButtons, setDisabledButtons] = useState<string[]>([])

  const getStatusAndBackgroundColor = (applicationState: StateMachineState, theme: Theme) => {
    switch (applicationState) {
      case StateMachineState.ready:
        return { statusColor: theme.palette.background.success, label: "Ready" }
      case StateMachineState.generating:
        return { statusColor: theme.palette.background.slate, label: "Generating" }
      case StateMachineState.grading:
        return { statusColor: theme.palette.background.warning, label: "Grading" }
      case StateMachineState.presenting:
        return { statusColor: theme.palette.background.blue, label: "Presenting" }
      case StateMachineState.fault:
        return { statusColor: theme.palette.background.destructive, label: "Fault" }
      default:
        return { statusColor: theme.palette.background.slate, label: "Unknown" }
    }
  }

  useEffect(() => {
    switch (state) {
      case StateMachineState.ready:
        setVisibleButtons(["start", "stop"])
        setDisabledButtons(["stop"])
        break
      case StateMachineState.generating:
      case StateMachineState.grading:
      case StateMachineState.presenting:
        setVisibleButtons(["start", "stop"])
        setDisabledButtons(["start"])
        break
      case StateMachineState.fault:
        setVisibleButtons(["start", "reset"])
        setDisabledButtons(["start"])
        break
      default:
        setVisibleButtons([])
        setDisabledButtons([])
    }
  }, [state])

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
            onClick={() => trigger(StateMachineTrigger.start)}
            backgroundColor={theme.palette.background.blue}
            textColor="white"
          />
          <StatusTopBar.Button
            id="stop"
            label="Stop"
            onClick={() => trigger(StateMachineTrigger.to_fault)}
            backgroundColor={theme.palette.background.destructive}
            textColor="white"
          />
          <StatusTopBar.Button
            id="reset"
            label="Reset"
            onClick={() => trigger(StateMachineTrigger.reset)}
            backgroundColor={theme.palette.background.warning}
            textColor="white"
          />
        </StatusTopBar>
        <Box sx={{ paddingTop: "128px", height: "calc(100vh - 128px)", overflow: "hidden" }}>
          <Routes>
            <Route path="/" element={<Navigate to="/quiz" replace />} />
            <Route path="/quiz" element={<OperationPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/operation" replace />} />
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
