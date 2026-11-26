// Paste this body into the Rule Chain's JavaScript Switch node.
if (msgType !== "POST_TELEMETRY_REQUEST" || !msg ||
    typeof msg.temperature !== "number" || !isFinite(msg.temperature)) {
    return "Ignore";
}
if (msg.temperature >= 35) {
    return "High";
}
if (msg.temperature <= 33) {
    return "Recovered";
}
return "Ignore";
