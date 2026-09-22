let recorderPort = null
let recorderReadyResolvers = []
const pending = new Map()

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'medscribe-recorder') return
  recorderPort = port
  const resolvers = [...recorderReadyResolvers]
  recorderReadyResolvers = []
  resolvers.forEach((resolve) => resolve())

  port.onMessage.addListener(({ requestId, result, event, level, active, error }) => {
    if (event === 'level') {
      chrome.storage.session.set({ captureLevel: Number(level) || 0 }).catch(() => {})
      return
    }
    if (event === 'micStatus') {
      chrome.storage.session.set({ micActive: !!active, micError: error || '' }).catch(() => {})
      return
    }
    const resolve = pending.get(requestId)
    if (resolve) {
      pending.delete(requestId)
      resolve(result)
    }
  })

  port.onDisconnect.addListener(() => {
    if (recorderPort === port) {
      recorderPort = null
    }
  })
})

function waitForRecorderPort(timeoutMs = 5000) {
  if (recorderPort) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      const idx = recorderReadyResolvers.indexOf(onReady)
      if (idx !== -1) recorderReadyResolvers.splice(idx, 1)
      reject(new Error('The background recorder did not load. Please click the extension icon again to reconnect.'))
    }, timeoutMs)

    const onReady = () => {
      clearTimeout(timeout)
      resolve()
    }
    recorderReadyResolvers.push(onReady)
  })
}

async function hasOffscreenDoc() {
  if ('hasDocument' in chrome.offscreen) {
    return await chrome.offscreen.hasDocument()
  }
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
    documentUrls: [chrome.runtime.getURL('offscreen/recorder.html')],
  })
  return contexts.length > 0
}

async function ensureRecorderDocument() {
  if (recorderPort) return

  const hasDoc = await hasOffscreenDoc().catch(() => false)
  if (hasDoc) {
    // If the offscreen doc exists, give the auto-reconnecting port a moment to reconnect
    try {
      await waitForRecorderPort(800)
      if (recorderPort) return
    } catch {
      // Offscreen doc is unresponsive or stale -> close it and recreate
      try {
        await chrome.offscreen.closeDocument()
      } catch {}
    }
  }

  try {
    await chrome.offscreen.createDocument({
      url: 'offscreen/recorder.html',
      reasons: ['USER_MEDIA'],
      justification: 'Hold an authorized Google Meet tab audio stream while the clinician starts and stops a recording.',
    })
  } catch (error) {
    if (!String(error.message || error).includes('Only a single offscreen')) throw error
  }

  await waitForRecorderPort(5000)
}

async function sendToRecorder(type, payload = {}) {
  await ensureRecorderDocument()
  if (!recorderPort) throw new Error('The background recorder is unavailable.')
  const requestId = crypto.randomUUID()
  return new Promise((resolve) => {
    pending.set(requestId, resolve)
    recorderPort.postMessage({ requestId, type, ...payload })
  })
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.get(['apiBase', 'appBase'], (settings) => {
    const updates = {}
    if (!settings.apiBase) updates.apiBase = 'http://127.0.0.1:8000/api'
    if (!settings.appBase) updates.appBase = 'http://127.0.0.1:5173'
    if (Object.keys(updates).length) chrome.storage.sync.set(updates)
  })
  ensureRecorderDocument().catch(() => {})
})

chrome.runtime.onStartup.addListener(() => ensureRecorderDocument().catch(() => {}))

let currentCapturedTabId = null

async function prepareCapture(tab) {
  try {
    if (!tab?.id || !/^https:\/\/meet\.google\.com\//.test(tab.url || '')) {
      throw new Error('Open a Google Meet tab first. Chrome cannot capture extension, settings, or other Chrome pages.')
    }

    await ensureRecorderDocument()

    // If we are already capturing this exact tab and the stream is healthy, keep it!
    if (currentCapturedTabId === tab.id) {
      try {
        const check = await sendToRecorder('isReady')
        if (check?.ready) {
          await chrome.storage.session.set({ captureReady: true, captureError: '' })
          return
        }
      } catch {}
    }

    // Release any previous stream in the recorder so tracks are stopped before minting new stream ID
    try {
      await sendToRecorder('release')
    } catch {}

    await new Promise((r) => setTimeout(r, 100))

    let streamId
    try {
      streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id })
    } catch (err) {
      if (String(err.message || err).includes('active stream')) {
        try {
          await chrome.offscreen.closeDocument()
        } catch {}
        await ensureRecorderDocument()
        await new Promise((r) => setTimeout(r, 150))
        streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id })
      } else {
        throw err
      }
    }

    const prepared = await sendToRecorder('prepare', { streamId })
    if (!prepared?.ok) throw new Error(prepared?.error || 'The recorder could not connect to the Meet tab.')

    currentCapturedTabId = tab.id
    await chrome.storage.session.set({ captureReady: true, captureError: '' })
  } catch (error) {
    currentCapturedTabId = null
    await chrome.storage.session.set({ captureReady: false, captureError: error.message || String(error) })
  }
}

chrome.action.onClicked.addListener((tab) => {
  // Open synchronously in the toolbar-click gesture; waiting for recorder setup
  // first causes Chrome to discard the gesture and silently refuse the panel.
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {})
  void prepareCapture(tab)
})

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  // ── Reconnect tab request from sidepanel ──────────────────────────
  if (message?.type === 'reconnectTab') {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (tab) {
        prepareCapture(tab).then(() => sendResponse({ ok: true })).catch((err) => sendResponse({ ok: false, error: err.message }))
      } else {
        sendResponse({ ok: false, error: 'No active tab found' })
      }
    })
    return true
  }

  // ── Speaker detection events from the Meet content script ──────
  if (message?.type === 'captionSpeakerEvent' || message?.type === 'speakerEvent') {
    chrome.storage.session.get({ speakerEvents: [] }, ({ speakerEvents }) => {
      speakerEvents.push({
        speaker: message.speaker,
        text: message.text,
        timestamp: message.timestamp,
      })
      chrome.storage.session.set({ speakerEvents })
    })
    return false // no async response needed
  }

  if (message?.type === 'captionsDetected') {
    chrome.storage.session.set({ captionDetected: !!message.active, captionsActive: !!message.active })
    return false
  }

  // ── Forward recorder-targeted messages to the offscreen document ─
  if (message?.target !== 'recorder') return
  sendToRecorder(message.type, message).then(sendResponse).catch((error) => sendResponse({ ok: false, error: error.message || String(error) }))
  return true
})
