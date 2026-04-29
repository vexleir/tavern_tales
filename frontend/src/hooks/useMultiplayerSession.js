import { useCallback, useEffect, useReducer, useRef } from 'react';
import { wsUrl } from '../lib/api';

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000];

const initialState = {
  status: 'connecting', // connecting | open | closed | error
  reconnectAttempt: 0,
  errorMessage: null,
  mySlot: null,
  myDisplayName: null,
  myCharacterName: null,
  sessionState: null,        // server-side public state
  multiplayer: null,         // MultiplayerConfig from campaign
  mergedPreferences: null,
  mergedPreferenceSummary: null,
  liveAssistantText: '',     // streaming buffer for current AI turn
  generating: false,
  oocMessages: [],           // {slot, display_name, text, ts}
  partnerComposing: false,
  partnerSubmittedThisRound: false,
  lastError: null,           // banner-style transient error
  archivedReason: null,
  ejectedSlot: null,
};

function reducer(state, action) {
  switch (action.type) {
    case 'connecting':
      return { ...state, status: 'connecting', errorMessage: null };
    case 'open':
      return { ...state, status: 'open', reconnectAttempt: 0, errorMessage: null };
    case 'closed':
      return { ...state, status: 'closed' };
    case 'error':
      return { ...state, status: 'error', errorMessage: action.message };
    case 'reconnect_scheduled':
      return { ...state, reconnectAttempt: action.attempt };
    case 'self_assigned':
      return {
        ...state,
        mySlot: action.slot,
        myDisplayName: action.displayName,
        myCharacterName: action.characterName,
      };
    case 'session_state':
      return {
        ...state,
        sessionState: action.payload.session_state || null,
        multiplayer: action.payload.multiplayer || null,
        mergedPreferences: action.payload.merged_preferences || null,
        mergedPreferenceSummary: action.payload.merged_preference_summary || null,
      };
    case 'token':
      return { ...state, liveAssistantText: state.liveAssistantText + action.text };
    case 'generation_start':
      return {
        ...state,
        liveAssistantText: '',
        generating: true,
        partnerSubmittedThisRound: false,
        partnerComposing: false,
      };
    case 'generation_done':
      return {
        ...state,
        generating: false,
        liveAssistantText: '',
        partnerSubmittedThisRound: false,
        partnerComposing: false,
      };
    case 'partner_composing':
      return { ...state, partnerComposing: true };
    case 'partner_submitted':
      return { ...state, partnerSubmittedThisRound: true, partnerComposing: false };
    case 'ooc':
      return { ...state, oocMessages: [...state.oocMessages.slice(-49), action.message] };
    case 'transient_error':
      return { ...state, lastError: action.message };
    case 'clear_error':
      return { ...state, lastError: null };
    case 'archived':
      return { ...state, archivedReason: action.reason, status: 'closed' };
    case 'ejected':
      return { ...state, ejectedSlot: action.slot };
    default:
      return state;
  }
}

/**
 * Multiplayer WebSocket hook.
 *
 * Opts:
 *   roomCode (required) — 6-char room code
 *   joinPayload — { displayName, characterName, preferenceProfile?, preferenceSource? }
 *   reconnectSlot — if set, sends reconnect instead of join (after a paused window)
 *   enabled — set false to skip connecting (lets the consumer gate on user input)
 */
export default function useMultiplayerSession({
  roomCode,
  joinPayload,
  reconnectSlot = null,
  enabled = true,
}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const intentionalCloseRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  // connectRef holds a stable pointer to the connect function so the close
  // handler can schedule a reconnect without creating a forward-reference.
  const connectRef = useRef(() => {});

  // Stash the latest joinPayload/reconnectSlot in refs so the connect effect
  // can grab the freshest values without re-running on every keystroke.
  const joinPayloadRef = useRef(joinPayload);
  const reconnectSlotRef = useRef(reconnectSlot);
  useEffect(() => { joinPayloadRef.current = joinPayload; }, [joinPayload]);
  useEffect(() => { reconnectSlotRef.current = reconnectSlot; }, [reconnectSlot]);

  const sendJSON = useCallback((obj) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(obj));
    return true;
  }, []);

  const handleMessage = useCallback((event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    const t = data.type;
    if (t === 'session_state') {
      dispatch({ type: 'session_state', payload: data });
    } else if (t === 'token') {
      dispatch({ type: 'token', text: data.text });
    } else if (t === 'generation_start') {
      dispatch({ type: 'generation_start' });
    } else if (t === 'generation_done') {
      dispatch({ type: 'generation_done' });
    } else if (t === 'partner_composing') {
      dispatch({ type: 'partner_composing' });
    } else if (t === 'partner_submitted') {
      dispatch({ type: 'partner_submitted' });
    } else if (t === 'ooc_message') {
      dispatch({
        type: 'ooc',
        message: {
          slot: data.slot,
          display_name: data.display_name,
          text: data.text,
          ts: Date.now(),
        },
      });
    } else if (t === 'session_archived') {
      intentionalCloseRef.current = true;
      dispatch({ type: 'archived', reason: data.reason || 'archived' });
    } else if (t === 'player_ejected') {
      dispatch({ type: 'ejected', slot: data.slot });
    } else if (t === 'error') {
      dispatch({ type: 'transient_error', message: data.message || 'unknown error' });
    } else if (t === 'session_paused' || t === 'session_resumed' || t === 'player_joined' || t === 'player_ready' || t === 'floor_passed') {
      // These are informational only — sessionState updates follow immediately
      // for any state changes. Nothing to do here.
    }
  }, []);

  const connect = useCallback(() => {
    if (!enabled || !roomCode) return;
    if (typeof window === 'undefined') return;
    intentionalCloseRef.current = false;
    dispatch({ type: 'connecting' });

    const ws = new WebSocket(wsUrl(`/api/session/${encodeURIComponent(roomCode)}/ws`));
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptRef.current = 0;
      dispatch({ type: 'open' });
      const reconnect = reconnectSlotRef.current;
      const payload = joinPayloadRef.current || {};
      if (reconnect) {
        ws.send(JSON.stringify({ type: 'reconnect', slot: reconnect }));
        dispatch({ type: 'self_assigned', slot: reconnect, displayName: payload.displayName, characterName: payload.characterName });
      } else {
        ws.send(JSON.stringify({
          type: 'join',
          display_name: payload.displayName || '',
          character_name: payload.characterName || '',
          preference_profile: payload.preferenceProfile || null,
          preference_source: payload.preferenceSource || 'none',
          slot: payload.desiredSlot || null,
        }));
        dispatch({
          type: 'self_assigned',
          slot: payload.desiredSlot || null,
          displayName: payload.displayName || '',
          characterName: payload.characterName || '',
        });
      }
    };

    ws.onmessage = handleMessage;

    ws.onclose = () => {
      dispatch({ type: 'closed' });
      wsRef.current = null;
      if (intentionalCloseRef.current) return;
      const attempt = reconnectAttemptRef.current + 1;
      reconnectAttemptRef.current = attempt;
      const delay = RECONNECT_DELAYS_MS[Math.min(attempt - 1, RECONNECT_DELAYS_MS.length - 1)];
      dispatch({ type: 'reconnect_scheduled', attempt });
      reconnectTimerRef.current = window.setTimeout(() => connectRef.current(), delay);
    };

    ws.onerror = () => {
      dispatch({ type: 'error', message: 'WebSocket error — retrying.' });
    };
  }, [enabled, roomCode, handleMessage]);

  // Keep the ref pointing at the latest connect() so the close handler can
  // invoke it without a forward reference.
  useEffect(() => { connectRef.current = connect; }, [connect]);

  // Effect: open the socket when (enabled && roomCode) becomes true. We
  // intentionally do NOT depend on `connect` directly to avoid reopening
  // every time `state.reconnectAttempt` changes.
  useEffect(() => {
    if (!enabled || !roomCode) return undefined;
    connect();
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws && ws.readyState <= WebSocket.OPEN) {
        try { ws.close(1000); } catch { /* ignore */ }
      }
    };
    // We deliberately omit `connect` so this effect only fires when
    // enabled/roomCode change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, roomCode]);

  // Public action helpers ------------------------------------------------

  const submitAction = useCallback((text) => sendJSON({ type: 'submit_action', text }), [sendJSON]);
  const readyUp = useCallback(() => sendJSON({ type: 'ready' }), [sendJSON]);
  const unready = useCallback(() => sendJSON({ type: 'unready' }), [sendJSON]);
  const sendOOC = useCallback((text) => sendJSON({ type: 'ooc_message', text }), [sendJSON]);
  const composing = useCallback(() => sendJSON({ type: 'composing' }), [sendJSON]);
  const updateCharacter = useCallback((fields) => sendJSON({ type: 'update_character', ...fields }), [sendJSON]);
  const ejectGuest = useCallback(() => sendJSON({ type: 'eject_guest' }), [sendJSON]);
  const archiveSession = useCallback(() => sendJSON({ type: 'archive_session' }), [sendJSON]);
  const deleteSession = useCallback(() => sendJSON({ type: 'delete_session' }), [sendJSON]);
  const clearError = useCallback(() => dispatch({ type: 'clear_error' }), []);

  return {
    state,
    submitAction,
    readyUp,
    unready,
    sendOOC,
    composing,
    updateCharacter,
    ejectGuest,
    archiveSession,
    deleteSession,
    clearError,
  };
}
