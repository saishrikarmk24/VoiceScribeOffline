const apiBase = document.getElementById('apiBase')
const appBase = document.getElementById('appBase')
const saved = document.getElementById('saved')
const detectMsg = document.getElementById('detectMsg')
const testMic = document.getElementById('testMic')
const micResult = document.getElementById('micResult')

// Load stored settings
chrome.storage.sync.get(
  { apiBase: 'http://127.0.0.1:8000/api', appBase: 'http://127.0.0.1:5173' },
  (settings) => {
    apiBase.value = settings.apiBase
    appBase.value = settings.appBase
  },
)

// Save button
document.getElementById('save').addEventListener('click', () => {
  const cleanApi = apiBase.value.trim().replace(/\/$/, '')
  const cleanApp = appBase.value.trim().replace(/\/$/, '')
  chrome.storage.sync.set({ apiBase: cleanApi, appBase: cleanApp }, () => {
    saved.hidden = false
    setTimeout(() => {
      saved.hidden = true
    }, 2500)
  })
})

// Auto-detect open MedScribe tab
document.getElementById('autoDetect').addEventListener('click', async () => {
  detectMsg.hidden = true
  try {
    const tabs = await chrome.tabs.query({})
    let found = null
    for (const tab of tabs) {
      if (!tab.url) continue
      try {
        const url = new URL(tab.url)
        if (
          (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
          (url.port === '5173' || url.port === '3000' || url.port === '5174' || tab.title?.toLowerCase().includes('voicescribe') || tab.title?.toLowerCase().includes('medscribe'))
        ) {
          found = url.origin
          break
        }
      } catch {}
    }

    if (found) {
      appBase.value = found
      // Also assume standard local API port if not custom
      if (!apiBase.value || apiBase.value.includes('127.0.0.1:8000') || apiBase.value.includes('localhost:8000')) {
        apiBase.value = 'http://127.0.0.1:8000/api'
      }
      chrome.storage.sync.set({ appBase: found, apiBase: apiBase.value })
      detectMsg.className = 'alert success'
      detectMsg.textContent = `Found active VoiceScribe AI tab at ${found}! Settings updated.`
      detectMsg.hidden = false
    } else {
      detectMsg.className = 'alert info'
      detectMsg.textContent = 'No running VoiceScribe AI tab detected. Ensure VoiceScribe AI is open in a browser tab.'
      detectMsg.hidden = false
    }
  } catch (err) {
    detectMsg.className = 'alert error'
    detectMsg.textContent = `Detection failed: ${err.message}`
    detectMsg.hidden = false
  }
})

// Test / Grant Microphone Permission
testMic.addEventListener('click', async () => {
  micResult.hidden = true
  testMic.disabled = true
  testMic.textContent = 'Requesting permission from Chrome...'

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    // Permission granted! Stop the tracks
    stream.getTracks().forEach((track) => track.stop())

    await chrome.storage.session.set({ micActive: true, micError: '' })
    micResult.className = 'alert success'
    micResult.textContent = '✓ Microphone permission is GRANTED! The extension can now record your computer voice in Google Meet.'
    micResult.hidden = false
    testMic.textContent = '✓ Microphone Access Granted'
  } catch (err) {
    await chrome.storage.session.set({ micActive: false, micError: err.message })
    micResult.className = 'alert error'
    micResult.textContent = `❌ Microphone permission denied: ${err.message}. Please click "Allow" in the Chrome address bar prompt.`
    micResult.hidden = false
    testMic.textContent = '🎙️ Retry Microphone Permission'
  } finally {
    testMic.disabled = false
  }
})
