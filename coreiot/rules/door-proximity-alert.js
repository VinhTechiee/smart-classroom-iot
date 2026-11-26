// This rule interprets distance near an open door only in the opted-in sandbox.
if (msgType !== "POST_TELEMETRY_REQUEST" || !msg || !metadata ||
    metadata.ss_classroomDoorProximityAlertEnabled !== "true" ||
    typeof msg.door !== "boolean" || typeof msg.distance !== "number" ||
    !isFinite(msg.distance) || msg.distance < 0) {
    return "Ignore";
}
if (msg.door && msg.distance <= 15) {
    return "Near";
}
if (!msg.door || msg.distance >= 25) {
    return "Recovered";
}
return "Ignore";
