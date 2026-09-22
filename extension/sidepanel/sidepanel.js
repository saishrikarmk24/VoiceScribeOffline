const $ = (id) => document.getElementById(id)
const state = { session: null, recording: false, timer: null, startedAt: 0 }

function showError(message = '') {
  const node = $('errorMessage')
  node.textContent = message
  node.classList.toggle('hidden', !message)
}

function updateUI() {
  const recordBtn = $('recordButton')
  const stopBtn = $('stopButton')
  const discardBtn = $('discardButton')
  const reviewBtn = $('reviewButton')
  const statusDot = $('statusDot')
  const statusText = $('statusText')

  if (state.recording) {
    if (recordBtn) recordBtn.classList.add('hidden')
    if (stopBtn) {
      stopBtn.classList.remove('hidden')
      stopBtn.disabled = false
      stopBtn.textContent = '⏹ Stop & Transcribe Note'
    }
    if (discardBtn) discardBtn.classList.remove('hidden')
    if (statusDot) statusDot.classList.add('recording')
    if (statusText) statusText.textContent = 'Recording Google Meet audio...'
  } else {
    if (recordBtn) {
      recordBtn.classList.remove('hidden')
      recordBtn.disabled = false
      recordBtn.textContent = 'Start Recording Meet'
    }
    if (stopBtn) stopBtn.classList.add('hidden')
    if (discardBtn) discardBtn.classList.add('hidden')
    if (statusDot) statusDot.classList.remove('recording')
    if (reviewBtn && state.session) reviewBtn.classList.remove('hidden')
  }
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

async function getEffectiveAppBase() {
  try {
    const tabs = await chrome.tabs.query({})
    for (const tab of tabs) {
      if (!tab.url) continue
      try {
        const url = new URL(tab.url)
        if (
          (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
          (url.port === '5173' || url.port === '3000' || url.port === '5174' || tab.title?.toLowerCase().includes('voicescribe') || tab.title?.toLowerCase().includes('medscribe'))
        ) {
          const detected = url.origin
          if ($('appBaseDisplay')) $('appBaseDisplay').textContent = detected
          chrome.storage.sync.set({ appBase: detected }).catch(() => {})
          return { appBase: detected, existingTabId: tab.id }
        }
      } catch {}
    }
  } catch {}

  const { appBase } = await chrome.storage.sync.get({ appBase: 'http://127.0.0.1:5173' })
  const fallback = appBase || 'http://127.0.0.1:5173'
  if ($('appBaseDisplay')) $('appBaseDisplay').textContent = fallback
  return { appBase: fallback, existingTabId: null }
}

async function getEffectiveApiBase() {
  const { apiBase } = await chrome.storage.sync.get({ apiBase: 'http://127.0.0.1:8000/api' })
  return apiBase || 'http://127.0.0.1:8000/api'
}

async function request(path, init = {}) {
  let apiBase = await getEffectiveApiBase()
  let response
  try {
    response = await fetch(`${apiBase.replace(/\/$/, '')}${path}`, init)
  } catch (netErr) {
    const altBase = apiBase.includes('127.0.0.1')
      ? apiBase.replace('127.0.0.1', 'localhost')
      : apiBase.includes('localhost')
        ? apiBase.replace('localhost', '127.0.0.1')
        : null

    if (altBase) {
      try {
        response = await fetch(`${altBase.replace(/\/$/, '')}${path}`, init)
        apiBase = altBase
        chrome.storage.sync.set({ apiBase })
      } catch {
        throw new Error(`Cannot connect to backend server at ${apiBase}. Make sure the Python backend is running on port 8000.`)
      }
    } else {
      throw new Error(`Cannot connect to backend server at ${apiBase}. Make sure the Python backend is running on port 8000.`)
    }
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `${response.status} ${response.statusText}`)
  }
  return response.json()
}

async function recorder(type, values = {}) {
  const result = await chrome.runtime.sendMessage({ target: 'recorder', type, ...values })
  if (!result?.ok) {
    throw new Error(result?.error || 'The Meet recorder is unavailable. Click the extension icon again from the Meet tab.')
  }
  return result
}

async function showCaptureState() {
  const { captureReady, captureError, captureLevel, captionsActive, captionDetected } =
    await chrome.storage.session.get({
      captureReady: false,
      captureError: '',
      captureLevel: 0,
      captionsActive: false,
      captionDetected: false,
    })

  if ($('levelBar')) {
    $('levelBar').style.width = `${Math.min(100, Number(captureLevel) * 180)}%`
  }

  // Caption status indicator
  const captionDot = $('captionDot')
  const captionText = $('captionText')
  if (captionDot && captionText) {
    if (captionDetected || captionsActive) {
      captionDot.classList.add('recording')
      captionText.textContent = 'Meet Captions: active (tagging speakers from CC)'
    } else {
      captionDot.classList.remove('recording')
      captionText.textContent = 'Meet Captions: turn ON captions (CC) in Meet for speaker tagging'
    }
  }

  if (!state.recording) {
    if (captureReady) {
      $('statusText').textContent = 'Meet tab connected — ready to record'
    } else {
      $('statusText').textContent = 'Meet tab is not connected'
      if (captureError) showError(captureError)
    }
  }
}

async function tryReconnectTab() {
  try {
    const res = await chrome.runtime.sendMessage({ type: 'reconnectTab' })
    if (res?.ok) {
      await showCaptureState()
      return true
    }
  } catch {}
  return false
}

async function createSession() {
  showError()
  const button = $('createButton')
  button.disabled = true
  button.textContent = 'Creating...'
  try {
    const session = await request('/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('sessionName').value.trim() || 'Telehealth Consultation',
        patient_id: $('patientId').value.trim() || 'PT-GMEET-01',
        scenario: $('scenario').value.trim() || null,
        simulation_type: $('encounterType').value,
        doctor_name: $('doctorName').value.trim() || null,
        mode: 'UPLOAD',
        audio_source: 'UPLOAD',
      }),
    })
    await request(`/sessions/${session.id}/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    state.session = session
    $('sessionReference').textContent = session.reference
    $('sessionDisplay').textContent = session.name
    $('setupCard').classList.add('hidden')
    $('captureCard').classList.remove('hidden')
    await showCaptureState()
    updateUI()
  } catch (error) {
    showError(error.message)
  } finally {
    button.disabled = false
    button.textContent = 'Start Consultation'
  }
}

async function startRecording() {
  showError()
  const { captureReady } = await chrome.storage.session.get({ captureReady: false })
  if (!captureReady) {
    const reconnected = await tryReconnectTab()
    if (!reconnected) {
      throw new Error('Meet tab is not connected. Make sure you are on a Google Meet tab and click the extension icon.')
    }
  }

  // Clear previous speaker events and caption status
  await chrome.storage.session.set({ speakerEvents: [], captionDetected: false })
  
  // Start recording the tab stream
  await recorder('start', { includeMicrophone: true })
  
  state.recording = true
  state.startedAt = Date.now()
  if (state.timer) clearInterval(state.timer)
  state.timer = setInterval(() => {
    if ($('duration')) $('duration').textContent = formatTime((Date.now() - state.startedAt) / 1000)
  }, 250)

  updateUI()
}

async function stopRecording() {
  if (!state.recording) return
  showError()
  state.recording = false
  if (state.timer) clearInterval(state.timer)

  const stopBtn = $('stopButton')
  if (stopBtn) {
    stopBtn.disabled = true
    stopBtn.textContent = 'Uploading & transcribing...'
  }
  $('statusText').textContent = 'Uploading audio and generating note with Gemini...'

  try {
    const apiBase = await getEffectiveApiBase()
    const result = await recorder('stopAndUpload', { sessionId: state.session.id, apiBase })
    if (!result.transcribed) throw new Error(result.message || 'No speech was recognised.')

    // Read speaker events from storage
    const { speakerEvents } = await chrome.storage.session.get({ speakerEvents: [] })

    // Upload speaker events to backend if any were captured
    if (speakerEvents && speakerEvents.length > 0) {
      await fetch(`${apiBase.replace(/\/$/, '')}/sessions/${state.session.id}/speaker-events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events: speakerEvents }),
      }).catch(() => {})
    }

    await request(`/sessions/${state.session.id}/stop`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    $('statusText').textContent = '✓ Note complete! Click "Open Review & Sign Note" below.'
  } catch (error) {
    $('statusText').textContent = 'Upload or transcription failed'
    showError(error.message)
  } finally {
    if ($('levelBar')) $('levelBar').style.width = '0%'
    updateUI()
  }
}

async function discard() {
  if (state.timer) clearInterval(state.timer)
  await recorder('discard')
  state.recording = false
  if ($('duration')) $('duration').textContent = '00:00'
  if ($('levelBar')) $('levelBar').style.width = '0%'
  $('statusText').textContent = 'Recording discarded — ready to capture'
  updateUI()
}

async function openReview() {
  if (!state.session) return
  const { appBase, existingTabId } = await getEffectiveAppBase()
  const targetUrl = `${appBase.replace(/\/$/, '')}/sessions/${state.session.id}/review`

  // If user already has MedScribe open in a tab, navigate that tab and bring to front
  if (existingTabId) {
    try {
      await chrome.tabs.update(existingTabId, { url: targetUrl, active: true })
      const tab = await chrome.tabs.get(existingTabId)
      if (tab?.windowId) {
        await chrome.windows.update(tab.windowId, { focused: true })
      }
      return
    } catch {}
  }

  // Otherwise, create a new tab
  chrome.tabs.create({ url: targetUrl })
}

// ── Event Bindings ───────────────────────────────────────────────────
$('createButton').addEventListener('click', () => void createSession())
$('recordButton').addEventListener('click', () => void startRecording().catch((err) => showError(err.message)))
$('stopButton').addEventListener('click', () => void stopRecording().catch((err) => showError(err.message)))
$('discardButton').addEventListener('click', () => void discard().catch((err) => showError(err.message)))
$('reviewButton').addEventListener('click', () => void openReview())
$('settingsButton').addEventListener('click', () => chrome.runtime.openOptionsPage())

// Initialize
void getEffectiveAppBase()
showCaptureState()
void tryReconnectTab()
updateUI()

chrome.storage.onChanged.addListener((changes, area) => {
  if (
    area === 'session' &&
    (changes.captureReady ||
      changes.captureError ||
      changes.captureLevel ||
      changes.captionsActive ||
      changes.captionDetected)
  ) {
    void showCaptureState()
  }
})
