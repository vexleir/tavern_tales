import { useCallback, useRef, useState } from 'react';
import { apiUrl, parseErrorResponse } from '../lib/api';

export default function useNdjsonStream({ onError, onAbortWithTokens } = {}) {
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef(null);

  const streamEndpoint = useCallback(async (url, body, { onStart, onToken, onDone } = {}) => {
    setIsStreaming(true);
    abortRef.current = new AbortController();
    let receivedToken = false;
    let aborted = false;

    try {
      const res = await fetch(apiUrl(url), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
        signal: abortRef.current.signal
      });

      if (!res.ok) {
        const msg = await parseErrorResponse(res);
        onError?.(`Backend error: ${msg}`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let tail = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        tail += decoder.decode(value, { stream: true });
        const lines = tail.split('\n');
        tail = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          let evt;
          try { evt = JSON.parse(line); } catch { continue; }
          if (evt.type === 'start') onStart?.(evt);
          else if (evt.type === 'token') {
            receivedToken = true;
            onToken?.(evt.data);
          } else if (evt.type === 'error') {
            onError?.(evt.data);
          } else if (evt.type === 'done') {
            onDone?.(evt);
          }
        }
      }
    } catch (e) {
      if (e.name === 'AbortError') aborted = true;
      else onError?.(`Stream failure: ${e.message}`);
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
      if (aborted && receivedToken) await onAbortWithTokens?.();
    }
  }, [onError, onAbortWithTokens]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { isStreaming, streamEndpoint, stop };
}
