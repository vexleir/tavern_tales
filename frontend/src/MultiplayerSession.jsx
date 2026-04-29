import { useEffect, useMemo, useState } from 'react';
import useMultiplayerSession from './hooks/useMultiplayerSession';
import MultiplayerLobby from './MultiplayerLobby';
import MultiplayerPlay from './MultiplayerPlay';

const PLAY_STATUSES = new Set(['host_turn', 'guest_turn', 'generating', 'paused']);

/**
 * Top-level multiplayer view. Owns the WS hook and dispatches between the
 * lobby (LOBBY status) and the play screen (HOST_TURN / GUEST_TURN /
 * GENERATING / PAUSED). The component receives a join payload from the
 * caller — no in-component "enter your name" form here, that's handled by
 * MultiplayerEntry.
 */
export default function MultiplayerSession({
  roomCode,
  joinUrl,
  joinPayload,
  onLeave,
  onArchived,
  banner,
}) {
  const session = useMultiplayerSession({ roomCode, joinPayload, enabled: true });
  const { state, ...actions } = session;

  // Surface transient WS errors to the global banner.
  useEffect(() => {
    if (state.lastError && banner?.error) {
      banner.error(state.lastError);
      actions.clearError();
    }
  }, [state.lastError, banner, actions]);

  // Notify parent if the session ended.
  useEffect(() => {
    if (state.archivedReason && onArchived) {
      onArchived(state.archivedReason);
    }
  }, [state.archivedReason, onArchived]);

  const status = state.sessionState?.status || 'lobby';
  const isLobby = status === 'lobby';
  const isPlay = PLAY_STATUSES.has(status);

  if (state.status === 'connecting' && !state.sessionState) {
    return <CenteredMessage title="Connecting…" detail="Opening the multiplayer channel." />;
  }
  if (state.status === 'closed' && !state.sessionState) {
    return <CenteredMessage title="Disconnected" detail={state.errorMessage || 'Connection closed.'} actionLabel="Back" onAction={onLeave} />;
  }

  if (isLobby) {
    return (
      <MultiplayerLobby
        roomCode={roomCode}
        joinUrl={joinUrl}
        mySlot={state.mySlot}
        sessionState={state.sessionState}
        multiplayer={state.multiplayer}
        mergedPreferenceSummary={state.mergedPreferenceSummary}
        onReady={actions.readyUp}
        onUnready={actions.unready}
        onUpdateCharacter={actions.updateCharacter}
        onArchive={actions.archiveSession}
        onDelete={actions.deleteSession}
        onEjectGuest={actions.ejectGuest}
        onLeave={onLeave}
      />
    );
  }

  if (isPlay) {
    return (
      <MultiplayerPlay
        roomCode={roomCode}
        campaignId={state.sessionState?.campaign_id}
        mySlot={state.mySlot}
        sessionState={state.sessionState}
        multiplayer={state.multiplayer}
        liveAssistantText={state.liveAssistantText}
        generating={state.generating}
        oocMessages={state.oocMessages}
        partnerComposing={state.partnerComposing}
        partnerSubmittedThisRound={state.partnerSubmittedThisRound}
        onSubmitAction={actions.submitAction}
        onSendOOC={actions.sendOOC}
        onComposing={actions.composing}
        onArchive={actions.archiveSession}
        onDelete={actions.deleteSession}
        onEjectGuest={actions.ejectGuest}
        onLeave={onLeave}
      />
    );
  }

  if (status === 'archived') {
    return <CenteredMessage title="Session ended" detail="The host archived this session." actionLabel="Back" onAction={onLeave} />;
  }

  return <CenteredMessage title={`Session status: ${status}`} detail="Unrecognized session state." actionLabel="Back" onAction={onLeave} />;
}

function CenteredMessage({ title, detail, actionLabel, onAction }) {
  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-serif flex flex-col items-center justify-center p-8">
      <h1 className="text-3xl text-fantasy-accent mb-3">{title}</h1>
      {detail && <p className="text-slate-300 mb-6 text-sm font-sans">{detail}</p>}
      {actionLabel && (
        <button
          onClick={onAction}
          className="bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-600 px-4 py-2 rounded font-sans text-sm uppercase tracking-widest"
        >{actionLabel}</button>
      )}
    </div>
  );
}

/**
 * Entry / launcher screen for multiplayer.
 *
 * The host arrives here after creating a session through CampaignCreator (with
 * the room_code in URL or props). The guest arrives by entering a room code
 * manually or by following the join URL.
 *
 * Once a roomCode and a joinPayload are in hand, render <MultiplayerSession>.
 */
function _initialRoomCodeFrom(prop) {
  if (prop) return prop.toUpperCase();
  if (typeof window === 'undefined') return '';
  try {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('room_code');
    if (fromUrl) return fromUrl.toUpperCase();
  } catch {
    // ignore
  }
  return '';
}

export function MultiplayerEntry({ initialRoomCode = '', onBack, banner }) {
  // Lazy initializer pulls the room code from props or the URL exactly once,
  // so we never have to setRoomCode inside an effect.
  const [roomCode, setRoomCode] = useState(() => _initialRoomCodeFrom(initialRoomCode));
  const [displayName, setDisplayName] = useState('');
  const [characterName, setCharacterName] = useState('');
  const [preferenceProfile, setPreferenceProfile] = useState(null);
  const [preferenceSource, setPreferenceSource] = useState('none');
  const [preferenceTab, setPreferenceTab] = useState('skip'); // skip | quick | import
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState('');
  const [launched, setLaunched] = useState(false);

  const joinUrl = useMemo(() => {
    if (!roomCode) return '';
    // Use the current origin so the URL works for any guest on the same LAN
    // who can reach our Vite server (host's machine + port 5173).
    const frontendOrigin = window.location.origin;
    return `${frontendOrigin}/?room_code=${roomCode}`;
  }, [roomCode]);

  const handleImport = () => {
    setImportError('');
    try {
      const parsed = JSON.parse(importText);
      // Allow either the raw profile or the export envelope shape.
      const profile = parsed.profile || parsed;
      if (!profile.profileId && !profile.categories) {
        throw new Error('Not a valid preference profile JSON.');
      }
      setPreferenceProfile(profile);
      setPreferenceSource('imported');
    } catch (e) {
      setImportError(e.message || 'Could not parse JSON.');
      setPreferenceProfile(null);
      setPreferenceSource('none');
    }
  };

  const buildQuickPreferenceProfile = (answers) => {
    // Build a minimal valid profile so the merger can include themes from this
    // player's quick answers. Each answer maps to a multiplayer-context item.
    const profile = {
      profileId: `quick_${Date.now()}`,
      userId: 'lobby_quick',
      displayName: displayName ? `${displayName} (Quick Setup)` : 'Quick Setup',
      profileVersion: 1,
      schemaVersion: '1.0.0',
      status: 'active',
      globalPreferences: {
        consentStyle: 'explicit',
        fadeToBlack: answers.fadeToBlack,
        preferredPOV: 'third',
        rolePreference: 'switch',
      },
      categories: [
        {
          id: 'lobby_quick_themes',
          label: 'Quick Setup',
          items: QUICK_THEMES.map((theme) => ({
            id: theme.id,
            label: theme.label,
            description: theme.description,
            fantasyInterest: answers.themes[theme.id] || 'none',
            realWorldWillingness: 'discuss_only',
            textRoleplayWillingness: answers.themes[theme.id] && answers.themes[theme.id] !== 'none' ? 'yes' : 'no',
            intensityPreference: answers.intensity,
            giverReceiverRole: 'both',
            context: ['multiplayer'],
            fantasyOnly: true,
            partnerSharePermission: 'overlap_only',
          })),
        },
      ],
    };
    setPreferenceProfile(profile);
    setPreferenceSource('lobby_form');
  };

  const ready = roomCode.length >= 4 && displayName.trim() && characterName.trim();

  if (launched && roomCode) {
    return (
      <MultiplayerSession
        roomCode={roomCode}
        joinUrl={joinUrl}
        joinPayload={{
          displayName,
          characterName,
          preferenceProfile,
          preferenceSource,
        }}
        onLeave={onBack}
        banner={banner}
        onArchived={() => setLaunched(false)}
      />
    );
  }

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-serif p-6">
      <div className="max-w-3xl mx-auto bg-fantasy-panel/40 border border-slate-700/50 rounded-xl p-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl text-fantasy-accent">Join a Multiplayer Session</h1>
          <button onClick={onBack} className="text-sm text-slate-400 hover:text-amber-300 underline font-sans">Back</button>
        </div>

        <div className="space-y-4 font-sans text-sm">
          <Field label="Room Code">
            <input
              value={roomCode}
              onChange={(e) => setRoomCode(e.target.value.toUpperCase().slice(0, 8))}
              placeholder="e.g. WOLF42"
              maxLength={8}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-amber-100 font-mono tracking-widest text-lg"
            />
          </Field>

          <Field label="Your Display Name">
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={80}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-amber-100" />
          </Field>

          <Field label="Your Character Name">
            <input value={characterName} onChange={(e) => setCharacterName(e.target.value)} maxLength={80}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-amber-100" />
          </Field>

          <div className="pt-2">
            <h2 className="text-amber-300 text-xs uppercase tracking-widest mb-2">Preferences (optional)</h2>
            <div className="flex gap-1 mb-2">
              {[
                ['skip', 'Skip'],
                ['quick', 'Quick Setup'],
                ['import', 'Import JSON'],
              ].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setPreferenceTab(key)}
                  className={`px-3 py-1 rounded text-xs ${
                    preferenceTab === key
                      ? 'bg-amber-700 text-white'
                      : 'bg-slate-800 text-slate-300 border border-slate-700'
                  }`}
                >{label}</button>
              ))}
            </div>
            {preferenceTab === 'skip' && (
              <p className="text-xs text-slate-400">No preferences shared. The session will use whatever the host has set.</p>
            )}
            {preferenceTab === 'quick' && (
              <QuickPreferenceForm
                onChange={buildQuickPreferenceProfile}
                isApplied={preferenceSource === 'lobby_form'}
              />
            )}
            {preferenceTab === 'import' && (
              <div>
                <textarea
                  value={importText}
                  onChange={(e) => setImportText(e.target.value)}
                  rows={6}
                  placeholder="Paste your exported preference profile JSON here…"
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100 font-mono text-xs"
                />
                <div className="flex gap-2 mt-2 items-center">
                  <button onClick={handleImport} className="bg-indigo-700 hover:bg-indigo-600 text-white text-xs px-3 py-1 rounded">Use this profile</button>
                  {preferenceSource === 'imported' && <span className="text-xs text-emerald-400">Profile loaded.</span>}
                  {importError && <span className="text-xs text-red-400">{importError}</span>}
                </div>
              </div>
            )}
          </div>

          <div className="pt-4">
            <button
              onClick={() => setLaunched(true)}
              disabled={!ready}
              className={`w-full px-5 py-3 rounded font-bold uppercase tracking-widest text-sm transition ${
                ready
                  ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed'
              }`}
            >Connect to Room</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-slate-400 tracking-widest">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

const QUICK_THEMES = [
  { id: 'quick_action', label: 'Action & combat', description: 'Fights, chases, dramatic peril.' },
  { id: 'quick_intrigue', label: 'Intrigue & mystery', description: 'Secrets, clues, schemes.' },
  { id: 'quick_romance', label: 'Romance', description: 'Tender or charged moments between characters.' },
  { id: 'quick_horror', label: 'Horror & dread', description: 'Suspense, fear, the uncanny.' },
  { id: 'quick_humor', label: 'Humor', description: 'Comic beats, banter, absurdity.' },
  { id: 'quick_dark', label: 'Dark themes', description: 'Loss, betrayal, moral weight.' },
  { id: 'quick_intimacy', label: 'Explicit intimacy', description: 'On-page intimate scenes; off if either player declines.' },
];

const INTEREST_LEVELS = [
  ['none', 'Not for me'],
  ['low', 'A little'],
  ['medium', 'Sure'],
  ['high', 'Yes please'],
];

function QuickPreferenceForm({ onChange, isApplied }) {
  const [intensity, setIntensity] = useState('moderate');
  const [fadeToBlack, setFadeToBlack] = useState(true);
  const [themes, setThemes] = useState(() => Object.fromEntries(QUICK_THEMES.map((t) => [t.id, 'none'])));

  const apply = () => onChange({ intensity, fadeToBlack, themes });

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs">
          <span className="text-slate-400 uppercase tracking-widest">Intensity ceiling</span>
          <select value={intensity} onChange={(e) => setIntensity(e.target.value)}
            className="block w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100 mt-1">
            <option value="light">Light</option>
            <option value="moderate">Moderate</option>
            <option value="intense">Intense</option>
          </select>
        </label>
        <label className="text-xs flex items-end gap-2">
          <input type="checkbox" checked={fadeToBlack} onChange={(e) => setFadeToBlack(e.target.checked)} />
          <span>Prefer fade-to-black for explicit scenes</span>
        </label>
      </div>
      <div className="space-y-1">
        {QUICK_THEMES.map((theme) => (
          <div key={theme.id} className="flex items-center gap-2 text-xs">
            <div className="flex-1">
              <div className="text-amber-200">{theme.label}</div>
              <div className="text-slate-500">{theme.description}</div>
            </div>
            <select
              value={themes[theme.id]}
              onChange={(e) => setThemes((t) => ({ ...t, [theme.id]: e.target.value }))}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-100"
            >
              {INTEREST_LEVELS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </div>
        ))}
      </div>
      <button onClick={apply} className="bg-indigo-700 hover:bg-indigo-600 text-white text-xs px-3 py-1 rounded">
        {isApplied ? 'Update Quick Preferences' : 'Apply Quick Preferences'}
      </button>
    </div>
  );
}
