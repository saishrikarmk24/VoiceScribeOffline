/**
 * Session WebSocket client with automatic reconnection and state resync.
 *
 * On reconnect it sends the last sequence number it saw; the server replays the
 * missed events or returns a full snapshot, so the workstation never shows stale
 * data after a dropped connection.
 */

import { WS_BASE } from '@/constants'
import type { SocketEvent } from '@/types'

export type ConnectionState = 'connecting' | 'open' | 'closed' | 'reconnecting'

interface SocketHandlers {
  onEvent: (event: SocketEvent) => void
  onStateChange: (state: ConnectionState) => void
}

const RECONNECT_DELAYS = [500, 1000, 2000, 4000, 8000]
const HEARTBEAT_MS = 20000

export class SessionSocket {
  private socket: WebSocket | null = null
  private attempt = 0
  private lastSequence = 0
  private closedByUser = false
  private heartbeat: number | null = null
  private reconnectTimer: number | null = null

  constructor(
    private readonly sessionId: string,
    private readonly handlers: SocketHandlers,
  ) {}

  private url(): string {
    if (WS_BASE) return `${WS_BASE}/ws/sessions/${this.sessionId}`
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/sessions/${this.sessionId}`
  }

  connect(): void {
    this.closedByUser = false
    this.handlers.onStateChange(this.attempt === 0 ? 'connecting' : 'reconnecting')

    const socket = new WebSocket(this.url())
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      this.handlers.onStateChange('open')
      if (this.lastSequence > 0) {
        socket.send(JSON.stringify({ type: 'SYNC', last_sequence: this.lastSequence }))
      }
      this.startHeartbeat()
    }

    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data as string) as SocketEvent
        if (typeof event.sequence === 'number' && event.sequence > this.lastSequence) {
          this.lastSequence = event.sequence
        }
        this.handlers.onEvent(event)
      } catch {
        /* ignore malformed frames rather than dropping the socket */
      }
    }

    socket.onclose = () => {
      this.stopHeartbeat()
      if (this.closedByUser) {
        this.handlers.onStateChange('closed')
        return
      }
      this.scheduleReconnect()
    }

    socket.onerror = () => {
      /* onclose always follows, reconnection is handled there */
    }
  }

  private scheduleReconnect(): void {
    const delay = RECONNECT_DELAYS[Math.min(this.attempt, RECONNECT_DELAYS.length - 1)]
    this.attempt += 1
    this.handlers.onStateChange('reconnecting')
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay)
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeat = window.setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: 'PING' }))
      }
    }, HEARTBEAT_MS)
  }

  private stopHeartbeat(): void {
    if (this.heartbeat !== null) {
      window.clearInterval(this.heartbeat)
      this.heartbeat = null
    }
  }

  requestSnapshot(): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'SYNC', last_sequence: 0 }))
    }
  }

  close(): void {
    this.closedByUser = true
    this.stopHeartbeat()
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.socket?.close()
    this.socket = null
  }
}
