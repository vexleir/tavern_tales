import { useMemo, useState } from 'react';

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
            title={mySlot === 'host' ? 'You (Host)' : 'You (Guest)'}
            isYou
            player={myPlayer}
            character={myCharacter}
            editable
            draft={draft}
            setDraft={setDraft}
            onSave={handleSaveCharacter}
          />
          <CharacterCard
            title={partnerSlot === 'host' ? 'Host' : 'Guest'}
            isYou={false}
            player={partnerPlayer}
            character={partnerCharacter}
            editable={false}
          />
        </div>

        <PreferenceSummaryPanel summary={mergedPreferenceSummary} />

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

function CharacterCard({ title, isYou, player, character, editable, draft, setDraft, onSave }) {
  const status = player ? (player.is_connected ? 'connected' : 'disconnected') : 'empty';
  return (
    <div className={`rounded-xl border p-4 ${isYou ? 'border-amber-700/50 bg-fantasy-panel/40' : 'border-slate-700/50 bg-fantasy-panel/20'}`}>
      <div className="flex justify-between items-baseline mb-2">
        <h2 className="text-lg text-amber-300 font-sans">{title}</h2>
        <span className={`text-xs font-sans uppercase tracking-widest ${
          status === 'connected' ? 'text-emerald-400' :
          status === 'disconnected' ? 'text-red-400' : 'text-slate-500'
        }`}>
          {status === 'empty' ? 'Not joined' : status}
          {player?.is_ready ? ' · ready' : ''}
        </span>
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
          <LabeledInput label="Name" value={draft.name} onChange={(v) => setDraft({ ...draft, name: v })} maxLength={80} />
          <LabeledInput label="Gender" value={draft.gender} onChange={(v) => setDraft({ ...draft, gender: v })} maxLength={40} />
          <LabeledInput label="Location" value={draft.location} onChange={(v) => setDraft({ ...draft, location: v })} maxLength={200} />
          <LabeledTextarea label="Appearance" value={draft.appearance} onChange={(v) => setDraft({ ...draft, appearance: v })} maxLength={600} rows={2} />
          <LabeledTextarea label="Description" value={draft.description} onChange={(v) => setDraft({ ...draft, description: v })} maxLength={1200} rows={3} />
          <button
            onClick={onSave}
            className="bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1 rounded text-xs font-bold uppercase tracking-widest"
          >Save Character</button>
        </div>
      )}
    </div>
  );
}

function LabeledInput({ label, value, onChange, maxLength }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-slate-400 tracking-widest">{label}</span>
      <input
        type="text"
        value={value || ''}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        className="block w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100"
      />
    </label>
  );
}

function LabeledTextarea({ label, value, onChange, maxLength, rows }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-slate-400 tracking-widest">{label}</span>
      <textarea
        value={value || ''}
        maxLength={maxLength}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
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
