import { useCallback, useEffect, useReducer, useRef } from 'react';
import { wsUrl } from '../lib/api';

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000];

function storageKey(roomCode, suffix) {
  return `tt_mp_${roomCode}_${suffix}`;
}

function getOrCreateClientId(roomCode) {
  if (typeof window === 'undefined') return '';
  const key = storageKey(roomCode, 'client_id');
  try {
    const existing = window.sessionStorage?.getItem(key) || window.localStorage?.getItem(key);
    if (existing) return existing;
    const generated = `client_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    window.sessionStorage?.setItem(key, generated);
    return generated;
  } catch {
    return `client_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }
}

function loadAssignedSlot(roomCode) {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage?.getItem(storageKey(roomCode, 'slot')) || null;
  } catch {
    return null;
  }
}

function saveAssignedSlot(roomCode, slot) {
  if (!slot || typeof window === 'undefined') return;
  try {
    window.sessionStorage?.setItem(storageKey(roomCode, 'slot'), slot);
  } catch {
    // Storage may be unavailable in privacy mode; the in-memory ref still works.
  }
}

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
  currentGeneration: null,   // {slot, actorName} for the active AI response
  lastCompletedGeneration: null,
  generating: false,
  oocMessages: [],           // {slot, display_name, text, ts}
  partnerComposing: false,
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
        currentGeneration: {
          slot: action.actingSlot || null,
          actorName: action.actorName || '',
        },
        lastCompletedGeneration: null,
        generating: true,
        partnerComposing: false,
      };
    case 'generation_done':
      return {
        ...state,
        generating: false,
        liveAssistantText: '',
        lastCompletedGeneration: {
          slot: action.actingSlot || state.currentGeneration?.slot || null,
          actorName: action.actorName || state.currentGeneration?.actorName || '',
        },
        currentGeneration: null,
        partnerComposing: false,
      };
    case 'partner_composing':
      return { ...state, partnerComposing: true };
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
  const assignedSlotRef = useRef(reconnectSlot || loadAssignedSlot(roomCode));
  const clientIdRef = useRef(getOrCreateClientId(roomCode));
  // connectRef holds a stable pointer to the connect function so the close
  // handler can schedule a reconnect without creating a forward-reference.
  const connectRef = useRef(() => {});

  // Stash the latest joinPayload/reconnectSlot in refs so the connect effect
  // can grab the freshest values without re-running on every keystroke.
  const joinPayloadRef = useRef(joinPayload);
  const reconnectSlotRef = useRef(reconnectSlot);
  useEffect(() => { joinPayloadRef.current = joinPayload; }, [joinPayload]);
  useEffect(() => { reconnectSlotRef.current = reconnectSlot; }, [reconnectSlot]);
  useEffect(() => {
    assignedSlotRef.current = reconnectSlot || loadAssignedSlot(roomCode);
    clientIdRef.current = getOrCreateClientId(roomCode);
  }, [roomCode, reconnectSlot]);

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
      dispatch({
        type: 'generation_start',
        actingSlot: data.acting_slot || null,
        actorName: data.actor_name || '',
      });
    } else if (t === 'generation_done') {
      dispatch({
        type: 'generation_done',
        actingSlot: data.acting_slot || null,
        actorName: data.actor_name || '',
      });
    } else if (t === 'slot_assigned') {
      assignedSlotRef.current = data.slot || null;
      saveAssignedSlot(roomCode, data.slot);
      dispatch({
        type: 'self_assigned',
        slot: data.slot || null,
        displayName: data.display_name || joinPayloadRef.current?.displayName || '',
        characterName: data.character_name || joinPayloadRef.current?.characterName || '',
      });
    } else if (t === 'partner_composing') {
      dispatch({ type: 'partner_composing' });
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
      if (data.code === 'join_failed') {
        intentionalCloseRef.current = true;
      }
      dispatch({ type: 'transient_error', message: data.message || 'unknown error' });
    } else if (t === 'session_paused' || t === 'session_resumed' || t === 'player_joined' || t === 'player_ready' || t === 'floor_passed') {
      // These are informational only — sessionState updates follow immediately
      // for any state changes. Nothing to do here.
    }
  }, [roomCode]);

  const connect = useCallback(() => {
    if (!enabled || !roomCode) return;
    if (typeof window === 'undefined') return;
    intentionalCloseRef.current = false;
    dispatch({ type: 'connecting' });

    const ws = new WebSocket(wsUrl(`/api/session/${encodeURIComponent(roomCode)}/ws`));
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      reconnectAttemptRef.current = 0;
      dispatch({ type: 'open' });
      const reconnect = reconnectSlotRef.current || assignedSlotRef.current || loadAssignedSlot(roomCode);
      const payload = joinPayloadRef.current || {};
      if (reconnect) {
        ws.send(JSON.stringify({
          type: 'reconnect',
          slot: reconnect,
          client_id: clientIdRef.current,
          display_name: payload.displayName || '',
          character_name: payload.characterName || '',
        }));
      } else {
        ws.send(JSON.stringify({
          type: 'join',
          display_name: payload.displayName || '',
          character_name: payload.characterName || '',
          preference_profile: payload.preferenceProfile || null,
          preference_source: payload.preferenceSource || 'none',
          slot: payload.desiredSlot || null,
          client_id: clientIdRef.current,
        }));
      }
    };

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) return;
      handleMessage(event);
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      dispatch({ type: 'closed' });
      wsRef.current = null;
      if (intentionalCloseRef.current) return;
      const attempt = reconnectAttemptRef.current + 1;
      if (attempt > RECONNECT_DELAYS_MS.length) {
        dispatch({ type: 'error', message: 'Connection lost. Refresh or rejoin the room.' });
        return;
      }
      reconnectAttemptRef.current = attempt;
      const delay = RECONNECT_DELAYS_MS[Math.min(attempt - 1, RECONNECT_DELAYS_MS.length - 1)];
      dispatch({ type: 'reconnect_scheduled', attempt });
      reconnectTimerRef.current = window.setTimeout(() => connectRef.current(), delay);
    };

    ws.onerror = () => {
      if (wsRef.current !== ws) return;
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
