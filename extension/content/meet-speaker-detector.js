(function () {
  let captionsContainer = null;
  let captionObserver = null;
  let lastSpeaker = '';
  let lastText = '';
  let debounceTimer = null;
  let captionBadge = null;

  function createBadge() {
    if (captionBadge) return;
    captionBadge = document.createElement('div');
    captionBadge.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      padding: 8px 12px;
      background: rgba(0, 0, 0, 0.7);
      color: white;
      font-family: sans-serif;
      font-size: 12px;
      border-radius: 4px;
      z-index: 999999;
      pointer-events: none;
    `;
    captionBadge.textContent = 'MedScribe: Enable captions (CC) for speaker detection';
    document.body.appendChild(captionBadge);
  }

  function updateBadge(found) {
    if (!captionBadge) createBadge();
    if (found) {
      captionBadge.textContent = 'MedScribe: Detecting speakers...';
    } else {
      captionBadge.textContent = 'MedScribe: Enable captions (CC) for speaker detection';
    }
  }

  function findCaptionsContainer() {
    const selectors = [
      '[role="region"][aria-label="Captions"]',
      '[aria-live="polite"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) return el;
    }
    return null;
  }

  function sendEvent(speaker, text) {
    if (!speaker || !text) return;
    chrome.runtime.sendMessage({
      type: 'captionSpeakerEvent',
      speaker: speaker,
      text: text,
      timestamp: Date.now()
    }).catch(() => {});
  }

  function extractSpeakerAndText(node) {
    if (!node || node.nodeType !== Node.ELEMENT_NODE) return null;
    const children = node.querySelectorAll('div, span');
    
    if (children.length < 2) {
      const text = node.textContent?.trim() || '';
      return text ? { speaker: lastSpeaker, text } : null;
    }
    
    let speaker = '';
    let text = '';
    
    for (const child of children) {
      const content = child.textContent?.trim() || '';
      if (!content) continue;
      
      if (!speaker) {
        const style = getComputedStyle(child);
        const weight = parseInt(style.fontWeight, 10);
        const isBold = (weight >= 500 && !isNaN(weight)) || style.fontWeight === 'bold' || child.tagName === 'STRONG';
        if (isBold) {
          speaker = content;
          continue;
        }
      }
      text += (text ? ' ' : '') + content;
    }
    
    if (!speaker && node.textContent?.includes(':')) {
      const raw = node.textContent;
      const colonIndex = raw.indexOf(':');
      speaker = raw.slice(0, colonIndex).trim();
      text = raw.slice(colonIndex + 1).trim();
    }
    return speaker ? { speaker, text } : null;
  }

  function processCaptionChanges(mutations) {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        const parsed = extractSpeakerAndText(node);
        if (!parsed?.text) continue;
        
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          if (parsed.speaker !== lastSpeaker || parsed.text !== lastText) {
            sendEvent(parsed.speaker || lastSpeaker || 'Unknown', parsed.text);
            lastSpeaker = parsed.speaker || lastSpeaker || 'Unknown';
            lastText = parsed.text;
          }
        }, 800);
      }
      if (mutation.type === 'characterData') {
        const parent = mutation.target.parentElement;
        const parsed = extractSpeakerAndText(parent);
        if (parsed?.text && parsed.text !== lastText) {
          clearTimeout(debounceTimer);
          debounceTimer = setTimeout(() => {
            sendEvent(parsed.speaker || lastSpeaker || 'Unknown', parsed.text);
            lastSpeaker = parsed.speaker || lastSpeaker || 'Unknown';
            lastText = parsed.text;
          }, 800);
        }
      }
    }
  }

  function startObserving() {
    captionsContainer = findCaptionsContainer();
    if (captionsContainer) {
      updateBadge(true);
      
      chrome.runtime.sendMessage({
        type: 'captionsDetected',
        active: true
      }).catch(() => {});
      
      captionObserver = new MutationObserver(processCaptionChanges);
      
      captionObserver.observe(captionsContainer, {
        childList: true,
        characterData: true,
        subtree: true
      });
    } else {
      updateBadge(false);
      chrome.runtime.sendMessage({
        type: 'captionsDetected',
        active: false
      }).catch(() => {});
    }
  }

  function init() {
    createBadge();
    
    // Check periodically for captions container
    setInterval(() => {
      const currentContainer = findCaptionsContainer();
      if (currentContainer && !captionsContainer) {
        startObserving();
      } else if (!currentContainer && captionsContainer) {
        if (captionObserver) captionObserver.disconnect();
        captionsContainer = null;
        updateBadge(false);
        chrome.runtime.sendMessage({
          type: 'captionsDetected',
          active: false
        }).catch(() => {});
        console.log('MedScribe: Captions container disappeared');
      }
    }, 2000);
    
    startObserving();
  }
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
