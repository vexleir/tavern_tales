import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import CampaignCreator from './CampaignCreator';
import PreferenceProfiles from './PreferenceProfiles';
import FantasyCreator from './FantasyCreator';
import { MultiplayerEntry } from './MultiplayerSession';
import BannerProvider from './components/BannerProvider';
import HelpModal from './components/HelpModal';
import ModalProvider from './components/ModalProvider';
import useBanner from './hooks/useBanner';
import useModal from './hooks/useModal';
import useNdjsonStream from './hooks/useNdjsonStream';
import { apiFetch, describeApiError } from './lib/api';

const createCampaignId = () => `campaign_${Date.now()}`;

const initialAppMode = () => {
  if (typeof window === 'undefined') return 'menu';
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get('room_code') ? 'multiplayer' : 'menu';
  } catch {
    return 'menu';
  }
};

const shouldShowLaunchHelp = () => {
  if (typeof window === 'undefined') return false;
  try {
    return !window.localStorage?.getItem('tt_has_launched');
  } catch {
    return true;
  }
};

const QUICK_ACTIONS = [
  { label: '⚔ Attack', text: 'I attack [target] with [weapon].' },
  { label: '🗣 Persuade', text: 'I attempt to persuade [character] to [goal].' },
  { label: '🔍 Search', text: 'I carefully search the [area] for anything hidden.' },
  { label: '🤫 Sneak', text: 'I try to move silently past [obstacle/character].' },
  { label: '💤 Rest', text: 'I take a short rest to catch my breath and recover.' },
  { label: '🎲 Roll', text: 'I roll to [skill/action].' },
];

const rollOutcomeMeta = {
  critical_success: { icon: '🎯', className: 'border-emerald-600/50 text-emerald-200' },
  success: { icon: '✅', className: 'border-emerald-600/50 text-emerald-200' },
  partial_success: { icon: '⚠️', className: 'border-amber-600/50 text-amber-200' },
  failure: { icon: '❌', className: 'border-red-700/50 text-red-200' },
  critical_failure: { icon: '💀', className: 'border-red-700/50 text-red-200' },
};

function formatDate(iso) {
  if (!iso) return '';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  return `Started ${parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}`;
}

function extractPlaceholders(template) {
  return [...new Set([...template.matchAll(/\[([^\]]+)\]/g)].map(match => match[1]))];
}

function resizeTextarea(element) {
  if (!element) return;
  element.style.height = 'auto';
  const nextHeight = Math.min(element.scrollHeight, 160);
  element.style.height = `${Math.max(nextHeight, 58)}px`;
  element.style.overflowY = element.scrollHeight > 160 ? 'auto' : 'hidden';
}

function RollResultBadge({ resolution }) {
  if (!resolution?.summary) return null;
  const meta = rollOutcomeMeta[resolution.outcome] || { icon: '🎲', className: 'border-amber-600/40 text-amber-200' };
  return (
    <div className={`bg-slate-800 border rounded-lg px-4 py-2 text-sm font-sans italic shadow-md ${meta.className}`}>
      <span className="mr-2 not-italic" aria-hidden="true">{meta.icon}</span>
      {resolution.summary}
    </div>
  );
}

function AppInner() {
  const [appMode, setAppMode] = useState(initialAppMode);
  const [activeCampaignId, setActiveCampaignId] = useState(() => createCampaignId());
  const [campaignState, setCampaignState] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [directorMode, setDirectorMode] = useState(false);
  const [savedCampaigns, setSavedCampaigns] = useState([]);
  const [promptStats, setPromptStats] = useState(null);
  const [lastPrompt, setLastPrompt] = useState(null);
  const [lastResolution, setLastResolution] = useState(null);
  const [undoStack, setUndoStack] = useState([]);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [newLoreKey, setNewLoreKey] = useState('');
  const [newLoreRule, setNewLoreRule] = useState('');
  const [renamingId, setRenamingId] = useState(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [pendingFantasyDraft, setPendingFantasyDraft] = useState(null);
  const [multiplayerLaunch, setMultiplayerLaunch] = useState(null);
  const [helpOpen, setHelpOpen] = useState(shouldShowLaunchHelp);
  const [helpManagesLaunchPreference, setHelpManagesLaunchPreference] = useState(shouldShowLaunchHelp);
  const [profilesOpen, setProfilesOpen] = useState(false);
  const [preferenceProfiles, setPreferenceProfiles] = useState(null);
  const [quickActionForm, setQuickActionForm] = useState(null);
  const [quickActionValues, setQuickActionValues] = useState({});
  const [lastRoomCard, setLastRoomCard] = useState(null);
  const [showQuickActions, setShowQuickActions] = useState(() => {
    try { return window.localStorage?.getItem('tt_quick_actions') !== 'false'; } catch { return true; }
  });

  const modal = useModal();
  const banner = useBanner();

  const buildLanJoinUrl = useCallback((roomCode, lanIp) => {
    if (!roomCode) return '';
    try {
      const here = new URL(window.location.origin);
      const hostname = lanIp || here.hostname;
      const port = here.port ? `:${here.port}` : '';
      return `${here.protocol}//${hostname}${port}/?room_code=${roomCode}`;
    } catch {
      return `/?room_code=${roomCode}`;
    }
  }, []);

  // Scroll the chat to the latest paragraph the first time a campaign's messages
  // populate — avoids landing on the prologue when reopening a long story.
  const scrollAnchorRef = useRef(null);
  const initialScrolledCampaignRef = useRef(null);
  const textareaRef = useRef(null);
  const quickActionContainerRef = useRef(null);

  useEffect(() => {
    if (appMode !== 'play' || messages.length === 0) return;
    if (initialScrolledCampaignRef.current === activeCampaignId) return;
    initialScrolledCampaignRef.current = activeCampaignId;
    // Wait one frame so the layout is committed before scrolling.
    requestAnimationFrame(() => {
      scrollAnchorRef.current?.scrollIntoView({ block: 'end' });
    });
  }, [appMode, activeCampaignId, messages.length]);

  // Auto-grow the textarea as user types; reset when input is cleared.
  useEffect(() => {
    if (!textareaRef.current) return;
    resizeTextarea(textareaRef.current);
  }, [input]);

  useEffect(() => {
    if (appMode !== 'play') {
      initialScrolledCampaignRef.current = null;
    }
  }, [appMode]);

  useEffect(() => {
    if (!quickActionForm) return;
    const closeOnEscape = (e) => {
      if (e.key === 'Escape') setQuickActionForm(null);
    };
    const closeOnOutsideClick = (e) => {
      if (!quickActionContainerRef.current?.contains(e.target)) {
        setQuickActionForm(null);
      }
    };
    document.addEventListener('keydown', closeOnEscape);
    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
      document.removeEventListener('mousedown', closeOnOutsideClick);
    };
  }, [quickActionForm]);

  // Story 7.1.3: Escape closes sidebar and prompt inspector.
  // Defers to ModalProvider when a modal dialog is on-screen (it owns Escape there).
  useEffect(() => {
    const onEscape = (e) => {
      if (e.key !== 'Escape') return;
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      if (inspectorOpen) { setInspectorOpen(false); return; }
      if (sidebarOpen) { setSidebarOpen(false); }
    };
    document.addEventListener('keydown', onEscape);
    return () => document.removeEventListener('keydown', onEscape);
  }, [inspectorOpen, sidebarOpen]);

  // -------------------------------------------------------- data access

  const refreshState = useCallback(async (id) => {
    try {
      const res = await apiFetch(`/api/state/${id}`);
      if (!res.ok) return null;
      const data = await res.json();
      setCampaignState(data);
      const visible = (data.messages || []).filter(m => !m.is_kickoff || m.role === 'assistant');
      setMessages(visible);
      return data;
    } catch (e) {
      banner.error(`Could not load campaign: ${describeApiError(e)}`);
      return null;
    }
  }, [banner]);

  const { isStreaming, streamEndpoint, stop: handleStop } = useNdjsonStream({
    onError: (msg, evt) => {
      if (evt?.partial) {
        banner.warn('The AI connection dropped mid-response. You can → Continue to extend it, or ↻ Reroll to try again.');
      } else {
        banner.error(msg);
      }
    },
    onAbortWithTokens: () => refreshState(activeCampaignId)
  });

  // Keep the scroll anchor visible during streaming so new tokens stay on screen.
  useEffect(() => {
    if (!isStreaming) return;
    scrollAnchorRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, isStreaming]);

  useEffect(() => {
    if (appMode === 'menu') {
      apiFetch('/api/campaigns')
        .then(r => r.json())
        .then(setSavedCampaigns)
        .catch(e => banner.error(`Could not list campaigns: ${describeApiError(e)}`));
      apiFetch('/api/preference-profiles')
        .then(r => (r.ok ? r.json() : []))
        .then(setPreferenceProfiles)
        .catch(() => setPreferenceProfiles(null));

      // Check if the user has a recently-joined session they can rejoin.
      try {
        const lastRoom = window.localStorage?.getItem('tt_last_room');
        const lastChar = window.localStorage?.getItem('tt_last_char');
        const lastDisplay = window.localStorage?.getItem('tt_last_display');
        if (lastRoom) {
          apiFetch(`/api/session/${lastRoom}/exists`)
            .then(r => (r.ok ? r.json() : null))
            .then(data => {
              if (data?.exists && data?.status !== 'archived') {
                setLastRoomCard({ roomCode: lastRoom, characterName: lastChar || '', displayName: lastDisplay || '' });
              } else {
                setLastRoomCard(null);
              }
            })
            .catch(() => setLastRoomCard(null));
        } else {
          window.setTimeout(() => setLastRoomCard(null), 0);
        }
      } catch { window.setTimeout(() => setLastRoomCard(null), 0); }
    }
  }, [appMode, banner]);

  // -------------------------------------------------------- kickoff / send

  const handleKickoff = async (id) => {
    setMessages([{ role: 'assistant', content: '', id: 'temp_kickoff' }]);
    await streamEndpoint(`/api/campaign/${id}/kickoff`, null, {
      onStart: (evt) => { setPromptStats(evt.stats); setLastResolution(null); },
      onToken: (t) => setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + t };
        return copy;
      }),
      onDone: async () => { await refreshState(id); }
    });
  };

  const handleSend = async (overrideText = null) => {
    const userText = typeof overrideText === 'string' ? overrideText : input;
    if (isStreaming || !userText.trim()) return;
    setInput('');
    setMessages(prev => [
      ...prev,
      { role: 'user', content: userText, id: 'temp_user' },
      { role: 'assistant', content: '', id: 'temp_gm' }
    ]);

    await streamEndpoint('/api/chat/stream', {
      campaign_id: activeCampaignId,
      user_message: userText
    }, {
      onStart: (evt) => {
        setPromptStats(evt.stats);
        setLastResolution(evt.action_resolution || null);
        if (evt.memory_warning) banner.warn('Memory store unavailable — this turn will not use past memories.');
      },
      onToken: (t) => setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + t };
        return copy;
      }),
      onDone: async (evt) => {
        setPromptStats(evt.prompt_stats);
        await refreshState(activeCampaignId);
      }
    });
  };

  const handleContinue = async () => {
    setMessages(prev => [...prev]);
    await streamEndpoint(`/api/campaign/${activeCampaignId}/continue`, null, {
      onStart: (evt) => { setPromptStats(evt.stats); setLastResolution(null); },
      onToken: (t) => setMessages(prev => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last && last.role === 'assistant') {
          copy[copy.length - 1] = { ...last, content: last.content + t };
        }
        return copy;
      }),
      onDone: async () => { await refreshState(activeCampaignId); }
    });
  };

  const handleRegenerate = async () => {
    const lastGm = [...messages].reverse().find(m => m.role === 'assistant' && m.id && !m.id.startsWith('temp'));
    if (!lastGm) return;
    if (lastGm.partial) {
      const ok = await modal.confirm({
        title: 'Discard partial response?',
        message: 'Discard the current partial response and generate a new one?',
        confirmLabel: 'Reroll',
        danger: true,
      });
      if (!ok) return;
    }
    setMessages(prev => {
      const copy = [...prev];
      copy.pop();
      copy.push({ role: 'assistant', content: '', id: 'temp_gm' });
      return copy;
    });
    await streamEndpoint(`/api/campaign/${activeCampaignId}/regenerate/${lastGm.id}`, null, {
      onStart: (evt) => {
        setPromptStats(evt.stats);
        setLastResolution(evt.action_resolution || null);
      },
      onToken: (t) => setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + t };
        return copy;
      }),
      onDone: async () => { await refreshState(activeCampaignId); }
    });
  };

  const handleDeleteMessage = async (msgId) => {
    if (!msgId || msgId.startsWith('temp')) return;
    const ok = await modal.confirm({
      title: 'Delete turn?',
      message: 'This removes the player action and GM response for this turn, reverses attributed state changes, and removes its memory entry.',
      confirmLabel: 'Delete Turn',
      danger: true
    });
    if (!ok) return;
    try {
      const res = await apiFetch(`/api/campaign/${activeCampaignId}/message/${msgId}`, { method: 'DELETE' });
      if (!res.ok) {
        banner.error('Delete failed');
        return;
      }
      await refreshState(activeCampaignId);
    } catch (e) {
      banner.error(`Delete failed: ${e.message}`);
    }
  };

  // -------------------------------------------------------- campaign lifecycle

  const loadCampaign = async (id) => {
    setActiveCampaignId(id);
    const data = await refreshState(id);
    if (!data) return;
    setAppMode('play');
    const hasAssistant = (data.messages || []).some(m => m.role === 'assistant');
    if (!hasAssistant) setTimeout(() => handleKickoff(id), 50);
  };

  const deleteCampaign = async (id, e) => {
    e.stopPropagation();
    const ok = await modal.confirm({
      title: 'Delete world?',
      message: 'This permanently removes the campaign and all its memories. Cannot be undone.',
      confirmLabel: 'Delete World',
      danger: true
    });
    if (!ok) return;
    try {
      await apiFetch(`/api/campaigns/${id}`, { method: 'DELETE' });
      if (id === activeCampaignId) {
        setCampaignState(null);
        setMessages([]);
        setPromptStats(null);
        setLastPrompt(null);
        setLastResolution(null);
        setUndoStack([]);
        setInspectorOpen(false);
        setAppMode('menu');
      }
      const res = await apiFetch('/api/campaigns');
      setSavedCampaigns(await res.json());
    } catch (err) {
      banner.error(`Delete failed: ${describeApiError(err)}`);
    }
  };

  const convertToSolo = async (id, e) => {
    e.stopPropagation();
    try {
      const res = await apiFetch(`/api/campaigns/${id}/convert_to_solo`, { method: 'POST' });
      if (!res.ok) { banner.error('Could not convert to solo'); return; }
      await loadCampaign(id);
    } catch (err) {
      banner.error(`Convert failed: ${describeApiError(err)}`);
    }
  };

  const hostCampaign = async (campaign, e) => {
    e.stopPropagation();
    try {
      const stateRes = await apiFetch(`/api/state/${campaign.id}`, {
        headers: { 'X-Player-Slot': 'host' },
      });
      if (!stateRes.ok) {
        banner.error('Could not load campaign to host.');
        return;
      }
      const state = await stateRes.json();
      if (state.multiplayer && state.multiplayer.session_status !== 'archived') {
        const roomCode = state.multiplayer.room_code;
        const serverInfo = await apiFetch('/api/server/info').then(r => r.json()).catch(() => ({}));
        setMultiplayerLaunch({
          roomCode,
          joinUrl: buildLanJoinUrl(roomCode, serverInfo.lan_ip),
          joinPayload: {
            displayName: 'Host',
            characterName: state.multiplayer.host_character?.name || state.player?.name || 'Host',
            desiredSlot: 'host',
            preferenceProfile: null,
            preferenceSource: 'none',
          },
        });
        setAppMode('multiplayer');
        return;
      }

      const createRes = await apiFetch('/api/session/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_id: campaign.id,
          host_character: {
            name: state.player?.name || 'Host',
            gender: state.player?.gender || 'Unspecified',
            location: state.player?.location || '',
            appearance: state.player?.appearance || '',
            description: state.player?.description || '',
            stats: state.player?.stats || {},
            inventory: state.player?.inventory || [],
          },
        }),
      });
      if (!createRes.ok) {
        const detail = await createRes.json().catch(() => ({ detail: createRes.statusText }));
        banner.error(`Could not host multiplayer: ${detail.detail || createRes.statusText}`);
        return;
      }
      const created = await createRes.json();
      setMultiplayerLaunch({
        roomCode: created.room_code,
        joinUrl: buildLanJoinUrl(created.room_code, created.lan_ip),
        joinPayload: {
          displayName: 'Host',
          characterName: state.player?.name || created.multiplayer?.host_character?.name || 'Host',
          desiredSlot: 'host',
          preferenceProfile: null,
          preferenceSource: 'none',
        },
      });
      setAppMode('multiplayer');
    } catch (err) {
      banner.error(`Could not host multiplayer: ${describeApiError(err)}`);
    }
  };

  const beginRename = (c, e) => {
    e.stopPropagation();
    setRenamingId(c.id);
    setRenameDraft(c.title || '');
  };

  const cancelRename = (e) => {
    if (e) e.stopPropagation();
    setRenamingId(null);
    setRenameDraft('');
  };

  const submitRename = async (id, e) => {
    if (e) e.stopPropagation();
    const title = renameDraft.trim();
    try {
      const res = await apiFetch(`/api/campaigns/${id}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
      });
      if (!res.ok) {
        banner.error('Rename failed');
        return;
      }
      const list = await apiFetch('/api/campaigns');
      setSavedCampaigns(await list.json());
      setRenamingId(null);
      setRenameDraft('');
    } catch (err) {
      banner.error(`Rename failed: ${err.message}`);
    }
  };

  const handleFork = async () => {
    try {
      const res = await apiFetch(`/api/campaigns/${activeCampaignId}/fork`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'success') {
          banner.info('Timeline forked — loading alternate campaign...');
          await loadCampaign(data.new_campaign_id);
        }
      }
    } catch (e) {
      banner.error(`Fork failed: ${describeApiError(e)}`);
    }
  };

  // -------------------------------------------------------- director-mode edits with undo

  const pushUndo = (entry) => setUndoStack(s => [...s.slice(-19), entry]);

  const pushStatePatch = async (patch, mutator, description) => {
    if (!campaignState) return;
    const before = structuredClone(campaignState);
    const next = structuredClone(campaignState);
    mutator(next);
    pushUndo({ before, description });
    setCampaignState(next);
    try {
      const res = await apiFetch(`/api/state/${activeCampaignId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: before.revision, ...patch })
      });
      if (!res.ok) {
        if (res.status === 409) {
          banner.warn('Campaign changed while editing. Refreshed the latest state.');
          await refreshState(activeCampaignId);
        } else {
          banner.error('Edit rejected by backend');
          setCampaignState(before);
        }
        return;
      }
      const data = await res.json();
      setCampaignState(data.state);
    } catch (e) {
      banner.error(`Edit failed: ${describeApiError(e)}`);
      setCampaignState(before);
    }
  };

  const handleUndo = async () => {
    if (undoStack.length === 0) return;
    const last = undoStack[undoStack.length - 1];
    setUndoStack(s => s.slice(0, -1));
    setCampaignState(last.before);
    try {
      const res = await apiFetch(`/api/state/${activeCampaignId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_revision: campaignState?.revision,
          player: {
            name: last.before.player?.name,
            location: last.before.player?.location
          },
          stats: last.before.player?.stats || {},
          inventory: last.before.player?.inventory || [],
          npcs: last.before.npcs || [],
          lorebook: last.before.lorebook || {},
          stat_bounds: last.before.stat_bounds || {}
        })
      });
      if (res.ok) {
        const data = await res.json();
        setCampaignState(data.state);
      } else {
        await refreshState(activeCampaignId);
      }
    } catch (e) {
      banner.error(`Undo failed: ${describeApiError(e)}`);
    }
  };

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && directorMode) {
        e.preventDefault();
        handleUndo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const updateStat = (name, val) => {
    if (!Object.prototype.hasOwnProperty.call(campaignState?.player?.stats || {}, name)) {
      banner.warn('Stat name is unavailable; refresh before editing stats.');
      return;
    }
    pushStatePatch({ stats: { [name]: val } }, s => { s.player.stats[name] = val; }, `Edit ${name}`);
  };
  const updateLocation = (loc) => pushStatePatch({ player: { location: loc } }, s => { s.player.location = loc; }, 'Edit location');
  const updatePlayerField = (field, val) => pushStatePatch({ player: { [field]: val } }, s => { s.player[field] = val; }, `Edit ${field}`);
  const addInventory = (item) => {
    if (!item.trim()) return;
    const inventory = [...(campaignState.player?.inventory || []), item.trim()];
    pushStatePatch({ inventory }, s => { s.player.inventory = inventory; }, 'Add item');
  };
  const removeInventory = (item) => {
    const inventory = (campaignState.player?.inventory || []).filter(i => i !== item);
    pushStatePatch({ inventory }, s => { s.player.inventory = inventory; }, 'Remove item');
  };
  const updateNpc = (idx, patch) => {
    const npcs = [...(campaignState.npcs || [])];
    npcs[idx] = { ...npcs[idx], ...patch };
    pushStatePatch({ npcs }, s => { s.npcs = npcs; }, 'Edit NPC');
  };
  const removeNpc = (idx) => {
    const npcs = (campaignState.npcs || []).filter((_, i) => i !== idx);
    pushStatePatch({ npcs }, s => { s.npcs = npcs; }, 'Remove NPC');
  };
  const addNpc = (n) => {
    const npcs = [...(campaignState.npcs || []), n];
    pushStatePatch({ npcs }, s => { s.npcs = npcs; }, 'Add NPC');
  };
  const updateLore = (key, rule) => {
    const lorebook = { ...(campaignState.lorebook || {}), [key]: rule };
    pushStatePatch({ lorebook }, s => { s.lorebook = lorebook; }, 'Edit lore');
  };
  const removeLore = (key) => {
    const lorebook = { ...(campaignState.lorebook || {}) };
    delete lorebook[key];
    pushStatePatch({ lorebook }, s => { s.lorebook = lorebook; }, 'Remove lore');
  };
  const addLore = () => {
    const key = newLoreKey.trim();
    if (!key) return;
    const lorebook = { ...(campaignState.lorebook || {}), [key]: newLoreRule.trim() };
    pushStatePatch({ lorebook }, s => { s.lorebook = lorebook; }, 'Add lore');
    setNewLoreKey('');
    setNewLoreRule('');
  };

  // -------------------------------------------------------- export / import

  const handleExport = async () => {
    try {
      const res = await apiFetch(`/api/campaign/${activeCampaignId}/export`);
      if (!res.ok) { banner.error('Export failed'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeCampaignId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      banner.error(`Export failed: ${describeApiError(e)}`);
    }
  };

  const handleDebugExport = async () => {
    try {
      const res = await apiFetch(`/api/campaign/${activeCampaignId}/debug`);
      if (!res.ok) { banner.error('Debug export failed'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeCampaignId}.debug.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      banner.error(`Debug export failed: ${describeApiError(e)}`);
    }
  };

  const handleImport = async (file) => {
    try {
      const text = await file.text();
      const payload = JSON.parse(text);
      const res = await apiFetch('/api/campaign/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: payload.state, memories: payload.memories })
      });
      if (!res.ok) { banner.error('Import failed'); return; }
      const { campaign_id } = await res.json();
      banner.info(`Imported campaign ${campaign_id}`);
      const list = await apiFetch('/api/campaigns');
      setSavedCampaigns(await list.json());
    } catch (e) {
      banner.error(`Import failed: ${describeApiError(e)}`);
    }
  };

  const toggleQuickActions = () => {
    const next = !showQuickActions;
    setShowQuickActions(next);
    if (!next) setQuickActionForm(null);
    try {
      if (next) window.localStorage?.removeItem('tt_quick_actions');
      else window.localStorage?.setItem('tt_quick_actions', 'false');
    } catch { /* storage unavailable */ }
  };

  const handleQuickActionClick = (action) => {
    const placeholders = extractPlaceholders(action.text);
    if (placeholders.length === 0) {
      setInput(action.text);
      setQuickActionForm(null);
      return;
    }
    setQuickActionForm({ ...action, placeholders });
    setQuickActionValues(Object.fromEntries(placeholders.map(placeholder => [placeholder, ''])));
  };

  const insertQuickAction = () => {
    if (!quickActionForm) return;
    const filled = quickActionForm.text.replace(/\[([^\]]+)\]/g, (match, placeholder) => {
      const value = quickActionValues[placeholder]?.trim();
      return value || match;
    });
    setInput(filled);
    setQuickActionForm(null);
  };

  const openHelp = () => {
    setHelpManagesLaunchPreference(false);
    setHelpOpen(true);
  };

  const closeHelp = () => {
    setHelpOpen(false);
    setHelpManagesLaunchPreference(false);
  };

  // -------------------------------------------------------- inspector

  const openInspector = async () => {
    try {
      const res = await apiFetch(`/api/campaign/${activeCampaignId}/last_prompt`);
      if (res.ok) {
        const data = await res.json();
        if (data.available) {
          setLastPrompt(data);
          setInspectorOpen(true);
        } else {
          banner.info('No prompt available yet — send a turn first.');
        }
      }
    } catch (e) { banner.error(`Inspector failed: ${describeApiError(e)}`); }
  };

  // -------------------------------------------------------- render

  if (appMode === 'menu') {
    return (
      <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-serif flex flex-col items-center justify-center p-8">
        <h1 className="text-6xl text-fantasy-accent drop-shadow-md mb-12 border-b border-slate-700 pb-4">Tavern Tales Reborn</h1>
        <div className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl shadow-lg backdrop-blur p-8 w-full max-w-2xl text-center relative">
          <button
            onClick={openHelp}
            title="Help & Documentation"
            aria-label="Help & Documentation"
            className="absolute top-4 right-4 text-xs text-slate-400 hover:text-amber-400 border border-slate-600 hover:border-amber-600 rounded-full w-7 h-7 flex items-center justify-center transition font-sans font-bold"
          >?</button>
          <button
            onClick={openHelp}
            className="absolute top-5 right-14 text-xs text-slate-400 hover:text-amber-400 underline-offset-4 hover:underline font-sans"
          >
            What is this?
          </button>

          <button
            onClick={() => { setPendingFantasyDraft(null); setMultiplayerLaunch(null); setActiveCampaignId(createCampaignId()); setAppMode('setup'); }}
            className="bg-indigo-700 hover:bg-indigo-600 text-white w-full py-4 rounded-lg font-sans font-bold tracking-widest text-lg uppercase transition shadow-md mb-4"
          >+ Forge New World</button>

          <button
            onClick={() => setAppMode('profiles')}
            className="bg-slate-800 hover:bg-slate-700 text-amber-400 border border-slate-600 w-full py-3 rounded-lg font-sans font-bold tracking-widest text-sm uppercase transition shadow-md mb-2"
          >Preference Profiles</button>

          <button
            onClick={() => setAppMode('fantasy-creator')}
            className="bg-slate-800 hover:bg-slate-700 text-pink-300 border border-slate-600 w-full py-3 rounded-lg font-sans font-bold tracking-widest text-sm uppercase transition shadow-md mb-2"
          >Fantasy Creator (Couples)</button>

          <button
            onClick={() => { setMultiplayerLaunch(null); setAppMode('multiplayer'); }}
            className="bg-slate-800 hover:bg-slate-700 text-emerald-300 border border-slate-600 w-full py-3 rounded-lg font-sans font-bold tracking-widest text-sm uppercase transition shadow-md mb-2"
          >Join Multiplayer Session</button>
          {pendingFantasyDraft && (
            <p className="text-xs text-amber-400 italic mb-4">Campaign seeded from: {pendingFantasyDraft.title || 'a saved fantasy draft'}</p>
          )}
          {!pendingFantasyDraft && <div className="mb-4" />}

          {savedCampaigns.length === 0 && preferenceProfiles?.length === 0 && (
            <div className="mb-6 bg-indigo-950/30 border border-indigo-700/40 rounded-lg p-3 text-sm text-indigo-100 font-sans">
              <span>Tip: Preference Profiles let you guide the story&apos;s tone and themes.</span>
              <button
                onClick={() => setAppMode('profiles')}
                className="ml-2 text-amber-300 hover:text-amber-200 font-bold underline-offset-4 hover:underline"
              >
                Get Started →
              </button>
            </div>
          )}

          <label className="block mb-8">
            <span className="text-xs uppercase tracking-widest text-slate-400 font-sans">Import Campaign (.json)</span>
            <input
              type="file"
              accept="application/json"
              onChange={(e) => e.target.files?.[0] && handleImport(e.target.files[0])}
              className="block mt-2 w-full text-xs text-slate-300 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200 hover:file:bg-slate-600"
            />
          </label>

          {lastRoomCard && (
            <div className="mb-4 flex items-center gap-3 bg-emerald-950/30 border border-emerald-700/50 rounded-lg px-4 py-3 text-sm font-sans">
              <div className="flex-1 min-w-0">
                <span className="text-emerald-300 font-bold">Rejoin Last Session</span>
                <span className="text-slate-400 ml-2">Room: <span className="font-mono text-slate-200">{lastRoomCard.roomCode}</span></span>
                {lastRoomCard.characterName && <span className="text-slate-400 ml-2">as <span className="text-slate-200">{lastRoomCard.characterName}</span></span>}
              </div>
              <button
                onClick={() => {
                  setMultiplayerLaunch({
                    roomCode: lastRoomCard.roomCode,
                    joinUrl: '',
                    joinPayload: {
                      displayName: lastRoomCard.displayName || lastRoomCard.characterName,
                      characterName: lastRoomCard.characterName,
                      desiredSlot: 'guest',
                      preferenceProfile: null,
                      preferenceSource: 'none',
                    },
                  });
                  setAppMode('multiplayer');
                }}
                className="bg-emerald-700 hover:bg-emerald-600 text-white px-4 py-1.5 rounded font-bold text-xs transition"
              >Rejoin</button>
              <button
                onClick={() => {
                  try { window.localStorage?.removeItem('tt_last_room'); } catch { /* ok */ }
                  setLastRoomCard(null);
                }}
                className="text-slate-500 hover:text-slate-300 text-lg leading-none ml-1"
                title="Dismiss"
                aria-label="Dismiss rejoin card"
              >×</button>
            </div>
          )}

          <h3 className="text-sm uppercase text-slate-400 font-sans tracking-widest mb-4">Or Continue Journey</h3>
          {savedCampaigns.length === 0 && <p className="text-slate-500 italic text-sm">No saved campaigns found.</p>}
          <div className="flex flex-col gap-3">
            {savedCampaigns.map(c => (
              <div key={c.id} className="flex gap-2">
                {renamingId === c.id ? (
                  <div className="flex-1 flex gap-2 bg-fantasy-dark/50 border border-fantasy-accent/60 rounded p-2">
                    <input
                      autoFocus
                      type="text"
                      value={renameDraft}
                      maxLength={120}
                      placeholder={`${c.player}'s Tale`}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setRenameDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') { e.preventDefault(); submitRename(c.id, e); }
                        if (e.key === 'Escape') { e.preventDefault(); cancelRename(e); }
                      }}
                      className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-amber-100 text-sm focus:outline-none focus:border-fantasy-accent"
                    />
                    <button onClick={(e) => submitRename(c.id, e)} className="bg-fantasy-accent hover:bg-amber-600 text-white px-3 rounded text-sm font-bold transition">Save</button>
                    <button onClick={cancelRename} className="bg-slate-700 hover:bg-slate-600 text-slate-200 px-3 rounded text-sm transition">Cancel</button>
                  </div>
                ) : (
                  <button onClick={() => loadCampaign(c.id)} className="flex-1 bg-fantasy-dark/50 hover:bg-slate-700 border border-slate-600 rounded p-4 text-left font-sans flex justify-between items-center transition">
                    <span className="text-amber-500 font-bold">{c.title?.trim() || `${c.player}'s Tale`}</span>
                    <span className="text-xs text-slate-500" title={c.id}>
                      {formatDate(c.created_at)}
                    </span>
                  </button>
                )}
                {renamingId !== c.id && (
                  <>
                    <button onClick={(e) => beginRename(c, e)} aria-label={`Rename ${c.title || c.player + "'s Tale"}`} className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 rounded px-4 font-sans font-bold transition" title="Rename World">✎</button>
                    {c.has_archived_multiplayer ? (
                      <button onClick={(e) => convertToSolo(c.id, e)} className="bg-indigo-900/40 hover:bg-indigo-800 text-indigo-200 border border-indigo-800/50 rounded px-3 font-sans font-bold transition text-xs" title="Continue this story in single-player mode">Continue Solo</button>
                    ) : (
                      <button onClick={(e) => hostCampaign(c, e)} className="bg-emerald-900/40 hover:bg-emerald-800 text-emerald-200 border border-emerald-800/50 rounded px-4 font-sans font-bold transition" title="Host Multiplayer">Host</button>
                    )}
                    <button onClick={(e) => deleteCampaign(c.id, e)} aria-label={`Delete ${c.title || c.player + "'s Tale"}`} className="bg-red-900/40 hover:bg-red-800 text-red-200 border border-red-900/50 rounded px-4 font-sans font-bold transition" title="Delete World">✗</button>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
        {helpOpen && <HelpModal onClose={closeHelp} manageLaunchPreference={helpManagesLaunchPreference} />}
      </div>
    );
  }

  if (appMode === 'setup') {
    return <CampaignCreator
      campaignId={activeCampaignId}
      initialFantasyDraft={pendingFantasyDraft}
      onComplete={async (result) => {
        setPendingFantasyDraft(null);
        if (result?.mode === 'multiplayer') {
          setMultiplayerLaunch({
            roomCode: result.roomCode,
            joinUrl: result.joinUrl || buildLanJoinUrl(result.roomCode, result.lanIp),
            joinPayload: {
              displayName: 'Host',
              characterName: result.hostCharacterName || 'Host',
              desiredSlot: 'host',
              preferenceProfile: null,
              preferenceSource: 'none',
            },
          });
          setAppMode('multiplayer');
          return;
        }
        await loadCampaign(activeCampaignId);
      }}
    />;
  }

  if (appMode === 'profiles') {
    return <PreferenceProfiles
      onBack={() => setAppMode('menu')}
      onCreateCampaignFromDraft={(draft) => {
        setPendingFantasyDraft(draft);
        setMultiplayerLaunch(null);
        setActiveCampaignId(createCampaignId());
        setAppMode('setup');
      }}
    />;
  }

  if (appMode === 'fantasy-creator') {
    return <FantasyCreator onBack={() => setAppMode('menu')} />;
  }

  if (appMode === 'multiplayer') {
    return <MultiplayerEntry
      initialRoomCode={multiplayerLaunch?.roomCode || ''}
      initialJoinUrl={multiplayerLaunch?.joinUrl || ''}
      initialJoinPayload={multiplayerLaunch?.joinPayload || null}
      autoLaunch={Boolean(multiplayerLaunch?.roomCode && multiplayerLaunch?.joinPayload)}
      banner={banner}
      onBack={() => { setMultiplayerLaunch(null); setAppMode('menu'); }}
    />;
  }

  const ctx = promptStats?.model_context_window ? Math.round((promptStats.total_used / promptStats.model_context_window) * 100) : 0;
  const lastGmMsg = [...messages].reverse().find(m => m.role === 'assistant');
  const canContinue = !isStreaming && lastGmMsg && (lastGmMsg.partial || !/[.!?…"'”’)\]]+$/.test((lastGmMsg.content || '').trim()));

  return (
    <div className="h-screen overflow-hidden flex text-fantasy-text bg-fantasy-dark">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-20 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      {/* Sidebar — left drawer on md+, bottom sheet on mobile */}
      <aside className={`
        ${sidebarOpen
          ? 'fixed inset-x-0 bottom-0 z-30 flex max-h-[80vh] flex-col rounded-t-2xl md:rounded-none md:inset-y-0 md:left-0 md:right-auto md:max-h-none md:h-screen'
          : 'hidden'}
        md:relative md:inset-auto md:z-auto md:flex md:flex-col md:h-screen
        w-full md:w-72 bg-fantasy-panel border-t md:border-t-0 border-r border-slate-700/50 p-4 gap-6 overflow-y-auto
        transition-transform
      `}>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-2xl font-serif text-fantasy-accent font-bold">Tavern Tales Reborn</h2>
          <button className="md:hidden text-xs border text-slate-300 border-slate-700 py-1 px-2 rounded" onClick={() => setSidebarOpen(false)}>Close</button>
        </div>
        <div className="flex gap-2">
          <button className="text-xs border text-slate-400 border-slate-700 py-1 px-2 rounded hover:bg-slate-700 flex-1" onClick={() => setAppMode('menu')}>Menu</button>
          <button className="text-xs border text-slate-400 border-slate-700 py-1 px-2 rounded hover:bg-slate-700 flex-1" onClick={handleExport}>Export</button>
        </div>

        {campaignState && (
          <>
            {campaignState.preference_context?.enabled && (
              <button
                onClick={() => setProfilesOpen(true)}
                className="bg-emerald-950/20 border border-emerald-800/60 rounded p-3 text-xs text-emerald-100 text-left w-full hover:bg-emerald-950/40 transition"
                title="View or edit your preference profiles"
              >
                <h3 className="uppercase text-emerald-300 font-bold tracking-widest mb-1 flex items-center gap-1">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  Preference Context — active
                </h3>
                <div className="text-emerald-200 font-semibold">{campaignState.preference_context.draft_title || 'Saved preference snapshot'}</div>
                <div className="text-emerald-300/70 mt-1">
                  Profile {campaignState.preference_context.profile_version ? `v${campaignState.preference_context.profile_version}` : 'snapshot'}
                  {campaignState.preference_context.draft_id ? ` / ${campaignState.preference_context.draft_id}` : ''}
                </div>
                <div className="mt-2 text-emerald-200/80">{campaignState.preference_context.safety_principle}</div>
              </button>
            )}

            <div>
              <h3 className="text-xs uppercase text-fantasy-dim font-bold tracking-widest mb-3 border-b border-slate-700 pb-1">
                Protagonist {directorMode && <span className="text-amber-500 lowercase opacity-80">(edit mode)</span>}
              </h3>
              <div className="bg-fantasy-dark/40 rounded border border-slate-700/50 p-3 text-sm flex flex-col gap-2 shadow-inner min-h-[100px]">
                {campaignState.player?.stats && Object.entries(campaignState.player.stats).map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center">
                    <span className="text-slate-400">{k}:</span>
                    {directorMode ? (
                      <input type="number" className="w-20 bg-slate-800 text-amber-500 font-bold p-1 border border-slate-600 rounded text-right" value={v} onChange={(e) => updateStat(k, parseInt(e.target.value) || 0)} />
                    ) : (
                      <span className="text-amber-500 font-bold">{v}</span>
                    )}
                  </div>
                ))}
                <div className="mt-2 pt-2 border-t border-slate-700/50">
                  <span className="text-slate-400 block text-xs mb-1">Location:</span>
                  {directorMode ? (
                    <input type="text" className="w-full bg-slate-800 text-slate-200 italic p-1 border border-slate-600 rounded text-xs" value={campaignState.player?.location || ''} onChange={(e) => updateLocation(e.target.value)} />
                  ) : (
                    <span className="text-slate-200 italic">{campaignState.player?.location || 'Unknown'}</span>
                  )}
                </div>
                {(directorMode || (campaignState.player?.gender && campaignState.player.gender !== 'Unspecified')) && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50">
                    <span className="text-slate-400 block text-xs mb-1">Gender:</span>
                    {directorMode ? (
                      <select className="w-full bg-slate-800 text-slate-200 p-1 border border-slate-600 rounded text-xs" value={campaignState.player?.gender || 'Unspecified'} onChange={(e) => updatePlayerField('gender', e.target.value)}>
                        <option value="Unspecified">Unspecified</option>
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                        <option value="NB">Non-binary</option>
                      </select>
                    ) : (
                      <span className="text-slate-200">{campaignState.player?.gender}</span>
                    )}
                  </div>
                )}
                {(directorMode || campaignState.player?.appearance) && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50">
                    <span className="text-slate-400 block text-xs mb-1">Appearance:</span>
                    {directorMode ? (
                      <textarea className="w-full bg-slate-800 text-slate-200 p-1 border border-slate-600 rounded text-xs" rows={2} value={campaignState.player?.appearance || ''} onChange={(e) => updatePlayerField('appearance', e.target.value)} />
                    ) : (
                      <span className="text-slate-200 italic">{campaignState.player?.appearance}</span>
                    )}
                  </div>
                )}
                {(directorMode || campaignState.player?.description) && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50">
                    <span className="text-slate-400 block text-xs mb-1">Details:</span>
                    {directorMode ? (
                      <textarea className="w-full bg-slate-800 text-slate-200 p-1 border border-slate-600 rounded text-xs" rows={2} value={campaignState.player?.description || ''} onChange={(e) => updatePlayerField('description', e.target.value)} />
                    ) : (
                      <span className="text-slate-200 italic">{campaignState.player?.description}</span>
                    )}
                  </div>
                )}
                {(campaignState.player?.inventory?.length > 0 || directorMode) && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50">
                    <span className="text-slate-400 block text-xs mb-1">Inventory:</span>
                    <div className="flex flex-wrap gap-1">
                      {campaignState.player?.inventory?.map((item, idx) => (
                        <span key={idx} className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-300 flex items-center gap-1">
                          {item}
                          {directorMode && <button onClick={() => removeInventory(item)} aria-label={`Remove ${item} from inventory`} className="text-red-400 hover:text-red-300 ml-1">×</button>}
                        </span>
                      ))}
                    </div>
                    {directorMode && (
                      <input type="text" placeholder="Add Item... (Enter)" className="mt-2 w-full bg-slate-800 text-slate-200 border border-slate-600 rounded px-1.5 py-1 text-xs focus:outline-none focus:border-fantasy-accent" onKeyDown={(e) => { if (e.key === 'Enter') { addInventory(e.target.value); e.target.value = ''; } }} />
                    )}
                  </div>
                )}
              </div>
            </div>

            <div>
              <h3 className="text-xs uppercase text-fantasy-dim font-bold tracking-widest mb-3 border-b border-slate-700 pb-1">The Cast</h3>
              {(campaignState.npcs || []).length === 0 ? (
                <div className="text-xs text-slate-500 italic p-2">No characters encountered yet.</div>
              ) : (
                <div className="flex flex-col gap-3">
                  {campaignState.npcs.map((npc, idx) => (
                    <div key={idx} className="bg-fantasy-dark/40 rounded border border-slate-700/50 p-3 text-sm">
                      {directorMode ? (
                        <>
                          <input className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm w-full mb-1 text-fantasy-accent font-bold" value={npc.name} onChange={e => updateNpc(idx, { name: e.target.value })} />
                          <div className="grid grid-cols-2 gap-1 mb-1">
                            <select className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-300" value={npc.disposition} onChange={e => updateNpc(idx, { disposition: e.target.value })}>
                              <option>Friendly</option><option>Neutral</option><option>Suspicious</option><option>Hostile</option>
                            </select>
                            <select className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-300" value={npc.gender || 'Unspecified'} onChange={e => updateNpc(idx, { gender: e.target.value })}>
                              <option value="Unspecified">Unspecified</option>
                              <option value="M">Male</option>
                              <option value="F">Female</option>
                              <option value="NB">Non-binary</option>
                            </select>
                          </div>
                          <textarea placeholder="Appearance" className="w-full bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 text-xs mb-1" rows={2} value={npc.appearance || ''} onChange={e => updateNpc(idx, { appearance: e.target.value })} />
                          <textarea placeholder="Details" className="w-full bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 text-xs mb-1" rows={2} value={npc.description || ''} onChange={e => updateNpc(idx, { description: e.target.value })} />
                          <button className="text-xs text-red-400 hover:text-red-300" onClick={() => removeNpc(idx)}>Remove NPC</button>
                        </>
                      ) : (
                        <>
                          <div className="font-serif text-fantasy-accent font-bold text-base border-b border-slate-700 pb-1 mb-2">{npc.name}</div>
                          <div className="text-xs text-slate-400 mb-1">
                            Disposition: <span className="ml-1 text-slate-200">{npc.disposition}</span>
                            {npc.gender && npc.gender !== 'Unspecified' && (
                              <span className="ml-2">· <span className="text-slate-200">{npc.gender}</span></span>
                            )}
                          </div>
                          {npc.appearance && (
                            <div className="text-xs text-slate-400 mt-1"><span className="text-slate-500 uppercase tracking-wider">Appearance:</span> <span className="text-slate-200 italic">{npc.appearance}</span></div>
                          )}
                          {npc.description && (
                            <div className="text-xs text-slate-400 mt-1"><span className="text-slate-500 uppercase tracking-wider">Details:</span> <span className="text-slate-200 italic">{npc.description}</span></div>
                          )}
                        </>
                      )}
                      {npc.secrets_known && npc.secrets_known.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-700/50">
                          <span className="text-xs text-amber-600 font-bold mb-1 block">Secrets / Notes</span>
                          <ul className="list-disc pl-4 text-xs text-slate-300 italic">
                            {npc.secrets_known.map((s, i) => <li key={i}>{s}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {directorMode && (
                <button className="mt-2 text-xs text-amber-400 hover:text-amber-300 border border-slate-600 rounded px-2 py-1 w-full" onClick={() => addNpc({ name: 'New NPC', disposition: 'Neutral', secrets_known: [] })}>+ Add NPC</button>
              )}
            </div>

            <div>
              <h3 className="text-xs uppercase text-fantasy-dim font-bold tracking-widest mb-3 border-b border-slate-700 pb-1">Lorebook</h3>
              {Object.entries(campaignState.lorebook || {}).length === 0 ? (
                <div className="text-xs text-slate-500 italic p-2">No lore entries.</div>
              ) : (
                <div className="flex flex-col gap-2">
                  {Object.entries(campaignState.lorebook).map(([k, v]) => (
                    <div key={k} className="bg-fantasy-dark/40 rounded border border-slate-700/50 p-2 text-xs">
                      {directorMode ? (
                        <>
                          <div className="flex gap-1 items-center mb-1">
                            <span className="text-amber-500 font-bold bg-slate-800 px-1.5 rounded">{k}</span>
                            <button onClick={() => removeLore(k)} aria-label={`Remove lorebook entry: ${k}`} className="text-red-400 hover:text-red-300 ml-auto">×</button>
                          </div>
                          <textarea className="w-full bg-slate-800 border border-slate-600 rounded p-1 text-xs text-slate-200" rows={2} value={v} onChange={e => updateLore(k, e.target.value)} />
                        </>
                      ) : (
                        <><span className="text-amber-500 font-bold">[{k}]</span> <span className="text-slate-300">{v}</span></>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {directorMode && (
                <div className="mt-3 bg-fantasy-dark/30 border border-dashed border-slate-600 rounded p-2 flex flex-col gap-2">
                  <input
                    type="text"
                    placeholder="New lore key"
                    className="w-full bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-fantasy-accent"
                    value={newLoreKey}
                    onChange={e => setNewLoreKey(e.target.value)}
                  />
                  <textarea
                    placeholder="Rule or note"
                    className="w-full bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-fantasy-accent"
                    rows={2}
                    value={newLoreRule}
                    onChange={e => setNewLoreRule(e.target.value)}
                  />
                  <button className="text-xs text-amber-400 hover:text-amber-300 border border-slate-600 rounded px-2 py-1" onClick={addLore}>+ Add Lore</button>
                </div>
              )}
            </div>
          </>
        )}
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col h-screen relative">
        <header className="p-4 border-b border-slate-700/50 flex justify-between items-center bg-fantasy-panel/90 backdrop-blur sticky top-0 z-10 shadow-sm flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <h1 className="font-serif text-xl text-fantasy-accent drop-shadow-sm">The Story</h1>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {promptStats && (
              <div
                title={`AI memory usage — green: plenty of room, amber: getting full, red: near limit. ${ctx}% full — ${promptStats.total_used.toLocaleString()} / ${promptStats.model_context_window.toLocaleString()} tokens`}
                role="progressbar"
                aria-valuenow={ctx}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="AI memory usage"
                className="flex items-center gap-2 text-xs text-slate-400 border-r border-slate-600 pr-3"
              >
                <div className="w-24 h-1.5 bg-slate-700 rounded overflow-hidden">
                  <div className={`h-full ${ctx > 85 ? 'bg-red-500' : ctx > 65 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(ctx, 100)}%` }} />
                </div>
                <span className={`font-mono ${ctx > 85 ? 'text-red-400' : ctx > 65 ? 'text-amber-400' : ''}`}>{ctx}% full</span>
              </div>
            )}
            <button onClick={openInspector} title="View the full system prompt sent to the AI this turn" className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded">Inspect Prompt</button>
            {directorMode && (
              <>
                <button onClick={handleDebugExport} title="Export a JSON snapshot of campaign state and memories" className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded">Debug Bundle</button>
                <button onClick={handleUndo} disabled={undoStack.length === 0} title="Remove the last director edit and revert all side effects (Ctrl+Z)" className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded disabled:opacity-40">Undo ({undoStack.length})</button>
                <button onClick={handleFork} title="Branch the story at this moment and start an alternate path" className="text-xs px-3 py-1 bg-amber-600/30 hover:bg-amber-600/50 text-amber-400 border border-amber-600/50 rounded">Branch Story</button>
              </>
            )}
            <button
              onClick={() => setDirectorMode(!directorMode)}
              title={directorMode ? 'Exit the editor and return to normal play' : 'Open the editor to change NPCs, stats, and world details mid-story'}
              className={`text-sm px-4 py-1.5 rounded transition shadow-sm font-semibold border ${directorMode ? 'bg-amber-600/20 text-amber-500 border-amber-600/50' : 'bg-fantasy-dark text-slate-300 border-slate-600 hover:bg-slate-700'}`}
            >
              <span className="flex flex-col items-center leading-tight">
                <span>{directorMode ? 'Exit Director Mode' : 'Director Mode'}</span>
                <span className="text-xs text-slate-500 font-normal">edit world state</span>
              </span>
            </button>
            <button
              onClick={openHelp}
              title="Help & Documentation"
              aria-label="Help & Documentation"
              className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded font-bold"
            >?</button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 md:p-8 flex flex-col gap-6 scroll-smooth" aria-live="polite" aria-atomic="false">
          {messages.map((m, idx) => {
            const nextMessage = messages[idx + 1];
            const showRollAfterUser = Boolean(
              lastResolution &&
              m.role === 'user' &&
              nextMessage?.role === 'assistant' &&
              lastGmMsg &&
              nextMessage.id === lastGmMsg.id
            );
            return (
              <Fragment key={m.id || idx}>
                <div className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} group relative`}>
                  {directorMode && m.id && !m.id.startsWith('temp') && (
                    <div className="absolute top-[-10px] right-2 bg-fantasy-panel border border-slate-600 rounded flex gap-1 p-1 opacity-0 group-hover:opacity-100 transition shadow-lg z-20">
                      <button onClick={() => handleDeleteMessage(m.id)} className="text-red-400 hover:bg-slate-700 px-2 py-0.5 rounded text-xs">Delete</button>
                    </div>
                  )}
                  <div className={`max-w-[85%] rounded-xl p-6 font-serif text-[1.1rem] leading-relaxed shadow-md whitespace-pre-wrap ${
                    m.role === 'user'
                      ? 'bg-gradient-to-br from-fantasy-accent/20 to-fantasy-accent/10 border border-fantasy-accent/30 text-amber-50 rounded-br-sm'
                      : 'bg-fantasy-panel border border-slate-700/50 text-slate-200 rounded-bl-sm drop-shadow-lg'
                  }`}>
                    {m.content}
                    {m.partial && <span className="ml-2 text-xs text-amber-600 italic">(partial)</span>}
                  </div>
                </div>
                {showRollAfterUser && (
                  <div className="flex justify-start -mt-3">
                    <RollResultBadge resolution={lastResolution} />
                  </div>
                )}
              </Fragment>
            );
          })}
          {isStreaming && <div className="text-sm text-amber-600/70 italic animate-pulse font-serif px-2">The storyteller is weaving the thread...</div>}
          {!isStreaming && lastGmMsg && lastGmMsg.id && !lastGmMsg.id.startsWith('temp') && (
            <div className="flex gap-2 text-xs">
              <button onClick={handleRegenerate} title="Discard the GM's last response and generate a new one" className="bg-slate-800 text-amber-400 border border-slate-600 hover:bg-slate-700 px-3 py-1 rounded-full shadow-md font-bold">↻ Reroll</button>
              {canContinue && (
                <button onClick={handleContinue} title="Ask the GM to keep writing without a new player action" className="bg-slate-800 text-emerald-400 border border-slate-600 hover:bg-slate-700 px-3 py-1 rounded-full shadow-md font-bold">→ Continue</button>
              )}
            </div>
          )}
          <div ref={scrollAnchorRef} aria-hidden="true" />
        </div>

        <div className="p-4 bg-fantasy-panel border-t border-slate-700/50 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)] sticky bottom-0 z-10">
          <div className="max-w-4xl mx-auto mb-2" ref={quickActionContainerRef}>
            <button
              onClick={toggleQuickActions}
              title="Toggle action shortcut buttons"
              className="text-xs text-slate-400 hover:text-amber-400 border border-slate-700 hover:border-amber-700 rounded px-2 py-1 transition font-sans"
            >⚡ Actions {showQuickActions ? '▾' : '▸'}</button>
            {showQuickActions && (
              <div className="flex flex-wrap gap-2 mt-2">
                {QUICK_ACTIONS.map(a => (
                  <button
                    key={a.label}
                    onClick={() => handleQuickActionClick(a)}
                    disabled={isStreaming}
                    title={`Pre-fill: "${a.text}"`}
                    className="text-xs bg-slate-800 border border-slate-600 hover:bg-slate-700 hover:border-fantasy-accent text-slate-300 px-3 py-1.5 rounded transition disabled:opacity-40"
                  >{a.label}</button>
                ))}
              </div>
            )}
            {quickActionForm && (
              <div className="mt-3 bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl font-sans">
                <div className="text-xs uppercase tracking-widest text-slate-500 mb-2">{quickActionForm.label.replace(/^[^\s]+\s*/, '')}</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {quickActionForm.placeholders.map(placeholder => (
                    <label key={placeholder} className="text-xs text-slate-400">
                      <span className="block mb-1 capitalize">{placeholder}</span>
                      <input
                        value={quickActionValues[placeholder] || ''}
                        onChange={(e) => setQuickActionValues(v => ({ ...v, [placeholder]: e.target.value }))}
                        className="w-full bg-fantasy-dark border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
                        autoFocus={placeholder === quickActionForm.placeholders[0]}
                      />
                    </label>
                  ))}
                </div>
                <div className="flex justify-end gap-2 mt-3">
                  <button
                    type="button"
                    onClick={() => setQuickActionForm(null)}
                    className="text-xs px-3 py-1 rounded border border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={insertQuickAction}
                    className="text-xs px-3 py-1 rounded bg-fantasy-accent hover:bg-amber-600 text-white font-bold"
                  >
                    Insert
                  </button>
                </div>
              </div>
            )}
            <button
              type="button"
              onClick={() => handleSend('I observe and wait, taking no action this turn.')}
              disabled={isStreaming}
              className="mt-2 text-xs text-slate-400 border border-slate-700 hover:border-slate-500 hover:text-slate-200 rounded px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Pass Turn
            </button>
          </div>
          <div className="max-w-4xl mx-auto flex gap-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onInput={e => resizeTextarea(e.currentTarget)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={isStreaming}
              placeholder="Describe your next action..."
              style={{ height: '58px', overflow: 'hidden' }}
              className="flex-1 min-h-[58px] max-h-40 overflow-hidden resize-none bg-fantasy-dark border border-slate-600 rounded-lg px-5 py-4 focus:outline-none focus:border-fantasy-accent text-fantasy-text focus:ring-2 focus:ring-fantasy-accent/50 transition shadow-inner placeholder:text-slate-500 font-serif text-lg"
            />
            {isStreaming ? (
              <button
                onClick={handleStop}
                className="bg-red-800 hover:bg-red-700 text-white px-8 py-4 rounded-lg font-bold tracking-wide transition shadow-md uppercase text-sm"
              >Stop</button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="bg-gradient-to-b from-fantasy-accent to-amber-700 hover:from-amber-600 hover:to-amber-800 text-white px-8 py-4 rounded-lg font-bold tracking-wide transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed uppercase text-sm"
              >Send</button>
            )}
          </div>
        </div>
      </main>

      {/* Mobile FAB for sidebar — hidden on md+ since sidebar is always visible.
          Positioned on the left to avoid overlapping the Send button on the right. */}
      <button
        className="md:hidden fixed bottom-28 left-4 z-20 bg-fantasy-accent hover:bg-amber-700 text-white rounded-full w-12 h-12 shadow-lg flex items-center justify-center text-xl font-bold"
        onClick={() => setSidebarOpen(true)}
        aria-label="Open character state panel"
      >☰</button>

      {helpOpen && <HelpModal onClose={closeHelp} manageLaunchPreference={helpManagesLaunchPreference} />}

      {profilesOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm" onClick={() => setProfilesOpen(false)}>
          <div className="h-full overflow-y-auto" onClick={e => e.stopPropagation()}>
            <PreferenceProfiles onBack={() => setProfilesOpen(false)} />
          </div>
        </div>
      )}

      {/* Prompt inspector modal */}
      {inspectorOpen && lastPrompt && (
        <div className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setInspectorOpen(false)}>
          <div className="bg-fantasy-panel border border-slate-600 rounded-lg shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-slate-700 flex justify-between items-center">
              <h2 className="font-serif text-lg text-fantasy-accent">Last Prompt (Inspector)</h2>
              <button onClick={() => setInspectorOpen(false)} aria-label="Close prompt inspector" className="text-slate-400 hover:text-slate-200">✗</button>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              <div className="mb-3 text-xs text-slate-400 font-mono">
                Tokens: {lastPrompt.stats?.system_tokens} system + {lastPrompt.stats?.history_tokens} history + {lastPrompt.stats?.response_budget} reserved = <span className="text-amber-400">{lastPrompt.stats?.total_used}</span> / {lastPrompt.stats?.model_context_window}
              </div>
              <pre className="whitespace-pre-wrap text-xs text-slate-300 bg-fantasy-dark border border-slate-700 rounded p-3 font-mono">{lastPrompt.system_prompt}</pre>
              {lastPrompt.memories && lastPrompt.memories.length > 0 && (
                <details className="mt-3">
                  <summary className="text-xs text-amber-500 cursor-pointer">Retrieved memories ({lastPrompt.memories.length})</summary>
                  <div className="mt-2 space-y-2">
                    {lastPrompt.memories.map((m, i) => (
                      <div key={i} className="bg-fantasy-dark border border-slate-700 rounded p-2 text-xs">
                        <div className="text-slate-500 font-mono">distance: {m.distance?.toFixed?.(3) ?? 'n/a'}</div>
                        <div className="text-slate-300 whitespace-pre-wrap">{m.document}</div>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BannerProvider>
      <ModalProvider>
        <AppInner />
      </ModalProvider>
    </BannerProvider>
  );
}
