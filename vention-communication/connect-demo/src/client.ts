import { createClient } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";
import { VentionAppService } from "./gen/connect/proto/app_connect";

const transport = createConnectTransport({
  baseUrl: "http://localhost:8000/rpc",
  useBinaryFormat: false,
});

export const client = createClient(VentionAppService, transport);
