import { useCallback, useEffect, useState } from 'react';
import CampaignCreator from './CampaignCreator';
import BannerProvider from './components/BannerProvider';
import ModalProvider from './components/ModalProvider';
import useBanner from './hooks/useBanner';
import useModal from './hooks/useModal';
import useNdjsonStream from './hooks/useNdjsonStream';
import { apiUrl } from './lib/api';

const createCampaignId = () => `campaign_${Date.now()}`;

function AppInner() {
  const [appMode, setAppMode] = useState('menu');
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

  const modal = useModal();
  const banner = useBanner();

  // -------------------------------------------------------- data access

  const refreshState = useCallback(async (id) => {
    try {
      const res = await fetch(apiUrl(`/api/state/${id}`));
      if (!res.ok) return null;
      const data = await res.json();
      setCampaignState(data);
      const visible = (data.messages || []).filter(m => !m.is_kickoff || m.role === 'assistant');
      setMessages(visible);
      return data;
    } catch (e) {
      banner.error(`Could not load campaign: ${e.message}`);
      return null;
    }
  }, [banner]);

  const { isStreaming, streamEndpoint, stop: handleStop } = useNdjsonStream({
    onError: banner.error,
    onAbortWithTokens: () => refreshState(activeCampaignId)
  });

  useEffect(() => {
    if (appMode === 'menu') {
      fetch(apiUrl('/api/campaigns'))
        .then(r => r.json())
        .then(setSavedCampaigns)
        .catch(e => banner.error(`Could not list campaigns: ${e.message}`));
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

  const handleSend = async () => {
    if (isStreaming || !input.trim()) return;
    const userText = input;
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
      const res = await fetch(apiUrl(`/api/campaign/${activeCampaignId}/message/${msgId}`), { method: 'DELETE' });
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
      await fetch(apiUrl(`/api/campaigns/${id}`), { method: 'DELETE' });
      const res = await fetch(apiUrl('/api/campaigns'));
      setSavedCampaigns(await res.json());
    } catch (err) {
      banner.error(`Delete failed: ${err.message}`);
    }
  };

  const handleFork = async () => {
    try {
      const res = await fetch(apiUrl(`/api/campaigns/${activeCampaignId}/fork`), { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'success') {
          banner.info('Timeline forked — loading alternate campaign...');
          await loadCampaign(data.new_campaign_id);
        }
      }
    } catch (e) {
      banner.error(`Fork failed: ${e.message}`);
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
      const res = await fetch(apiUrl(`/api/state/${activeCampaignId}`), {
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
      banner.error(`Edit failed: ${e.message}`);
      setCampaignState(before);
    }
  };

  const handleUndo = async () => {
    if (undoStack.length === 0) return;
    const last = undoStack[undoStack.length - 1];
    setUndoStack(s => s.slice(0, -1));
    setCampaignState(last.before);
    try {
      const res = await fetch(apiUrl(`/api/state/${activeCampaignId}`), {
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
      banner.error(`Undo failed: ${e.message}`);
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

  const updateStat = (name, val) => pushStatePatch({ stats: { [name]: val } }, s => { s.player.stats[name] = val; }, `Edit ${name}`);
  const updateLocation = (loc) => pushStatePatch({ player: { location: loc } }, s => { s.player.location = loc; }, 'Edit location');
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
      const res = await fetch(apiUrl(`/api/campaign/${activeCampaignId}/export`));
      if (!res.ok) { banner.error('Export failed'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeCampaignId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      banner.error(`Export failed: ${e.message}`);
    }
  };

  const handleDebugExport = async () => {
    try {
      const res = await fetch(apiUrl(`/api/campaign/${activeCampaignId}/debug`));
      if (!res.ok) { banner.error('Debug export failed'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeCampaignId}.debug.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      banner.error(`Debug export failed: ${e.message}`);
    }
  };

  const handleImport = async (file) => {
    try {
      const text = await file.text();
      const payload = JSON.parse(text);
      const res = await fetch(apiUrl('/api/campaign/import'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: payload.state, memories: payload.memories })
      });
      if (!res.ok) { banner.error('Import failed'); return; }
      const { campaign_id } = await res.json();
      banner.info(`Imported campaign ${campaign_id}`);
      const list = await fetch(apiUrl('/api/campaigns'));
      setSavedCampaigns(await list.json());
    } catch (e) {
      banner.error(`Import failed: ${e.message}`);
    }
  };

  // -------------------------------------------------------- inspector

  const openInspector = async () => {
    try {
      const res = await fetch(apiUrl(`/api/campaign/${activeCampaignId}/last_prompt`));
      if (res.ok) {
        const data = await res.json();
        if (data.available) {
          setLastPrompt(data);
          setInspectorOpen(true);
        } else {
          banner.info('No prompt available yet — send a turn first.');
        }
      }
    } catch (e) { banner.error(`Inspector failed: ${e.message}`); }
  };

  // -------------------------------------------------------- render

  if (appMode === 'menu') {
    return (
      <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-serif flex flex-col items-center justify-center p-8">
        <h1 className="text-6xl text-fantasy-accent drop-shadow-md mb-12 border-b border-slate-700 pb-4">Tavern Tales Reborn</h1>
        <div className="bg-fantasy-panel/40 border border-slate-700/50 rounded-xl shadow-lg backdrop-blur p-8 w-full max-w-2xl text-center">
          <button
            onClick={() => { setActiveCampaignId(createCampaignId()); setAppMode('setup'); }}
            className="bg-indigo-700 hover:bg-indigo-600 text-white w-full py-4 rounded-lg font-sans font-bold tracking-widest text-lg uppercase transition shadow-md mb-4"
          >+ Forge New World</button>

          <label className="block mb-8">
            <span className="text-xs uppercase tracking-widest text-slate-400 font-sans">Import Campaign (.json)</span>
            <input
              type="file"
              accept="application/json"
              onChange={(e) => e.target.files?.[0] && handleImport(e.target.files[0])}
              className="block mt-2 w-full text-xs text-slate-300 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200 hover:file:bg-slate-600"
            />
          </label>

          <h3 className="text-sm uppercase text-slate-400 font-sans tracking-widest mb-4">Or Continue Journey</h3>
          {savedCampaigns.length === 0 && <p className="text-slate-500 italic text-sm">No saved campaigns found.</p>}
          <div className="flex flex-col gap-3">
            {savedCampaigns.map(c => (
              <div key={c.id} className="flex gap-2">
                <button onClick={() => loadCampaign(c.id)} className="flex-1 bg-fantasy-dark/50 hover:bg-slate-700 border border-slate-600 rounded p-4 text-left font-sans flex justify-between items-center transition">
                  <span className="text-amber-500 font-bold">{c.player}'s Tale</span>
                  <span className="text-xs text-slate-500">{c.id}</span>
                </button>
                <button onClick={(e) => deleteCampaign(c.id, e)} className="bg-red-900/40 hover:bg-red-800 text-red-200 border border-red-900/50 rounded px-4 font-sans font-bold transition" title="Delete World">✗</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (appMode === 'setup') {
    return <CampaignCreator campaignId={activeCampaignId} onComplete={async () => { await loadCampaign(activeCampaignId); }} />;
  }

  const ctx = promptStats ? Math.round((promptStats.total_used / promptStats.model_context_window) * 100) : 0;
  const lastGmMsg = [...messages].reverse().find(m => m.role === 'assistant');
  const canContinue = !isStreaming && lastGmMsg && (lastGmMsg.partial || !/[.!?…"'”]$/.test((lastGmMsg.content || '').trim()));

  return (
    <div className="h-screen overflow-hidden flex text-fantasy-text bg-fantasy-dark">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-20 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      {/* Sidebar */}
      <aside className={`${sidebarOpen ? 'fixed inset-y-0 left-0 z-30 flex' : 'hidden'} md:relative md:inset-auto md:z-auto w-72 bg-fantasy-panel border-r border-slate-700/50 p-4 md:flex flex-col gap-6 overflow-y-auto h-screen`}>
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
                {(campaignState.player?.inventory?.length > 0 || directorMode) && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50">
                    <span className="text-slate-400 block text-xs mb-1">Inventory:</span>
                    <div className="flex flex-wrap gap-1">
                      {campaignState.player?.inventory?.map((item, idx) => (
                        <span key={idx} className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-300 flex items-center gap-1">
                          {item}
                          {directorMode && <button onClick={() => removeInventory(item)} className="text-red-400 hover:text-red-300 ml-1">×</button>}
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
                          <select className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-300 w-full mb-1" value={npc.disposition} onChange={e => updateNpc(idx, { disposition: e.target.value })}>
                            <option>Friendly</option><option>Neutral</option><option>Suspicious</option><option>Hostile</option>
                          </select>
                          <button className="text-xs text-red-400 hover:text-red-300" onClick={() => removeNpc(idx)}>Remove NPC</button>
                        </>
                      ) : (
                        <>
                          <div className="font-serif text-fantasy-accent font-bold text-base border-b border-slate-700 pb-1 mb-2">{npc.name}</div>
                          <div className="text-xs text-slate-400 mb-1">Disposition: <span className="ml-1 text-slate-200">{npc.disposition}</span></div>
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
                            <button onClick={() => removeLore(k)} className="text-red-400 hover:text-red-300 ml-auto">×</button>
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
            <button className="md:hidden text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded" onClick={() => setSidebarOpen(true)}>State</button>
            <h1 className="font-serif text-xl text-fantasy-accent drop-shadow-sm">The Story</h1>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {promptStats && (
              <div className="flex items-center gap-2 text-xs text-slate-400 border-r border-slate-600 pr-3">
                <div className="w-32 h-1.5 bg-slate-700 rounded overflow-hidden">
                  <div className={`h-full ${ctx > 85 ? 'bg-red-500' : ctx > 65 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(ctx, 100)}%` }} />
                </div>
                <span className="font-mono">{promptStats.total_used.toLocaleString()} / {promptStats.model_context_window.toLocaleString()}</span>
              </div>
            )}
            {lastResolution && (
              <div className="text-xs text-emerald-300 border border-emerald-700/60 bg-emerald-950/30 rounded px-2 py-1">
                {lastResolution.summary}
              </div>
            )}
            {directorMode && (
              <>
                <button onClick={openInspector} className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded">Inspect Prompt</button>
                <button onClick={handleDebugExport} className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded">Debug Bundle</button>
                <button onClick={handleUndo} disabled={undoStack.length === 0} className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600 rounded disabled:opacity-40">Undo ({undoStack.length})</button>
                <button onClick={handleFork} className="text-xs px-3 py-1 bg-amber-600/30 hover:bg-amber-600/50 text-amber-400 border border-amber-600/50 rounded">Fork Timeline</button>
              </>
            )}
            <button
              onClick={() => setDirectorMode(!directorMode)}
              className={`text-sm px-4 py-1.5 rounded transition shadow-sm font-semibold border ${directorMode ? 'bg-amber-600/20 text-amber-500 border-amber-600/50' : 'bg-fantasy-dark text-slate-300 border-slate-600 hover:bg-slate-700'}`}
            >
              {directorMode ? 'Exit Director Mode' : 'Director Mode'}
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 md:p-8 flex flex-col gap-6 scroll-smooth">
          {messages.map((m, idx) => (
            <div key={m.id || idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} group relative`}>
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
          ))}
          {isStreaming && <div className="text-sm text-amber-600/70 italic animate-pulse font-serif px-2">The storyteller is weaving the thread...</div>}
          {!isStreaming && lastGmMsg && lastGmMsg.id && !lastGmMsg.id.startsWith('temp') && (
            <div className="flex gap-2 text-xs">
              <button onClick={handleRegenerate} className="bg-slate-800 text-amber-400 border border-slate-600 hover:bg-slate-700 px-3 py-1 rounded-full shadow-md font-bold">↻ Reroll</button>
              {canContinue && (
                <button onClick={handleContinue} className="bg-slate-800 text-emerald-400 border border-slate-600 hover:bg-slate-700 px-3 py-1 rounded-full shadow-md font-bold">→ Continue</button>
              )}
            </div>
          )}
        </div>

        <div className="p-4 bg-fantasy-panel border-t border-slate-700/50 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]">
          <div className="max-w-4xl mx-auto flex gap-3">
            <textarea
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={isStreaming}
              placeholder="Describe your next action..."
              className="flex-1 min-h-[58px] max-h-40 resize-y bg-fantasy-dark border border-slate-600 rounded-lg px-5 py-4 focus:outline-none focus:border-fantasy-accent text-fantasy-text focus:ring-2 focus:ring-fantasy-accent/50 transition shadow-inner placeholder:text-slate-500 font-serif text-lg"
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
              >Commit</button>
            )}
          </div>
        </div>
      </main>

      {/* Prompt inspector modal */}
      {inspectorOpen && lastPrompt && (
        <div className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setInspectorOpen(false)}>
          <div className="bg-fantasy-panel border border-slate-600 rounded-lg shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-slate-700 flex justify-between items-center">
              <h2 className="font-serif text-lg text-fantasy-accent">Last Prompt (Inspector)</h2>
              <button onClick={() => setInspectorOpen(false)} className="text-slate-400 hover:text-slate-200">✗</button>
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
