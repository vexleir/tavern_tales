import { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, describeApiError } from './lib/api';

/**
 * In-game view for an active multiplayer session.
 *
 * Renders:
 *   - The narrative log (public session export, plus the live streaming text
 *     from the WS hook during generation).
 *   - The player's input box, locked when it's not their turn.
 *   - A turn indicator, OOC chat, and host management controls.
 */
export default function MultiplayerPlay({
  roomCode,
  mySlot,
  sessionState,
  multiplayer,
  liveAssistantText,
  currentGeneration,
  lastCompletedGeneration,
  generating,
  reconnectAttempt = 0,
  oocMessages,
  partnerComposing,
  onSubmitAction,
  onGiftTurn,
  onRequestReroll,
  onRequestContinue,
  onSendOOC,
  onComposing,
  onUpdateCharacter,
  onArchive,
  onDelete,
  onEjectGuest,
  onLeave,
}) {
  const [draft, setDraft] = useState('');
  const [oocDraft, setOocDraft] = useState('');
  const [oocOpen, setOocOpen] = useState(true);
  const [assistantMessages, setAssistantMessages] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [mobileTab, setMobileTab] = useState('party'); // party | ooc
  const composingTimer = useRef(null);

  // Both players can reload the public multiplayer narrative from the session
  // export endpoint. This keeps guests from losing prior turns after a refresh.
  useEffect(() => {
    let cancelled = false;
    if (!roomCode || generating) return undefined;
    (async () => {
      try {
        const res = await apiFetch(`/api/session/${encodeURIComponent(roomCode)}/export`, {
          method: 'POST',
        });
        if (!res.ok) {
          setLoadError('Failed to load session narrative.');
          return;
        }
        const data = await res.json();
        if (cancelled) return;
        const visible = (data.turns || [])
          .map((turn, index) => ({
            id: turn.id || turn.turn_id || `${turn.timestamp || 'turn'}_${index}`,
            role: 'assistant',
            content: turn.gm_content || turn.content || '',
            timestamp: turn.timestamp || '',
            turn_id: turn.turn_id || null,
            partial: Boolean(turn.partial),
            player_slot: turn.player_slot || null,
            actor_name: turn.actor_name || '',
            player_action: turn.player_action || '',
            is_kickoff: Boolean(turn.is_kickoff),
          }));
        setAssistantMessages(visible);
        setLoadError(null);
      } catch (e) {
        if (!cancelled) setLoadError(describeApiError(e));
      }
    })();
    return () => { cancelled = true; };
  }, [roomCode, generating]);

  // Stash streamed text into history when the turn ends —
  // the hook resets `liveAssistantText` to '' on generation_done.
  const lastLiveTextRef = useRef('');
  useEffect(() => {
    if (liveAssistantText) {
      lastLiveTextRef.current = liveAssistantText;
    }
    if (!generating && lastLiveTextRef.current) {
      const streamedText = lastLiveTextRef.current;
      const completed = lastCompletedGeneration || {};
      setAssistantMessages((prev) => {
        const replacement = {
          id: completed.gmMsgId || `local_${Date.now()}`,
          role: 'assistant',
          content: streamedText,
          turn_id: `live_${Date.now()}`,
          player_slot: completed.slot || null,
          actor_name: completed.actorName || '',
          player_action: completed.playerAction || '',
          is_kickoff: Boolean(completed.isKickoff),
          partial: Boolean(completed.partial),
        };

        if (completed.mode === 'continue') {
          const targetIndex = completed.targetMessageId
            ? prev.findIndex((m) => m.id === completed.targetMessageId)
            : prev.length - 1;
          if (targetIndex < 0) return prev;
          const copy = [...prev];
          const current = copy[targetIndex];
          const separator = current.content.endsWith('\n') || current.content.endsWith(' ') ? '' : ' ';
          copy[targetIndex] = {
            ...current,
            content: `${current.content}${separator}${streamedText}`,
            partial: Boolean(completed.partial),
          };
          return copy;
        }

        if (completed.mode === 'reroll') {
          const targetIndex = completed.targetMessageId
            ? prev.findIndex((m) => m.id === completed.targetMessageId)
            : prev.length - 1;
          if (targetIndex < 0) return [...prev, replacement];
          const copy = [...prev];
          copy[targetIndex] = replacement;
          return copy;
        }

        if (prev.some((m) => m.content === streamedText)) {
          return prev;
        }
        return [...prev, replacement];
      });
      lastLiveTextRef.current = '';
    }
  }, [liveAssistantText, generating, lastCompletedGeneration]);

  const status = sessionState?.status || 'paused';
  const players = sessionState?.players || {};
  const bothPlayersConnected = Boolean(players.host?.is_connected && players.guest?.is_connected);
  const activeSlot = sessionState?.active_slot || null;
  const kickoffPending = Boolean(sessionState?.kickoff_needed || sessionState?.kickoff_in_progress);
  const generationInProgress = generating || status === 'generating' || kickoffPending;
  const isMyTurn = activeSlot === mySlot && !generationInProgress && status !== 'paused';
  const partnerName = (mySlot === 'host'
    ? sessionState?.players?.guest?.character_name
    : sessionState?.players?.host?.character_name) || 'Partner';
  const canGiftTurn = (
    mySlot === 'host'
    && status === 'host_turn'
    && !generationInProgress
    && !kickoffPending
  );
  const lastAssistantMessage = assistantMessages.length > 0
    ? assistantMessages[assistantMessages.length - 1]
    : null;
  const canReviseLastMessage = Boolean(lastAssistantMessage && !generationInProgress && status !== 'paused' && status !== 'lobby');
  const canContinueLastMessage = Boolean(
    canReviseLastMessage
    && (
      lastAssistantMessage.partial
      || !/[.!?…"'”’)\]]+$/.test((lastAssistantMessage.content || '').trim())
    )
  );
  const inputLocked = !isMyTurn;
  const pausedSinceMs = Date.parse(sessionState?.paused_since || '');
  const reconnectWindowMs = (sessionState?.reconnect_window_seconds || 300) * 1000;
  const reconnectRemainingMs = Number.isFinite(pausedSinceMs)
    ? Math.max(0, pausedSinceMs + reconnectWindowMs - nowMs)
    : null;

  useEffect(() => {
    if (status !== 'paused' || !sessionState?.paused_since) return undefined;
    const id = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(id);
  }, [status, sessionState?.paused_since]);

  const indicatorText = useMemo(() => {
    if (status === 'paused') {
      if (bothPlayersConnected) return 'Both players are connected - restoring the turn state.';
      if (reconnectRemainingMs === 0) {
        return 'Reconnect window closed. Please contact the host for a new room code.';
      }
      if (reconnectRemainingMs !== null) {
        return `Partner disconnected - ${formatDuration(reconnectRemainingMs)} remaining.`;
      }
      return 'Partner disconnected - waiting for reconnect.';
    }
    if (status === 'archived') return 'Session archived.';
    if (kickoffPending) return 'Waiting for the opening scene...';
    if (generationInProgress && currentGeneration?.isKickoff) return 'Waiting for the opening scene...';
    if (generationInProgress) return 'AI is writing…';
    if (status === 'lobby') return 'Returning to lobby…';
    if (activeSlot === mySlot) {
      return 'Your turn — respond to the latest narration.';
    }
    if (partnerComposing) return `${partnerName} is composing…`;
    return `${partnerName} has the floor.`;
  }, [status, activeSlot, mySlot, generationInProgress, kickoffPending, currentGeneration, partnerComposing, partnerName, bothPlayersConnected, reconnectRemainingMs]);

  const handleSubmit = () => {
    const text = draft.trim();
    if (!text) return;
    onSubmitAction(text);
    setDraft('');
  };

  const handlePassTurn = () => {
    if (!isMyTurn) return;
    onSubmitAction('I wait and observe this turn.');
    setDraft('');
  };

  const handleRequestReroll = () => {
    if (!lastAssistantMessage) return;
    const ok = window.confirm('Request the GM to rewrite the last response?');
    if (!ok) return;
    onRequestReroll(lastAssistantMessage.id);
  };

  const handleRequestContinue = () => {
    if (!lastAssistantMessage) return;
    onRequestContinue(lastAssistantMessage.id);
  };

  const handleArchive = () => {
    if (!window.confirm('Archive this multiplayer session?')) return;
    onArchive();
  };

  const handleDelete = () => {
    if (!window.confirm('Delete this multiplayer session and its campaign? This cannot be undone.')) return;
    onDelete();
  };

  const handleDraftChange = (value) => {
    setDraft(value);
    if (composingTimer.current) window.clearTimeout(composingTimer.current);
    composingTimer.current = window.setTimeout(() => {
      onComposing();
    }, 350);
  };

  const handleOocSubmit = (e) => {
    e.preventDefault();
    const text = oocDraft.trim();
    if (!text) return;
    onSendOOC(text);
    setOocDraft('');
  };

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-serif p-4">
      <div className="max-w-6xl mx-auto lg:grid lg:grid-cols-[3fr_1fr] lg:gap-4">
        <div className="flex flex-col h-[calc(100vh-2rem)]">
          <header className="flex justify-between items-baseline mb-2">
            <div>
              <h1 className="text-2xl text-fantasy-accent">Turn {sessionState?.turn_number ?? 0}</h1>
              <div className="text-sm text-slate-400 font-sans">{indicatorText}</div>
            </div>
            <div className="flex gap-2 text-xs font-sans">
              <button onClick={onLeave} className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-3 py-1 rounded">Leave</button>
              {mySlot === 'host' && (
                <>
                  {canGiftTurn && (
                    <button onClick={onGiftTurn} className="bg-indigo-900/50 hover:bg-indigo-800/70 text-indigo-100 border border-indigo-700/60 px-3 py-1 rounded">
                      Gift Turn to {partnerName}
                    </button>
                  )}
                  <button onClick={handleArchive} className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-3 py-1 rounded">Archive</button>
                  <button onClick={handleDelete} className="bg-red-900/40 hover:bg-red-800/60 text-red-200 border border-red-900/50 px-3 py-1 rounded">Delete</button>
                </>
              )}
            </div>
          </header>

          {loadError && (
            <div className="bg-red-900/30 border border-red-900/50 text-red-200 px-3 py-2 mb-2 text-sm rounded">
              {loadError}
            </div>
          )}

          {reconnectAttempt > 0 && (
            <div className="bg-indigo-950/40 border border-indigo-700/40 text-indigo-100 px-3 py-2 mb-2 text-sm rounded font-sans">
              Reconnecting... attempt {reconnectAttempt}
            </div>
          )}

          <div className="flex-1 overflow-y-auto bg-fantasy-panel/30 border border-slate-700/40 rounded p-4 mb-2 space-y-3">
            {assistantMessages.length === 0 && !generating && (
              <p className="text-slate-500 italic text-sm">No narration yet — the GM is waiting on the first turn.</p>
            )}
            {assistantMessages.map((m) => (
              <NarrationBlock
                key={m.id}
                message={m}
                sessionState={sessionState}
                multiplayer={multiplayer}
              />
            ))}
            {canReviseLastMessage && (
              <div className="flex gap-2 text-xs font-sans">
                <button
                  type="button"
                  onClick={handleRequestReroll}
                  className="bg-slate-800 text-amber-300 border border-slate-600 hover:bg-slate-700 px-3 py-1 rounded-full shadow-md font-bold"
                >Reroll</button>
                {canContinueLastMessage && (
                  <button
                    type="button"
                    onClick={handleRequestContinue}
                    className="bg-slate-800 text-emerald-300 border border-slate-600 hover:bg-slate-700 px-3 py-1 rounded-full shadow-md font-bold"
                  >Continue</button>
                )}
              </div>
            )}
            {generating && liveAssistantText && (
              <NarrationBlock
                message={{
                  id: 'live',
                  content: liveAssistantText,
                  player_slot: currentGeneration?.slot || null,
                  actor_name: currentGeneration?.actorName || '',
                  player_action: currentGeneration?.playerAction || '',
                  is_kickoff: Boolean(currentGeneration?.isKickoff),
                }}
                sessionState={sessionState}
                multiplayer={multiplayer}
                live
              />
            )}
          </div>

          <div className="bg-fantasy-panel/30 border border-slate-700/40 rounded p-3">
            <textarea
              value={draft}
              onChange={(e) => handleDraftChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder={inputLocked ? indicatorText : 'Describe your action… (Ctrl+Enter to submit)'}
              rows={3}
              maxLength={4000}
              disabled={inputLocked}
              className={`w-full bg-slate-900 border border-slate-700 rounded p-2 text-amber-100 resize-none ${
                inputLocked ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            <div className="flex justify-between items-center mt-2 text-xs text-slate-400 font-sans">
              <div>{isMyTurn ? 'The next AI response will follow your prompt.' : ''}</div>
              <div className="flex gap-2">
                {isMyTurn && (
                  <button
                    type="button"
                    onClick={handlePassTurn}
                    className="px-3 py-1 rounded font-bold uppercase tracking-widest text-xs transition bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600"
                  >Pass Turn</button>
                )}
                <button
                  onClick={handleSubmit}
                  disabled={inputLocked || !draft.trim()}
                  className={`px-4 py-1 rounded font-bold uppercase tracking-widest text-xs transition ${
                    (inputLocked || !draft.trim())
                      ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                      : 'bg-emerald-700 hover:bg-emerald-600 text-white'
                  }`}
                >Submit</button>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile tab bar — only visible below lg */}
        <div className="lg:hidden flex border-b border-slate-700/50 mb-3 mt-3">
          {[['party', 'Party'], ['ooc', 'OOC Chat']].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setMobileTab(key)}
              className={`flex-1 py-2 text-sm font-sans font-bold transition ${
                mobileTab === key
                  ? 'text-amber-300 border-b-2 border-amber-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >{label}</button>
          ))}
        </div>

        <aside className="flex flex-col gap-3 lg:h-[calc(100vh-2rem)]">
          {/* Party panel — always visible on lg, tab-controlled on mobile */}
          <div className={mobileTab === 'party' ? 'block lg:block' : 'hidden lg:block'}>
            <RosterPanel mySlot={mySlot} sessionState={sessionState} multiplayer={multiplayer} onEjectGuest={mySlot === 'host' ? onEjectGuest : null} />
          </div>
          {/* OOC panel — always visible on lg, tab-controlled on mobile */}
          <div className={mobileTab === 'ooc' ? 'block lg:block' : 'hidden lg:block'}>
            <OocPanel
              open={oocOpen}
              setOpen={setOocOpen}
              messages={oocMessages}
              mySlot={mySlot}
              draft={oocDraft}
              setDraft={setOocDraft}
              onSubmit={handleOocSubmit}
            />
          </div>
          <CharacterSheetsPanel multiplayer={multiplayer} mySlot={mySlot} onUpdateCharacter={onUpdateCharacter} />
        </aside>
      </div>
    </div>
  );
}

function slotName(slot, sessionState, multiplayer, fallbackName = '') {
  if (fallbackName) return fallbackName;
  if (slot === 'host') {
    return multiplayer?.host_character?.name || sessionState?.players?.host?.character_name || 'Host';
  }
  if (slot === 'guest') {
    return multiplayer?.guest_character?.name || sessionState?.players?.guest?.character_name || 'Guest';
  }
  return 'Player';
}

function slotStyle(slot) {
  if (slot === 'guest') {
    return {
      border: 'border-cyan-400',
      badge: 'border-cyan-500/50 bg-cyan-500/15 text-cyan-100',
      accent: 'text-cyan-200',
    };
  }
  if (slot === 'host') {
    return {
      border: 'border-amber-500',
      badge: 'border-amber-600/50 bg-amber-500/15 text-amber-100',
      accent: 'text-amber-200',
    };
  }
  return {
    border: 'border-slate-500',
    badge: 'border-slate-600 bg-slate-800/70 text-slate-200',
    accent: 'text-slate-300',
  };
}

function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function NarrationBlock({ message, sessionState, multiplayer, live = false }) {
  const slot = message.player_slot;
  const name = slotName(slot, sessionState, multiplayer, message.actor_name);
  const styles = slotStyle(slot);
  const label = message.is_kickoff ? 'Opening Scene' : `Prompted by ${name}`;
  return (
    <article className={`text-fantasy-text border-l-4 ${styles.border} bg-slate-950/25 rounded-r px-3 py-2`}>
      <div className="font-sans text-[11px] uppercase tracking-widest mb-2 flex items-center gap-2">
        <span className={`border rounded px-2 py-0.5 ${styles.badge}`}>{label}</span>
        {live && <span className={`${styles.accent} normal-case tracking-normal`}>streaming</span>}
      </div>
      {message.player_action && (
        <div className="font-sans text-xs italic text-slate-400 mb-2 pl-1">
          <span className={styles.accent}>{name} said:</span> &quot;{message.player_action}&quot;
        </div>
      )}
      <div className="whitespace-pre-wrap leading-relaxed">
        {message.content}{live && <span className="animate-pulse">▋</span>}
      </div>
    </article>
  );
}

function RosterPanel({ mySlot, sessionState, multiplayer, onEjectGuest }) {
  const players = sessionState?.players || {};
  const slots = ['host', 'guest'];
  return (
    <div className="bg-fantasy-panel/30 border border-slate-700/40 rounded p-3 font-sans text-sm">
      <h2 className="text-amber-300 text-xs uppercase tracking-widest mb-2">Party</h2>
      <ul className="space-y-2">
        {slots.map((slot) => {
          const p = players[slot];
          const character = slot === 'host' ? multiplayer?.host_character : multiplayer?.guest_character;
          const displayName = character?.name || p?.display_name || (slot === 'host' ? 'Host' : 'Guest');
          const isYou = slot === mySlot;
          return (
            <li key={slot} className={`flex items-center gap-2 px-2 py-1 rounded border ${isYou ? 'border-amber-700/50 bg-amber-900/10' : 'border-slate-700/50 bg-slate-800/40'}`}>
              <span className={`w-2 h-2 rounded-full ${p?.is_connected ? 'bg-emerald-400' : 'bg-red-400'}`} aria-hidden="true" />
              <span className="sr-only">{p?.is_connected ? 'connected' : 'disconnected'}</span>
              <div className="flex-1">
                <div className="text-amber-200">{displayName}</div>
                <div className="text-xs text-slate-400">
                  {p ? p.display_name : 'not joined'}
                  {isYou ? ' · you' : ''}
                </div>
              </div>
              {onEjectGuest && slot === 'guest' && p && (
                <button
                  onClick={onEjectGuest}
                  className="text-xs text-red-200 border border-red-900/40 hover:bg-red-900/30 rounded px-2 py-0.5"
                >Eject {displayName}</button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function CharacterSheetsPanel({ multiplayer, mySlot, onUpdateCharacter }) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [myOpen, setMyOpen] = useState(true);
  const [partnerOpen, setPartnerOpen] = useState(false);
  const ownSlot = mySlot === 'guest' ? 'guest' : 'host';
  const partnerSlot = ownSlot === 'host' ? 'guest' : 'host';
  const characterFor = (slot) => (
    slot === 'host' ? multiplayer?.host_character : multiplayer?.guest_character
  );

  return (
    <section className="bg-fantasy-panel/30 border border-slate-700/40 rounded p-3 font-sans text-sm">
      <button
        type="button"
        onClick={() => setPanelOpen((open) => !open)}
        aria-expanded={panelOpen}
        className="flex w-full justify-between items-center text-amber-300 text-xs uppercase tracking-widest lg:cursor-default"
      >
        <span>Character Sheets</span>
        <span className="text-slate-500 lg:hidden">{panelOpen ? '-' : '+'}</span>
      </button>
      <div className={`${panelOpen ? 'block' : 'hidden'} lg:block mt-3 max-h-[42vh] overflow-y-auto pr-1 space-y-2`}>
        <CharacterSheetCard
          title="My Character"
          slot={ownSlot}
          character={characterFor(ownSlot)}
          open={myOpen}
          onToggle={() => setMyOpen((open) => !open)}
          canEdit={Boolean(onUpdateCharacter)}
          onBeginEdit={() => setMyOpen(true)}
          onUpdateCharacter={onUpdateCharacter}
        />
        <CharacterSheetCard
          title="Partner's Character"
          slot={partnerSlot}
          character={characterFor(partnerSlot)}
          open={partnerOpen}
          onToggle={() => setPartnerOpen((open) => !open)}
        />
      </div>
    </section>
  );
}

function characterDraft(character) {
  return {
    location: character?.location || '',
    appearance: character?.appearance || '',
    stats: Object.fromEntries(
      Object.entries(character?.stats || {}).map(([stat, value]) => [stat, String(value)]),
    ),
    inventory: [...(character?.inventory || [])],
  };
}

function CharacterSheetCard({
  title,
  slot,
  character,
  open,
  onToggle,
  canEdit = false,
  onBeginEdit,
  onUpdateCharacter,
}) {
  const styles = slotStyle(slot);
  const stats = Object.entries(character?.stats || {});
  const inventory = character?.inventory || [];
  const name = character?.name || (slot === 'host' ? 'Host Character' : 'Guest Character');
  const location = character?.location || 'Unknown location';
  const gender = character?.gender || 'Unspecified';
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => characterDraft(character));
  const [newInventoryItem, setNewInventoryItem] = useState('');

  const beginEdit = () => {
    if (!character) return;
    setDraft(characterDraft(character));
    setNewInventoryItem('');
    setEditing(true);
    onBeginEdit?.();
  };

  const cancelEdit = () => {
    setDraft(characterDraft(character));
    setNewInventoryItem('');
    setEditing(false);
  };

  const saveEdit = () => {
    const cleanedStats = Object.fromEntries(
      Object.entries(draft.stats).map(([stat, value]) => {
        const parsed = Number.parseInt(value, 10);
        return [stat, Number.isNaN(parsed) ? 0 : parsed];
      }),
    );
    const cleanedInventory = draft.inventory.map((item) => item.trim()).filter(Boolean);
    const sent = onUpdateCharacter?.({
      location: draft.location,
      appearance: draft.appearance,
      stats: cleanedStats,
      inventory: cleanedInventory,
    });
    if (sent !== false) {
      setEditing(false);
    }
  };

  const addInventoryItem = () => {
    const item = newInventoryItem.trim();
    if (!item) return;
    setDraft((current) => ({
      ...current,
      inventory: [...current.inventory, item],
    }));
    setNewInventoryItem('');
  };

  return (
    <article className={`border ${styles.border} bg-slate-900/45 rounded p-2`}>
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={() => {
            if (open && editing) setEditing(false);
            onToggle();
          }}
          aria-expanded={open}
          className="flex flex-1 items-start justify-between gap-2 text-left"
        >
          <span>
            <span className="block text-[11px] uppercase tracking-widest text-slate-500">{title}</span>
            <span className={`block ${styles.accent} font-semibold break-words`}>{name}</span>
          </span>
          <span className="text-slate-500 text-xs pt-1">{open ? '-' : '+'}</span>
        </button>
        {canEdit && character && open && (
          <button
            type="button"
            onClick={editing ? cancelEdit : beginEdit}
            className="text-[11px] border border-slate-600 bg-slate-800/80 hover:bg-slate-700 rounded px-2 py-1 text-slate-200"
          >
            {editing ? 'Cancel' : 'Edit'}
          </button>
        )}
      </div>
      {open && (
        <div className="mt-2 space-y-3 text-xs text-slate-300">
          {!character && (
            <p className="text-slate-500 italic">Waiting for this character to join.</p>
          )}
          {editing ? (
            <CharacterSheetEditor
              draft={draft}
              setDraft={setDraft}
              newInventoryItem={newInventoryItem}
              setNewInventoryItem={setNewInventoryItem}
              onAddInventoryItem={addInventoryItem}
              onCancel={cancelEdit}
              onSave={saveEdit}
            />
          ) : (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
                <dt className="text-slate-500">Location</dt>
                <dd className="break-words">{location}</dd>
                <dt className="text-slate-500">Gender</dt>
                <dd className="break-words">{gender}</dd>
                {character?.appearance && (
                  <>
                    <dt className="text-slate-500">Appearance</dt>
                    <dd className="break-words">{character.appearance}</dd>
                  </>
                )}
              </dl>
              <div>
                <div className="text-slate-500 uppercase tracking-widest text-[10px] mb-1">Stats</div>
                {stats.length > 0 ? (
                  <dl className="grid grid-cols-2 gap-1">
                    {stats.map(([stat, value]) => (
                      <div key={stat} className="bg-slate-950/45 border border-slate-700/50 rounded px-2 py-1">
                        <dt className="text-slate-500 truncate">{stat}</dt>
                        <dd className="text-amber-100 font-semibold">{value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="text-slate-500 italic">No stats recorded.</p>
                )}
              </div>
              <div>
                <div className="text-slate-500 uppercase tracking-widest text-[10px] mb-1">Inventory</div>
                {inventory.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {inventory.map((item, index) => (
                      <span key={`${item}-${index}`} className={`border rounded px-2 py-0.5 ${styles.badge} break-words`}>
                        {item}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 italic">Inventory empty.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </article>
  );
}

function CharacterSheetEditor({
  draft,
  setDraft,
  newInventoryItem,
  setNewInventoryItem,
  onAddInventoryItem,
  onCancel,
  onSave,
}) {
  const statEntries = Object.entries(draft.stats || {});

  return (
    <div className="space-y-3">
      <label className="block">
        <span className="text-slate-500 uppercase tracking-widest text-[10px]">Location</span>
        <input
          type="text"
          value={draft.location}
          onChange={(e) => setDraft((current) => ({ ...current, location: e.target.value }))}
          maxLength={200}
          className="mt-1 w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-amber-100"
        />
      </label>
      <label className="block">
        <span className="text-slate-500 uppercase tracking-widest text-[10px]">Appearance</span>
        <textarea
          value={draft.appearance}
          onChange={(e) => setDraft((current) => ({ ...current, appearance: e.target.value }))}
          maxLength={600}
          rows={3}
          className="mt-1 w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-amber-100 resize-y"
        />
      </label>
      <div>
        <div className="text-slate-500 uppercase tracking-widest text-[10px] mb-1">Stats</div>
        {statEntries.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {statEntries.map(([stat, value]) => (
              <label key={stat} className="block">
                <span className="block text-slate-500 truncate">{stat}</span>
                <input
                  type="number"
                  value={value}
                  onChange={(e) => {
                    const nextValue = e.target.value;
                    setDraft((current) => ({
                      ...current,
                      stats: { ...current.stats, [stat]: nextValue },
                    }));
                  }}
                  className="mt-1 w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-amber-100"
                />
              </label>
            ))}
          </div>
        ) : (
          <p className="text-slate-500 italic">No stats recorded.</p>
        )}
      </div>
      <div>
        <div className="text-slate-500 uppercase tracking-widest text-[10px] mb-1">Inventory</div>
        {draft.inventory.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {draft.inventory.map((item, index) => (
              <span key={`${item}-${index}`} className="inline-flex items-center gap-1 border border-slate-600 bg-slate-800/80 rounded px-2 py-0.5 text-slate-200">
                <span className="break-words">{item}</span>
                <button
                  type="button"
                  onClick={() => setDraft((current) => ({
                    ...current,
                    inventory: current.inventory.filter((_, i) => i !== index),
                  }))}
                  className="text-slate-400 hover:text-red-200"
                >
                  Remove
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex gap-1">
          <input
            type="text"
            value={newInventoryItem}
            onChange={(e) => setNewInventoryItem(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                onAddInventoryItem();
              }
            }}
            maxLength={120}
            className="flex-1 min-w-0 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-amber-100"
          />
          <button
            type="button"
            onClick={onAddInventoryItem}
            className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-2 text-slate-200"
          >
            +
          </button>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="border border-slate-600 bg-slate-800/80 hover:bg-slate-700 rounded px-2 py-1 text-slate-200"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onSave}
          className="bg-emerald-700 hover:bg-emerald-600 text-white rounded px-3 py-1 font-semibold"
        >
          Save
        </button>
      </div>
    </div>
  );
}

function OocPanel({ open, setOpen, messages, mySlot, draft, setDraft, onSubmit }) {
  return (
    <div className="bg-fantasy-panel/30 border border-slate-700/40 rounded p-3 font-sans text-sm flex-1 flex flex-col min-h-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex justify-between items-center text-amber-300 text-xs uppercase tracking-widest mb-2"
      >
        <span>Out-of-Character Chat</span>
        <span className="text-slate-500">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <>
          <div className="flex-1 overflow-y-auto space-y-1 bg-slate-900/40 rounded p-2 mb-2 min-h-0">
            {messages.length === 0 && (
              <p className="text-slate-500 italic text-xs">OOC messages stay between you and your partner — the AI never sees them.</p>
            )}
            {messages.map((m, i) => (
              <div key={`${m.ts}-${i}`} className={`text-xs ${m.slot === mySlot ? 'text-amber-200' : 'text-slate-300'}`}>
                <span className="text-slate-500">[{m.display_name || m.slot}]</span> {m.text}
              </div>
            ))}
          </div>
          <form onSubmit={onSubmit} className="flex gap-1">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={1000}
              placeholder="Say something out-of-character…"
              className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100 text-xs"
            />
            <button type="submit" className="bg-indigo-700 hover:bg-indigo-600 text-white text-xs px-2 rounded">Send</button>
          </form>
        </>
      )}
    </div>
  );
}
