// client.ts
import { createClient } from "@connectrpc/connect"
import { createConnectTransport } from "@connectrpc/connect-web"
import { create } from "@bufbuild/protobuf"
import { VentionAppService } from "./gen/app_pb"

// -------------------------------------------
// Create base transport + client
// -------------------------------------------
const PROCESS_NAME = "quiz"

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

  const basePath = `/digital-twin/machine-motion/passthrough/${sessionId}/80/v1/machineCode/services/${PROCESS_NAME}/rpc`

  // Use external digital twin URL in dev, current origin in production
  const isDev = port === "5173" || hostname === "localhost"
  const baseOrigin = isDev ? "https://digital-twin.vention.foo" : origin

  return `${baseOrigin}${basePath}`
}

// Determine if running on edge device or in development
const isOnEdge = window.location.hostname.startsWith("192.168") || window.location.hostname.startsWith("localhost")
const httpBaseUrl = isOnEdge ? `http://${window.location.hostname}:8000/rpc` : getExecutionEngineHttpUrl()

const transport = createConnectTransport({
  baseUrl: httpBaseUrl,
})

const baseClient = createClient(VentionAppService, transport)

// -------------------------------------------
// Type-safe wrapper that accepts plain objects
// -------------------------------------------

export const client = new Proxy(baseClient, {
  get(target, prop) {
    const fn = (target as any)[prop]
    if (typeof fn !== "function") return fn

    // We know our client is created from a GenService descriptor,
    // which has a .methods map — but it's not typed in createClient().
    const methodDef = (VentionAppService as any).methods?.[prop]

    return (input?: any) => {
      // If no input provided, create empty message
      if (!input) {
        const schema = methodDef?.input
        return schema ? fn(create(schema, {})) : fn({})
      }

      // Already a protobuf message? Pass through
      if (input.$typeName) return fn(input)

      // If schema known, construct message
      const schema = methodDef?.input
      if (schema) return fn(create(schema, input))

      // Fallback: call raw
      return fn(input)
    }
  },
})