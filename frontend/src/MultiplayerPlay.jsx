import { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, describeApiError } from './lib/api';

/**
 * In-game view for an active multiplayer session.
 *
 * Renders:
 *   - The narrative log (assistant messages from /api/state, plus the live
 *     streaming text from the WS hook during generation).
 *   - The player's input box, locked when it's not their turn.
 *   - A turn indicator, OOC chat, and host management controls.
 */
export default function MultiplayerPlay({
  campaignId,
  mySlot,
  sessionState,
  multiplayer,
  liveAssistantText,
  generating,
  oocMessages,
  partnerComposing,
  partnerSubmittedThisRound,
  onSubmitAction,
  onSendOOC,
  onComposing,
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
  const composingTimer = useRef(null);

  // The host loads /api/state directly (it's host-only). The guest sees only
  // the assistant narration that has been broadcast over the WS — which we
  // approximate by storing each completed AI turn locally.
  useEffect(() => {
    let cancelled = false;
    if (mySlot !== 'host' || !campaignId) return undefined;
    (async () => {
      try {
        const res = await apiFetch(`/api/state/${campaignId}`, {
          headers: { 'X-Player-Slot': 'host' },
        });
        if (!res.ok) {
          setLoadError('Failed to load campaign state.');
          return;
        }
        const data = await res.json();
        if (cancelled) return;
        const visible = (data.messages || []).filter(
          (m) => m.role === 'assistant' && !m.is_kickoff,
        );
        setAssistantMessages(visible);
      } catch (e) {
        if (!cancelled) setLoadError(describeApiError(e));
      }
    })();
    return () => { cancelled = true; };
  }, [mySlot, campaignId, generating]);

  // For guests we stash the streamed text into history when the round ends —
  // the hook resets `liveAssistantText` to '' on generation_done.
  const lastLiveTextRef = useRef('');
  useEffect(() => {
    if (mySlot === 'host') return;
    if (liveAssistantText) {
      lastLiveTextRef.current = liveAssistantText;
    }
    if (!generating && lastLiveTextRef.current) {
      setAssistantMessages((prev) => [
        ...prev,
        {
          id: `local_${Date.now()}`,
          role: 'assistant',
          content: lastLiveTextRef.current,
          turn_id: `live_${Date.now()}`,
        },
      ]);
      lastLiveTextRef.current = '';
    }
  }, [mySlot, liveAssistantText, generating]);

  const status = sessionState?.status || 'paused';
  const activeSlot = sessionState?.active_slot || null;
  const isMyTurn = activeSlot === mySlot && !generating && status !== 'paused';
  const inputLocked = !isMyTurn;

  const indicatorText = useMemo(() => {
    if (status === 'paused') return 'Partner disconnected — waiting up to 5 minutes for reconnect.';
    if (status === 'archived') return 'Session archived.';
    if (generating) return 'Both players submitted — AI is writing…';
    if (status === 'lobby') return 'Returning to lobby…';
    if (activeSlot === mySlot) {
      return partnerSubmittedThisRound
        ? 'Partner has already submitted. Your turn.'
        : 'Your turn — type your action.';
    }
    const partnerName = (mySlot === 'host'
      ? sessionState?.players?.guest?.character_name
      : sessionState?.players?.host?.character_name) || 'Partner';
    if (partnerSubmittedThisRound) return `${partnerName} has submitted. Waiting for round.`;
    if (partnerComposing) return `${partnerName} is composing…`;
    return `${partnerName} has the floor.`;
  }, [status, activeSlot, mySlot, generating, partnerSubmittedThisRound, partnerComposing, sessionState]);

  const handleSubmit = () => {
    const text = draft.trim();
    if (!text) return;
    onSubmitAction(text);
    setDraft('');
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
      <div className="max-w-6xl mx-auto grid lg:grid-cols-[3fr_1fr] gap-4">
        <div className="flex flex-col h-[calc(100vh-2rem)]">
          <header className="flex justify-between items-baseline mb-2">
            <div>
              <h1 className="text-2xl text-fantasy-accent">Round {sessionState?.turn_number ?? 0}</h1>
              <div className="text-sm text-slate-400 font-sans">{indicatorText}</div>
            </div>
            <div className="flex gap-2 text-xs font-sans">
              <button onClick={onLeave} className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-3 py-1 rounded">Leave</button>
              {mySlot === 'host' && (
                <>
                  <button onClick={onArchive} className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-3 py-1 rounded">Archive</button>
                  <button onClick={onDelete} className="bg-red-900/40 hover:bg-red-800/60 text-red-200 border border-red-900/50 px-3 py-1 rounded">Delete</button>
                </>
              )}
            </div>
          </header>

          {loadError && (
            <div className="bg-red-900/30 border border-red-900/50 text-red-200 px-3 py-2 mb-2 text-sm rounded">
              {loadError}
            </div>
          )}

          <div className="flex-1 overflow-y-auto bg-fantasy-panel/30 border border-slate-700/40 rounded p-4 mb-2 space-y-3">
            {assistantMessages.length === 0 && !generating && (
              <p className="text-slate-500 italic text-sm">No narration yet — the GM is waiting on your first round.</p>
            )}
            {assistantMessages.map((m) => (
              <div key={m.id} className="text-fantasy-text whitespace-pre-wrap leading-relaxed">
                {m.content}
              </div>
            ))}
            {generating && liveAssistantText && (
              <div className="text-fantasy-text whitespace-pre-wrap leading-relaxed border-l-2 border-amber-600 pl-3">
                {liveAssistantText}<span className="animate-pulse">▋</span>
              </div>
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
              <div>
                {partnerSubmittedThisRound && !inputLocked && (
                  <span className="text-amber-300">Partner is ready — submit when you're done.</span>
                )}
              </div>
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

        <aside className="flex flex-col gap-3 h-[calc(100vh-2rem)]">
          <RosterPanel mySlot={mySlot} sessionState={sessionState} multiplayer={multiplayer} onEjectGuest={mySlot === 'host' ? onEjectGuest : null} />
          <OocPanel
            open={oocOpen}
            setOpen={setOocOpen}
            messages={oocMessages}
            mySlot={mySlot}
            draft={oocDraft}
            setDraft={setOocDraft}
            onSubmit={handleOocSubmit}
          />
        </aside>
      </div>
    </div>
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
          const isYou = slot === mySlot;
          return (
            <li key={slot} className={`flex items-center gap-2 px-2 py-1 rounded border ${isYou ? 'border-amber-700/50 bg-amber-900/10' : 'border-slate-700/50 bg-slate-800/40'}`}>
              <span className={`w-2 h-2 rounded-full ${p?.is_connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <div className="flex-1">
                <div className="text-amber-200">{character?.name || (slot === 'host' ? 'Host' : 'Guest')}</div>
                <div className="text-xs text-slate-400">
                  {p ? p.display_name : 'not joined'} · {slot}
                  {isYou ? ' · you' : ''}
                </div>
              </div>
              {onEjectGuest && slot === 'guest' && p && (
                <button
                  onClick={onEjectGuest}
                  className="text-xs text-red-200 border border-red-900/40 hover:bg-red-900/30 rounded px-2 py-0.5"
                >Eject</button>
              )}
            </li>
          );
        })}
      </ul>
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
