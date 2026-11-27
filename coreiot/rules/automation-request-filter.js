// Only complete, supported automation requests proceed to logging or RPC.
return !!msg && msg.method === "setLamp" &&
    typeof msg.params === "boolean";
