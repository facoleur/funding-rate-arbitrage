import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export type SSEStatus = 'connecting' | 'connected' | 'disconnected'

const TRADE_EVENTS = new Set(['trade_opened', 'trade_filled', 'trade_failed', 'trade_stuck'])

export function useSSE(): SSEStatus {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<SSEStatus>('connecting')
  const retryDelay = useRef(1000)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    let cancelled = false

    function connect() {
      if (cancelled) return
      setStatus('connecting')
      const es = new EventSource('/api/stream')
      esRef.current = es

      es.onopen = () => {
        retryDelay.current = 1000
        setStatus('connected')
      }

      es.addEventListener('opportunity_detected', () => {
        void queryClient.invalidateQueries({ queryKey: ['opportunities'] })
      })

      for (const evt of TRADE_EVENTS) {
        es.addEventListener(evt, () => {
          void queryClient.invalidateQueries({ queryKey: ['trades'] })
        })
      }

      es.addEventListener('kill_switch_tripped', () => {
        void queryClient.invalidateQueries({ queryKey: ['executor'] })
      })

      es.addEventListener('balance_low', () => {
        void queryClient.invalidateQueries({ queryKey: ['exchanges'] })
      })

      es.addEventListener('exchange_unhealthy', () => {
        void queryClient.invalidateQueries({ queryKey: ['exchanges'] })
      })

      es.addEventListener('position_expiring', () => {
        void queryClient.invalidateQueries({ queryKey: ['positions'] })
      })

      es.onerror = () => {
        es.close()
        esRef.current = null
        if (!cancelled) {
          setStatus('disconnected')
          const delay = retryDelay.current
          retryDelay.current = Math.min(delay * 2, 10000)
          setTimeout(connect, delay)
        }
      }
    }

    connect()
    return () => {
      cancelled = true
      esRef.current?.close()
      esRef.current = null
    }
  }, [queryClient])

  return status
}
