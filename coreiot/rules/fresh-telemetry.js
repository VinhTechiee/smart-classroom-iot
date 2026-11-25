// Evaluate only recent telemetry that still matches the latest stored sample.
if (msgType !== "POST_TELEMETRY_REQUEST" || !msg || !metadata ||
    typeof metadata.ts !== "string" || !/^[0-9]+$/.test(metadata.ts)) {
    return false;
}

var timestamp = Number(metadata.ts);
var ageMs = Date.now() - timestamp;
if (ageMs < -5000 || ageMs > 30000) {
    return false;
}

try {
    var latest = JSON.parse(metadata.temperature);
    return !!latest && latest.ts === timestamp;
} catch (error) {
    return false;
}
