const body = { jsonrpc: "2.0", method: "call", params: { service: "object", method: "execute", args: [] } };
fetch("https://erp.example.com/jsonrpc", { method: "POST", body: JSON.stringify(body) });
