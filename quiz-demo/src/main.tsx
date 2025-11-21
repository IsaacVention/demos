import "buffer"

import { StrictMode } from "react"
import ReactDOM from "react-dom"

import App from "./app/app"
import { AppProvider } from "./app/app-context"
import { ThemeProvider } from "@mui/material"
import { machineUiTheme } from "@ventionco/machine-ui"

ReactDOM.render(
  <StrictMode>
    <ThemeProvider theme={machineUiTheme}>
      <AppProvider>
        <App />
      </AppProvider>
    </ThemeProvider>
  </StrictMode>,
  document.getElementById("root")
)
