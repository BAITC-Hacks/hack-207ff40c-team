// Build the Radxa appliance UI without upstream transcription/cloud entrypoints.
// Normal Scriberr builds preserve all upstream routes and navigation.
export const meetingStationMode = import.meta.env.VITE_MEETING_STATION === 'true'

// The standalone Python host uses the station pairing token instead of a Go
// account. This explicit build mode is valid only on the machine serving it.
export const localStationMode = meetingStationMode
  && import.meta.env.VITE_MEETING_LOCAL === 'true'
  && ['127.0.0.1', 'localhost', '[::1]'].includes(window.location.hostname)
