import { useEffect, useMemo, useRef, useState } from 'react';

/**
 * Lobby screen for a multiplayer session.
 *
 * Shows the room code, both character cards (host + guest), the merged
 * preferences summary, and a Ready toggle. Host sees host-only management
 * controls (eject / archive / delete). When both players Ready, the parent
 * (MultiplayerSession) routes us into the Play view because session.status
 * advances to HOST_TURN.
 */
export default function MultiplayerLobby({
  roomCode,
  joinUrl,
  mySlot,
  sessionState,
  multiplayer,
  mergedPreferenceSummary,
  onReady,
  onUnready,
  onSetStartingSlot,
  onUpdateCharacter,
  onArchive,
  onDelete,
  onEjectGuest,
  onLeave,
}) {
  const myPlayer = sessionState?.players?.[mySlot] || null;
  const partnerSlot = mySlot === 'host' ? 'guest' : 'host';
  const partnerPlayer = sessionState?.players?.[partnerSlot] || null;

  const myCharacter = mySlot === 'host'
    ? multiplayer?.host_character
    : multiplayer?.guest_character;
  const partnerCharacter = mySlot === 'host'
    ? multiplayer?.guest_character
    : multiplayer?.host_character;
  const myTitle = myCharacter?.name ? `You - ${myCharacter.name}` : 'You';
  const partnerTitle = partnerCharacter?.name || partnerPlayer?.display_name || 'Partner';

  // The form is initialized from the current character once. After that,
  // local edits are canonical until the player clicks Save. Server-side
  // updates from another tab won't overwrite their in-progress edits.
  const [draft, setDraft] = useState(() => ({
    name: myCharacter?.name || '',
    gender: myCharacter?.gender || '',
    appearance: myCharacter?.appearance || '',
    description: myCharacter?.description || '',
    location: myCharacter?.location || '',
  }));

  const bothJoined = useMemo(
    () => Boolean(sessionState?.players?.host && sessionState?.players?.guest),
    [sessionState],
  );

  const canReady = bothJoined && Boolean(draft.name.trim());
  const isReady = Boolean(myPlayer?.is_ready);
  const startingSlot = sessionState?.starting_slot_this_round || 'host';

  const handleSaveCharacter = () => {
    onUpdateCharacter({
      name: draft.name,
      gender: draft.gender,
      appearance: draft.appearance,
      description: draft.description,
      location: draft.location,
    });
  };

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-serif p-6">
      <div className="max-w-5xl mx-auto">
        <header className="mb-6 flex justify-between items-start gap-4">
          <div>
            <h1 className="text-3xl text-fantasy-accent mb-1">Multiplayer Lobby</h1>
            <div className="text-sm text-slate-400 font-sans">
              Room <span className="font-mono text-amber-300 text-base tracking-widest">{roomCode}</span>
              {joinUrl && (
                <>
                  <span className="mx-2">·</span>
                  <span>Join URL:</span>{' '}
                  <a href={joinUrl} className="text-amber-400 underline break-all">{joinUrl}</a>{' '}
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(joinUrl)}
                    className="ml-1 text-xs underline text-slate-400 hover:text-amber-300"
                  >copy</button>
                </>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onLeave}
              className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-3 py-1 rounded text-sm font-sans"
              title="Disconnect from the session"
            >Leave</button>
          </div>
        </header>

        <div className="grid md:grid-cols-2 gap-4 mb-6">
          <CharacterCard
            title={myTitle}
            isYou
            player={myPlayer}
            character={myCharacter}
            editable
            draft={draft}
            setDraft={setDraft}
            onSave={handleSaveCharacter}
          />
          <CharacterCard
            title={partnerTitle}
            isYou={false}
            player={partnerPlayer}
            character={partnerCharacter}
            editable={false}
          />
        </div>

        <PreferenceSummaryPanel summary={mergedPreferenceSummary} />

        {mySlot === 'host' && (
          <StartingSlotControl
            value={startingSlot}
            onChange={onSetStartingSlot}
          />
        )}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 bg-fantasy-panel/30 border border-slate-700/40 rounded p-4">
          <div className="text-sm font-sans text-slate-300">
            {bothJoined
              ? (isReady ? 'You are READY. Waiting for partner.' : 'Click Ready when your character is set.')
              : 'Waiting for the other player to join…'}
          </div>
          <div className="flex gap-2">
            {!isReady && (
              <button
                onClick={onReady}
                disabled={!canReady}
                className={`px-5 py-2 rounded font-sans font-bold uppercase tracking-widest text-sm transition ${
                  canReady
                    ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                    : 'bg-slate-800 text-slate-500 cursor-not-allowed'
                }`}
              >Ready</button>
            )}
            {isReady && (
              <button
                onClick={onUnready}
                className="bg-amber-700 hover:bg-amber-600 text-white px-5 py-2 rounded font-sans font-bold uppercase tracking-widest text-sm transition"
              >Unready</button>
            )}
          </div>
        </div>

        {mySlot === 'host' && (
          <HostControls
            onEjectGuest={onEjectGuest}
            onArchive={onArchive}
            onDelete={onDelete}
            hasGuest={Boolean(partnerPlayer)}
          />
        )}
      </div>
    </div>
  );
}

function StartingSlotControl({ value, onChange }) {
  return (
    <fieldset className="mt-6 bg-fantasy-panel/30 border border-slate-700/40 rounded p-4 font-sans text-sm">
      <legend className="text-xs uppercase tracking-widest text-slate-400 mb-2">Who goes first?</legend>
      <div className="flex flex-wrap gap-3">
        {['host', 'guest'].map((slot) => (
          <label key={slot} className="inline-flex items-center gap-2 text-slate-200">
            <input
              type="radio"
              name="starting-slot"
              value={slot}
              checked={value === slot}
              onChange={() => onChange(slot)}
              className="accent-amber-500"
            />
            <span>{slot === 'host' ? 'Host' : 'Guest'}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function CharacterCard({ title, isYou, player, character, editable, draft, setDraft, onSave }) {
  const status = player ? (player.is_connected ? 'connected' : 'disconnected') : 'empty';
  const [savedBadge, setSavedBadge] = useState(false);
  const saveTimerRef = useRef(null);
  const savedTimerRef = useRef(null);

  useEffect(() => () => {
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    if (savedTimerRef.current) window.clearTimeout(savedTimerRef.current);
  }, []);

  const scheduleSave = () => {
    if (!editable || !onSave) return;
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      onSave();
      setSavedBadge(true);
      if (savedTimerRef.current) window.clearTimeout(savedTimerRef.current);
      savedTimerRef.current = window.setTimeout(() => setSavedBadge(false), 2000);
    }, 1000);
  };

  return (
    <div className={`rounded-xl border p-4 ${isYou ? 'border-amber-700/50 bg-fantasy-panel/40' : 'border-slate-700/50 bg-fantasy-panel/20'}`}>
      <div className="flex justify-between items-baseline mb-2">
        <h2 className="text-lg text-amber-300 font-sans">{title}</h2>
        <div className="flex items-center gap-2">
          {savedBadge && <span className="text-xs text-emerald-400 font-sans">&#10003; Saved</span>}
          <span className={`text-xs font-sans uppercase tracking-widest ${
            status === 'connected' ? 'text-emerald-400' :
            status === 'disconnected' ? 'text-red-400' : 'text-slate-500'
          }`}>
            {status === 'empty' ? 'Not joined' : status}
            {player?.is_ready ? ' · ready' : ''}
          </span>
        </div>
      </div>

      {!editable && (
        <div className="text-sm space-y-1 font-sans">
          <div><span className="text-slate-400">Name:</span> {character?.name || <em className="text-slate-500">unset</em>}</div>
          {character?.gender && <div><span className="text-slate-400">Gender:</span> {character.gender}</div>}
          {character?.location && <div><span className="text-slate-400">Location:</span> {character.location}</div>}
          {character?.appearance && <div className="text-slate-300 italic">{character.appearance}</div>}
          {character?.description && <div className="text-slate-400 text-xs">{character.description}</div>}
        </div>
      )}

      {editable && (
        <div className="space-y-2 font-sans text-sm">
          <LabeledInput label="Name" value={draft.name} onChange={(v) => setDraft({ ...draft, name: v })} onBlur={scheduleSave} maxLength={80} />
          <LabeledInput label="Gender" value={draft.gender} onChange={(v) => setDraft({ ...draft, gender: v })} onBlur={scheduleSave} maxLength={40} />
          <LabeledInput label="Location" value={draft.location} onChange={(v) => setDraft({ ...draft, location: v })} onBlur={scheduleSave} maxLength={200} />
          <LabeledTextarea label="Appearance" value={draft.appearance} onChange={(v) => setDraft({ ...draft, appearance: v })} onBlur={scheduleSave} maxLength={600} rows={2} />
          <LabeledTextarea label="Description" value={draft.description} onChange={(v) => setDraft({ ...draft, description: v })} onBlur={scheduleSave} maxLength={1200} rows={3} />
        </div>
      )}
    </div>
  );
}

function LabeledInput({ label, value, onChange, onBlur, maxLength }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-slate-400 tracking-widest">{label}</span>
      <input
        type="text"
        value={value || ''}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        className="block w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100"
      />
    </label>
  );
}

function LabeledTextarea({ label, value, onChange, onBlur, maxLength, rows }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-slate-400 tracking-widest">{label}</span>
      <textarea
        value={value || ''}
        maxLength={maxLength}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        className="block w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100 resize-y"
      />
    </label>
  );
}

function PreferenceSummaryPanel({ summary }) {
  const [open, setOpen] = useState(false);

  if (!summary || !summary.enabled) {
    return (
      <details className="bg-fantasy-panel/30 border border-slate-700/40 rounded p-3 text-sm font-sans">
        <summary className="cursor-pointer text-slate-300">Merged Preferences (no shared themes)</summary>
        <p className="mt-2 text-slate-400">
          No preference profiles were shared, or no themes overlap with multiplayer context.
          The session will run with default GM rules.
        </p>
      </details>
    );
  }

  return (
    <div className="bg-fantasy-panel/30 border border-slate-700/40 rounded p-4 text-sm font-sans">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex justify-between items-center text-left text-slate-200 hover:text-amber-300"
      >
        <span className="text-amber-300">Merged Preferences</span>
        <span className="text-xs text-slate-400">
          {summary.selected_count} themes · {summary.soft_caution_count} soft-caution · {summary.hard_no_count} excluded · {open ? 'hide' : 'show'}
        </span>
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <div className="text-xs text-slate-400">
            Intensity ceiling: lowest of both players · Fade-to-black: {summary.fade_to_black ? 'yes' : 'no'} · Consent: {summary.consent_style} · POV: {summary.preferred_pov}
          </div>
          <ul className="grid sm:grid-cols-2 gap-1 text-sm">
            {summary.themes.map((theme) => (
              <li
                key={theme.id}
                className={`px-2 py-1 rounded border ${
                  theme.softCaution
                    ? 'border-amber-700/50 bg-amber-900/10 text-amber-200'
                    : 'border-slate-700/50 bg-slate-800/40 text-slate-300'
                }`}
              >
                <span className="font-bold">{theme.label || theme.id}</span>
                <span className="text-xs text-slate-400 ml-2">
                  {theme.fantasyInterest} · {theme.intensityPreference}
                  {theme.softCaution ? ' · approach with care' : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function HostControls({ onEjectGuest, onArchive, onDelete, hasGuest }) {
  return (
    <div className="mt-6 flex flex-wrap gap-2 justify-end text-sm font-sans">
      {hasGuest && (
        <button
          onClick={onEjectGuest}
          className="bg-amber-900/40 hover:bg-amber-800/60 text-amber-200 border border-amber-800/50 px-3 py-1 rounded"
        >Eject Guest</button>
      )}
      <button
        onClick={onArchive}
        className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 px-3 py-1 rounded"
      >Archive Session</button>
      <button
        onClick={onDelete}
        className="bg-red-900/40 hover:bg-red-800/60 text-red-200 border border-red-900/50 px-3 py-1 rounded"
      >Delete Session</button>
    </div>
  );
}
