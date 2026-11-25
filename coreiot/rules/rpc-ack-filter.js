// The MQTT RPC reply can arrive successfully with an application-level error.
return !!msg && !!metadata && typeof msg.id === "string" && msg.id.length > 0 &&
    msg.ok === true && typeof msg.actualState === "boolean" &&
    metadata.classroomExpectedRpcState === String(msg.actualState);
