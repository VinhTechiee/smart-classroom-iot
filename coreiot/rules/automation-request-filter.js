// Only complete, supported automation requests proceed to logging or RPC.
return !!msg && (msg.method === "setLamp" || msg.method === "setFan") &&
    typeof msg.params === "boolean";
