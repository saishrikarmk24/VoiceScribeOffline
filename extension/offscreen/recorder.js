let tabStream = null, micStream = null, context = null, processor = null, sources = [], sink = null, chunks = [], samples = 0, sampleRate = 16000, recording = false, lastLevelAt = 0, micActive = false

function release() {
  processor?.disconnect()
  sources.forEach((source) => source.disconnect())
  sink?.disconnect()
  tabStream?.getTracks().forEach((track) => track.stop())
  micStream?.getTracks().forEach((track) => track.stop())
  if (context?.state !== 'closed') context?.close()
  tabStream = null; micStream = null; context = null; processor = null
  sources = []; sink = null; recording = false; chunks = []; samples = 0
  micActive = false
}

function mixToMono(buffer) {
  const output = new Float32Array(buffer.length)
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const input = buffer.getChannelData(channel)
    for (let i = 0; i < input.length; i++) output[i] += input[i] / buffer.numberOfChannels
  }
  return output
}

function downsample(input, sourceRate, targetRate) {
  if (sourceRate === targetRate) return input
  const output = new Float32Array(Math.round(input.length * targetRate / sourceRate))
  const ratio = sourceRate / targetRate
  for (let i = 0; i < output.length; i++) {
    const start = Math.floor(i * ratio), end = Math.min(Math.floor((i + 1) * ratio), input.length)
    let total = 0
    for (let j = start; j < end; j++) total += input[j]
    output[i] = total / Math.max(1, end - start)
  }
  return output
}

function encodeWav(input, rate) {
  const buffer = new ArrayBuffer(44 + input.length * 2), view = new DataView(buffer)
  const write = (at, text) => [...text].forEach((char, i) => view.setUint8(at + i, char.charCodeAt(0)))
  write(0, 'RIFF'); view.setUint32(4, 36 + input.length * 2, true); write(8, 'WAVEfmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  write(36, 'data'); view.setUint32(40, input.length * 2, true)
  input.forEach((sample, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, sample)) * 0x7fff, true))
  return buffer
}

async function prepare(streamId) {
  release()
  tabStream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } },
    video: false,
  })
  context = new AudioContext({ sampleRate: 16000 })
  if (context.state === 'suspended') await context.resume()
  const tabSource = context.createMediaStreamSource(tabStream)
  tabSource.connect(context.destination)
  sources = [tabSource]
  sampleRate = context.sampleRate
  tabStream.getAudioTracks()[0].onended = release
  return { ok: true }
}

async function start(includeMicrophone) {
  if (!tabStream || !context) {
    throw new Error('Meet tab connection expired. Click the extension icon again from the Meet tab.')
  }

  chunks = []; samples = 0; micActive = false
  const mixer = context.createGain()
  mixer.gain.value = 1.0

  // Tab audio: connect with gain control
  const tabGain = context.createGain()
  tabGain.gain.value = 1.0
  sources[0].connect(tabGain)
  tabGain.connect(mixer)
  sources.push(tabGain)

  // Microphone: always attempt to capture the doctor's voice
  if (includeMicrophone !== false) {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
        },
      })
      const mic = context.createMediaStreamSource(micStream)
      const micGain = context.createGain()
      micGain.gain.value = 1.2  // Boost mic slightly since tab audio tends to be louder
      mic.connect(micGain)
      micGain.connect(mixer)
      sources.push(mic, micGain)
      micActive = true
      sendPortMessage({ event: 'micStatus', active: true, error: null })
    } catch (micError) {
      // Surface the error to the UI instead of silently swallowing it
      const reason = micError.name === 'NotAllowedError'
        ? 'Microphone permission denied. Your voice will NOT be recorded. Grant mic access in chrome://settings/content/microphone and allow this extension.'
        : micError.name === 'NotFoundError'
          ? 'No microphone found on this computer. Only Meet tab audio will be recorded.'
          : `Microphone error: ${micError.message}. Only Meet tab audio will be recorded.`
      sendPortMessage({ event: 'micStatus', active: false, error: reason })
    }
  }

  // Audio processing pipeline
  processor = context.createScriptProcessor(4096, 2, 1)
  sink = context.createGain()
  sink.gain.value = 0
  mixer.connect(processor)
  processor.connect(sink)
  sink.connect(context.destination)

  processor.onaudioprocess = (event) => {
    const data = mixToMono(event.inputBuffer)
    chunks.push(data)
    samples += data.length
    if (Date.now() - lastLevelAt > 120) {
      let peak = 0
      for (let i = 0; i < data.length; i += 12) peak = Math.max(peak, Math.abs(data[i]))
      sendPortMessage({ event: 'level', level: peak })
      lastLevelAt = Date.now()
    }
  }

  recording = true
  return { ok: true, micActive }
}

async function isReady() {
  const isHealthy = Boolean(
    tabStream &&
    tabStream.active &&
    tabStream.getAudioTracks().some((t) => t.readyState === 'live') &&
    context &&
    context.state !== 'closed'
  )
  return { ok: true, ready: isHealthy, recording }
}

async function stopAndUpload(sessionId, apiBase) {
  if (!recording) throw new Error('No active recording to stop.')
  recording = false
  if (processor) {
    processor.onaudioprocess = null
    try { processor.disconnect() } catch {}
  }
  if (sink) {
    try { sink.disconnect() } catch {}
  }
  sendPortMessage({ event: 'level', level: 0 })
  const merged = new Float32Array(samples)
  let offset = 0
  chunks.forEach((chunk) => { merged.set(chunk, offset); offset += chunk.length })
  chunks = []; samples = 0
  if (merged.length < sampleRate * .4) {
    return { ok: true, transcribed: false, message: 'No usable audio was captured. Make sure the Meet tab is playing audio.' }
  }
  const audio = downsample(merged, sampleRate, 16000)
  const form = new FormData()
  form.append('file', new File([encodeWav(audio, 16000)], `gmeet-${Date.now()}.wav`, { type: 'audio/wav' }))

  const uploadEndpoint = `${apiBase.replace(/\/$/, '')}/sessions/${sessionId}/audio/upload`
  let response
  try {
    response = await fetch(uploadEndpoint, { method: 'POST', body: form })
  } catch (fetchErr) {
    const altBase = apiBase.includes('127.0.0.1')
      ? apiBase.replace('127.0.0.1', 'localhost')
      : apiBase.includes('localhost')
        ? apiBase.replace('localhost', '127.0.0.1')
        : null
    if (altBase) {
      response = await fetch(`${altBase.replace(/\/$/, '')}/sessions/${sessionId}/audio/upload`, { method: 'POST', body: form })
    } else {
      throw new Error(`Failed to upload audio to backend at ${uploadEndpoint}: ${fetchErr.message}`)
    }
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`)
  return { ok: true, transcribed: body.ok, message: body.message }
}

// ── Persistent Port with Automatic Reconnection ──────────────────────
let port = null
let reconnectTimer = null

function sendPortMessage(payload) {
  if (port) {
    try {
      port.postMessage(payload)
      return
    } catch {
      port = null
    }
  }
}

function handleMessage(message) {
  const handlers = {
    prepare: () => prepare(message.streamId),
    release: async () => { release(); return { ok: true } },
    isReady: () => isReady(),
    start: () => start(message.includeMicrophone),
    stopAndUpload: () => stopAndUpload(message.sessionId, message.apiBase),
    discard: async () => { chunks = []; samples = 0; return { ok: true } },
    ping: async () => ({ ok: true }),
  }
  const handler = handlers[message.type]
  if (!handler) return
  handler()
    .then((result) => sendPortMessage({ requestId: message.requestId, result }))
    .catch((error) => sendPortMessage({ requestId: message.requestId, result: { ok: false, error: error.message || String(error) } }))
}

function connectPort() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  try {
    port = chrome.runtime.connect({ name: 'medscribe-recorder' })
    port.onMessage.addListener(handleMessage)
    port.onDisconnect.addListener(() => {
      port = null
      // When Chrome background service worker goes to sleep or restarts,
      // reconnect automatically so the offscreen document remains available.
      reconnectTimer = setTimeout(connectPort, 500)
    })
  } catch {
    port = null
    reconnectTimer = setTimeout(connectPort, 1000)
  }
}

connectPort()
