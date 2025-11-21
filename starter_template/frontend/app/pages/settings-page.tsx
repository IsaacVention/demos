/**
 * Settings Page Component
 *
 * This component provides a configuration interface for system settings
 * including robot parameters and quiz timeout values.
 */

import React, { useEffect, useState } from "react"
import { tss } from "tss-react/mui"
import { VentionSidebarItem, VentionTextInput, VentionButton } from "@ventionco/machine-ui"
import { useForm, Controller } from "react-hook-form"
import { useConfig } from "../app-context"
import { Configuration } from "../api"

export const SettingsPage = () => {
  // -------------------------------
  // Component State and Hooks
  // -------------------------------

  const { classes } = useStyles()
  const { config, save } = useConfig()

  // Form management
  const {
    control,
    handleSubmit,
    reset,
    formState: { isDirty },
  } = useForm<Configuration>()

  // Local component state
  const [saving, setSaving] = useState(false)

  // -------------------------------
  // Effect Handlers
  // -------------------------------

  useEffect(() => {
    // Reset form when configuration data is loaded
    if (config) {
      reset(config)
    }
  }, [config, reset])

  // -------------------------------
  // Event Handlers
  // -------------------------------

  /**
   * Handle form submission to save configuration changes
   */
  const handleConfigSubmit = async (data: Configuration) => {
    try {
      setSaving(true)
      await save(data)
      reset(data)
    } catch (err) {
      console.error("Error saving config", err)
    } finally {
      setSaving(false)
    }
  }

  // -------------------------------
  // Component Render
  // -------------------------------

  return (
    <div className={classes.pageContainer}>
      <div className={classes.layoutGrid}>
        {/* Left sidebar with navigation */}
        <div className={classes.leftColumn}>
          <div className={classes.sidebarItemContainer}>
            <SidebarItemComponent />
          </div>
        </div>

        {/* Main configuration form */}
        <div className={classes.rightColumn}>
          <form onSubmit={handleSubmit(handleConfigSubmit)}>
            {/* Header with title and save button */}
            <div className={classes.machineSaveSection}>
              <div className={classes.machineInfo}>
                <h2 className={classes.machineTitle}>System Settings</h2>
              </div>
              <div className={classes.saveButtonContainer}>
                <VentionButton
                  variant="filled-brand"
                  size="xx-large"
                  type="submit"
                  loading={saving}
                  disabled={!isDirty || saving}
                  className={classes.saveButton}
                >
                  {saving ? "Saving..." : "Save"}
                </VentionButton>
              </div>
            </div>

            {/* Configuration form sections */}
            <div className={classes.configSection}>
              {/* System Configuration Panel */}
              <div className={classes.panel}>
                <h2 className={classes.panelTitle}>System Configuration</h2>
                <div className={classes.inputFieldGroup}>
                  <label className={classes.inputLabel}>Max Box Height (mm)</label>
                  <Controller
                    name="max_box_height"
                    control={control}
                    render={({ field }) => (
                      <VentionTextInput
                        variant="outlined"
                        type="number"
                        size="x-large"
                        className={classes.input}
                        style={{ width: 394 }}
                        {...field}
                      />
                    )}
                  />
                </div>
                <div className={classes.inputFieldGroup}>
                  <label className={classes.inputLabel}>Robot Reach (mm)</label>
                  <Controller
                    name="robot_reach"
                    control={control}
                    render={({ field }) => (
                      <VentionTextInput
                        variant="outlined"
                        type="number"
                        size="x-large"
                        className={classes.input}
                        style={{ width: 394 }}
                        {...field}
                      />
                    )}
                  />
                </div>
              </div>

              {/* Timer Configuration Panel */}
              <div className={classes.panel}>
                <h2 className={classes.panelTitle}>Timer Configuration</h2>
                <div className={classes.inputFieldGroup}>
                  <label className={classes.inputLabel}>Timeout (s)</label>
                  <Controller
                    name="timeout_seconds"
                    control={control}
                    render={({ field }) => (
                      <VentionTextInput
                        variant="outlined"
                        type="number"
                        size="x-large"
                        className={classes.input}
                        style={{ width: 394 }}
                        {...field}
                      />
                    )}
                  />
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

/**
 * Sidebar navigation component for settings page
 */
function SidebarItemComponent() {
  const { classes } = useStyles()

  return (
    <div className={classes.sidebarItemContainer}>
      <VentionSidebarItem
        onClick={() => {
          // Currently only one settings option available
        }}
        size="xx-large"
        state="active"
        title="Settings"
        type="profile"
      />
    </div>
  )
}

const useStyles = tss.create(({ theme }) => ({
  pageContainer: {
    margin: 0,
    width: "100%",
    height: "100%",
    gap: theme.spacing(4),
    overflow: "hidden",
  },
  layoutGrid: {
    display: "grid",
    gridTemplateColumns: "391px 1fr",
    height: "100%",
  },
  leftColumn: {
    display: "flex",
    width: "391px",
    height: "100%",
    padding: theme.spacing(4),
    alignItems: "flex-start",
    gap: theme.spacing(4),
    flexShrink: 0,
    borderRight: `1px solid ${theme.palette.border.main}`,
  },
  rightColumn: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    backgroundColor: theme.palette.background.subtleSlate,
  },
  sidebarItemContainer: {
    width: "100%",
    height: "128px",
    display: "flex",
    "& > *": {
      flex: 1,
    },
  },
  machineSaveSection: {
    width: "100%",
    height: "104px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingLeft: theme.spacing(7),
    paddingRight: theme.spacing(7),
    paddingTop: theme.spacing(4),
    paddingBottom: theme.spacing(4),
    backgroundColor: theme.palette.background.default,
    borderBottom: `1px solid ${theme.palette.border.main}`,
    flexShrink: 0,
  },
  machineInfo: {
    display: "flex",
    alignItems: "center",
  },
  machineTitle: {
    ...theme.typography.heading36Bold,
    margin: 0,
  },
  saveButtonContainer: {
    display: "flex",
    alignItems: "center",
  },
  saveButton: {
    minWidth: "240px",
  },
  configSection: {
    flex: 1,
    padding: theme.spacing(7),
    display: "flex",
    flexDirection: "column",
    gap: theme.spacing(4),
    minHeight: 0,
  },
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: theme.spacing(4),
    padding: theme.spacing(7),
    backgroundColor: theme.palette.background.default,
    borderRadius: theme.shape.borderRadius,
    border: `1px solid ${theme.palette.border.main}`,
  },
  panelTitle: {
    ...theme.typography.heading24SemiBold,
  },
  inputFieldGroup: {
    display: "flex",
    flexDirection: "column",
    gap: theme.spacing(1),
    justifyContent: "center",
  },
  inputLabel: {
    ...theme.typography.heading18SemiBold,
  },
  input: {
    backgroundColor: theme.palette.background.default,
    borderRadius: theme.shape.borderRadius,
  },
}))

export default SettingsPage
