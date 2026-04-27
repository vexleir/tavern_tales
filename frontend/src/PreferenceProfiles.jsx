import { useCallback, useEffect, useState } from 'react';
import { apiFetch, parseErrorResponse } from './lib/api';

const fantasyInterestOptions = ['none', 'low', 'medium', 'high', 'favorite'];
const realWorldOptions = ['hard_no', 'soft_no', 'discuss_only', 'maybe', 'yes'];
const textRoleplayOptions = ['no', 'maybe', 'yes'];
const intensityOptions = ['light', 'moderate', 'intense'];
const shareOptions = ['private', 'overlap_only', 'summary', 'full'];
const povOptions = ['first', 'third'];
const roleOptions = ['dominant', 'submissive', 'switch', 'none'];
const consentOptions = ['explicit', 'implied', 'negotiated'];
const customResponseOptions = ['scale', 'yes_no', 'multi_select', 'text'];

function labelize(value) {
  return String(value || '').replaceAll('_', ' ');
}

function nowIso() {
  return new Date().toISOString();
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function SelectControl({ label, value, options, onChange }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-400">
      <span className="uppercase tracking-widest">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-fantasy-dark border border-slate-600 rounded px-2 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
      >
        {options.map(option => (
          <option key={option} value={option}>{labelize(option)}</option>
        ))}
      </select>
    </label>
  );
}

function TextControl({ label, value, onChange, rows = 2, placeholder = '', readOnly = false }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-400">
      <span className="uppercase tracking-widest">{label}</span>
      <textarea
        rows={rows}
        value={value || ''}
        placeholder={placeholder}
        readOnly={readOnly}
        onChange={(e) => onChange(e.target.value)}
        className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent resize-y"
      />
    </label>
  );
}

export default function PreferenceProfiles({ onBack }) {
  const [profiles, setProfiles] = useState([]);
  const [profile, setProfile] = useState(null);
  const [fantasies, setFantasies] = useState([]);
  const [activeFantasy, setActiveFantasy] = useState(null);
  const [newProfileName, setNewProfileName] = useState('');
  const [customDraft, setCustomDraft] = useState({ label: '', description: '', responseType: 'text' });
  const [protectDraft, setProtectDraft] = useState({ password: '', hint: '' });
  const [includePrivateExport, setIncludePrivateExport] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadProfiles = useCallback(async () => {
    try {
      const res = await apiFetch('/api/preference-profiles');
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const data = await res.json();
      setProfiles(data);
      return data;
    } catch (e) {
      setError(`Could not load profiles: ${e.message}`);
      return [];
    }
  }, []);

  const loadFantasies = useCallback(async (profileId) => {
    if (!profileId) return [];
    try {
      const res = await apiFetch(`/api/fantasies?profile_id=${encodeURIComponent(profileId)}`);
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const data = await res.json();
      setFantasies(data);
      return data;
    } catch (e) {
      setError(`Could not load fantasy drafts: ${e.message}`);
      return [];
    }
  }, []);

  const openProfile = useCallback(async (profileId) => {
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/preference-profiles/${profileId}?include_private=true`);
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const data = await res.json();
      setProfile(data);
      setActiveFantasy(null);
      await loadFantasies(profileId);
    } catch (e) {
      setError(`Could not open profile: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }, [loadFantasies]);

  useEffect(() => {
    let cancelled = false;
    apiFetch('/api/preference-profiles')
      .then(async (res) => {
        if (!res.ok) throw new Error(await parseErrorResponse(res));
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setProfiles(data);
        if (data.length > 0) openProfile(data[0].profileId);
      })
      .catch((e) => {
        if (!cancelled) setError(`Could not load profiles: ${e.message}`);
      });
    return () => { cancelled = true; };
  }, [openProfile]);

  const createProfile = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/preference-profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ displayName: newProfileName || 'New Profile' })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const created = await res.json();
      setNewProfileName('');
      await loadProfiles();
      await openProfile(created.profileId);
    } catch (e) {
      setError(`Could not create profile: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = async (nextProfile = profile) => {
    if (!nextProfile) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/preference-profiles/${nextProfile.profileId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextProfile)
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const saved = await res.json();
      setProfile(saved);
      await loadProfiles();
    } catch (e) {
      setError(`Could not save profile: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const patchProfile = (mutator) => {
    setProfile(current => {
      if (!current) return current;
      const next = structuredClone(current);
      mutator(next);
      next.updatedAt = nowIso();
      return next;
    });
  };

  const updateGlobal = (field, value) => {
    patchProfile(next => {
      next.globalPreferences = { ...(next.globalPreferences || {}), [field]: value };
    });
  };

  const updateRealityBridge = (field, value) => {
    patchProfile(next => {
      next.realityBridge = { ...(next.realityBridge || {}), [field]: value };
    });
  };

  const updateItem = (categoryIndex, itemIndex, patch) => {
    patchProfile(next => {
      const item = next.categories[categoryIndex].items[itemIndex];
      next.categories[categoryIndex].items[itemIndex] = { ...item, ...patch, updatedAt: nowIso() };
    });
  };

  const addCustomQuestion = () => {
    if (!customDraft.label.trim()) return;
    patchProfile(next => {
      next.customPreferences = [
        ...(next.customPreferences || []),
        {
          createdBy: next.profileId,
          label: customDraft.label.trim(),
          description: customDraft.description.trim(),
          responseType: customDraft.responseType,
          options: [],
          response: '',
          fantasyInterest: 'none',
          realWorldWillingness: 'hard_no',
          textRoleplayWillingness: 'no',
          fantasyOnly: true,
          context: ['ai'],
          partnerSharePermission: 'private',
          commentsPrivate: '',
          commentsShareable: '',
          status: 'active',
          createdAt: nowIso(),
          updatedAt: nowIso()
        }
      ];
    });
    setCustomDraft({ label: '', description: '', responseType: 'text' });
  };

  const updateCustom = (index, patch) => {
    patchProfile(next => {
      const current = next.customPreferences[index];
      next.customPreferences[index] = { ...current, ...patch, updatedAt: nowIso() };
    });
  };

  const generateFantasyDraft = async () => {
    if (!profile) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/preference-profiles/${profile.profileId}/random-fantasy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ save: true, context: 'ai', selectedCount: 4, sharingMode: 'private' })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const draft = await res.json();
      setActiveFantasy(draft);
      await loadFantasies(profile.profileId);
    } catch (e) {
      setError(`Could not create fantasy draft: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const openFantasy = async (fantasyId) => {
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/fantasies/${fantasyId}?include_private=true`);
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setActiveFantasy(await res.json());
      setProtectDraft({ password: '', hint: '' });
    } catch (e) {
      setError(`Could not open fantasy draft: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const protectFantasy = async () => {
    if (!activeFantasy || protectDraft.password.length < 8) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/fantasies/${activeFantasy.id}/protect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(protectDraft)
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setActiveFantasy(await res.json());
      setProtectDraft({ password: '', hint: '' });
      await loadFantasies(activeFantasy.ownerProfileId);
    } catch (e) {
      setError(`Could not protect draft: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const exportProfile = async () => {
    if (!profile) return;
    try {
      const res = await apiFetch(`/api/preference-profiles/${profile.profileId}/export?include_private=${includePrivateExport}`);
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const payload = await res.json();
      downloadJson(`${profile.profileId}.${includePrivateExport ? 'private' : 'redacted'}.preferences.json`, payload);
    } catch (e) {
      setError(`Could not export profile: ${e.message}`);
    }
  };

  const importProfile = async (file) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const payload = JSON.parse(await file.text());
      const res = await apiFetch('/api/preference-profiles/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: payload.profile || payload })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const imported = await res.json();
      await loadProfiles();
      await openProfile(imported.profileId);
    } catch (e) {
      setError(`Could not import profile: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const visibleCustoms = (profile?.customPreferences || [])
    .map((question, index) => ({ question, index }))
    .filter(({ question }) => question.status !== 'deleted');

  return (
    <div className="min-h-screen bg-fantasy-dark text-fantasy-text font-sans">
      <header className="sticky top-0 z-20 bg-fantasy-panel/95 border-b border-slate-700/70 px-5 py-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-serif text-fantasy-accent">Preference Profiles</h1>
          <p className="text-xs uppercase tracking-widest text-slate-500 mt-1">Fantasy interest is not real-world consent</p>
        </div>
        <div className="flex gap-2">
          <button onClick={onBack} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 rounded px-4 py-2 text-sm">Menu</button>
          <button onClick={() => saveProfile()} disabled={!profile || busy} className="bg-fantasy-accent hover:bg-amber-600 disabled:opacity-50 text-white rounded px-4 py-2 text-sm font-bold">Save Profile</button>
        </div>
      </header>

      <main className="grid grid-cols-1 xl:grid-cols-[290px_1fr_360px] min-h-[calc(100vh-73px)]">
        <aside className="border-r border-slate-700/70 bg-fantasy-panel/50 p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label className="text-xs uppercase tracking-widest text-slate-400">New profile</label>
            <div className="flex gap-2">
              <input
                value={newProfileName}
                onChange={(e) => setNewProfileName(e.target.value)}
                placeholder="Profile name"
                className="min-w-0 flex-1 bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-fantasy-accent"
              />
              <button onClick={createProfile} disabled={busy} className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded px-3 text-sm font-bold">Add</button>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <h2 className="text-xs uppercase tracking-widest text-slate-400">Profiles</h2>
            {profiles.length === 0 && <p className="text-sm text-slate-500 italic">No profiles yet.</p>}
            {profiles.map(summary => (
              <button
                key={summary.profileId}
                onClick={() => openProfile(summary.profileId)}
                className={`text-left rounded border px-3 py-3 transition ${
                  profile?.profileId === summary.profileId
                    ? 'bg-fantasy-accent/15 border-fantasy-accent/60'
                    : 'bg-fantasy-dark/60 border-slate-700 hover:border-slate-500'
                }`}
              >
                <span className="block text-sm font-bold text-amber-400">{summary.displayName}</span>
                <span className="block text-xs text-slate-500 mt-1">v{summary.profileVersion}</span>
              </button>
            ))}
          </div>

          <div className="border-t border-slate-700 pt-4 flex flex-col gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={includePrivateExport} onChange={(e) => setIncludePrivateExport(e.target.checked)} className="accent-amber-500" />
              Include private fields
            </label>
            <button onClick={exportProfile} disabled={!profile} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Export Profile</button>
            <label className="block">
              <span className="text-xs uppercase tracking-widest text-slate-400">Import profile</span>
              <input
                type="file"
                accept="application/json"
                onChange={(e) => importProfile(e.target.files?.[0])}
                className="mt-2 block w-full text-xs text-slate-300 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200 hover:file:bg-slate-600"
              />
            </label>
          </div>

          {error && <div className="bg-red-900/40 border border-red-700 rounded p-3 text-red-200 text-sm">{error}</div>}
        </aside>

        <section className="p-5 md:p-7 overflow-y-auto flex flex-col gap-6">
          {!profile ? (
            <div className="border border-dashed border-slate-700 rounded p-8 text-slate-400 text-center">Create or select a profile.</div>
          ) : (
            <>
              <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-lg p-5">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <label className="flex flex-col gap-1 text-xs text-slate-400 md:col-span-1">
                    <span className="uppercase tracking-widest">Display name</span>
                    <input
                      value={profile.displayName || ''}
                      onChange={(e) => patchProfile(next => { next.displayName = e.target.value; })}
                      className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-slate-400">
                    <span className="uppercase tracking-widest">Gender</span>
                    <input value={profile.globalPreferences?.gender || ''} onChange={(e) => updateGlobal('gender', e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent" />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-slate-400">
                    <span className="uppercase tracking-widest">Orientation</span>
                    <input value={profile.globalPreferences?.orientation || ''} onChange={(e) => updateGlobal('orientation', e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent" />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-slate-400">
                    <span className="uppercase tracking-widest">Relationship style</span>
                    <input value={profile.globalPreferences?.relationshipStyle || ''} onChange={(e) => updateGlobal('relationshipStyle', e.target.value)} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent" />
                  </label>
                  <SelectControl label="Consent style" value={profile.globalPreferences?.consentStyle || 'explicit'} options={consentOptions} onChange={(v) => updateGlobal('consentStyle', v)} />
                  <SelectControl label="POV" value={profile.globalPreferences?.preferredPOV || 'third'} options={povOptions} onChange={(v) => updateGlobal('preferredPOV', v)} />
                  <SelectControl label="Role" value={profile.globalPreferences?.rolePreference || 'none'} options={roleOptions} onChange={(v) => updateGlobal('rolePreference', v)} />
                  <label className="flex items-end gap-2 text-sm text-slate-300 pb-2">
                    <input type="checkbox" checked={Boolean(profile.globalPreferences?.fadeToBlack)} onChange={(e) => updateGlobal('fadeToBlack', e.target.checked)} className="accent-amber-500" />
                    Fade to black
                  </label>
                  <TextControl label="Aftercare preference" value={profile.globalPreferences?.aftercarePreference || ''} onChange={(v) => updateGlobal('aftercarePreference', v)} />
                </div>
              </section>

              {profile.categories.map((category, categoryIndex) => (
                <section key={category.id} className="bg-fantasy-panel/40 border border-slate-700/50 rounded-lg p-5">
                  <div className="mb-4">
                    <h2 className="text-xl font-serif text-amber-500">{category.label}</h2>
                    <p className="text-sm text-slate-400 mt-1">{category.description}</p>
                  </div>
                  <div className="flex flex-col gap-4">
                    {category.items.map((item, itemIndex) => (
                      <div key={item.id} className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4">
                        <div className="flex flex-col gap-1 mb-4">
                          <h3 className="text-base font-bold text-slate-100">{item.label}</h3>
                          <p className="text-sm text-slate-400">{item.description}</p>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                          <SelectControl label="Fantasy interest" value={item.fantasyInterest} options={fantasyInterestOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { fantasyInterest: v })} />
                          <SelectControl label="Text roleplay" value={item.textRoleplayWillingness} options={textRoleplayOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { textRoleplayWillingness: v })} />
                          <SelectControl label="Real world" value={item.realWorldWillingness} options={realWorldOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { realWorldWillingness: v })} />
                          <SelectControl label="Intensity" value={item.intensityPreference} options={intensityOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { intensityPreference: v })} />
                          <SelectControl label="Partner share" value={item.partnerSharePermission} options={shareOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { partnerSharePermission: v })} />
                          <label className="flex items-end gap-2 text-sm text-slate-300 pb-2">
                            <input type="checkbox" checked={Boolean(item.fantasyOnly)} onChange={(e) => updateItem(categoryIndex, itemIndex, { fantasyOnly: e.target.checked })} className="accent-amber-500" />
                            Fantasy only
                          </label>
                          <TextControl label="Private notes" value={item.commentsPrivate} onChange={(v) => updateItem(categoryIndex, itemIndex, { commentsPrivate: v })} />
                          <TextControl label="Shareable notes" value={item.commentsShareable} onChange={(v) => updateItem(categoryIndex, itemIndex, { commentsShareable: v })} />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}

              <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-lg p-5">
                <h2 className="text-xl font-serif text-amber-500 mb-4">Custom Questions</h2>
                <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_150px_auto] gap-3 items-end mb-4">
                  <label className="flex flex-col gap-1 text-xs text-slate-400">
                    <span className="uppercase tracking-widest">Label</span>
                    <input value={customDraft.label} onChange={(e) => setCustomDraft(d => ({ ...d, label: e.target.value }))} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent" />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-slate-400">
                    <span className="uppercase tracking-widest">Description</span>
                    <input value={customDraft.description} onChange={(e) => setCustomDraft(d => ({ ...d, description: e.target.value }))} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent" />
                  </label>
                  <SelectControl label="Response" value={customDraft.responseType} options={customResponseOptions} onChange={(v) => setCustomDraft(d => ({ ...d, responseType: v }))} />
                  <button onClick={addCustomQuestion} className="bg-slate-700 hover:bg-slate-600 text-white rounded px-4 py-2 text-sm font-bold">Add</button>
                </div>
                <div className="flex flex-col gap-3">
                  {visibleCustoms.map(({ question, index }) => (
                    <div key={question.id || index} className="bg-fantasy-dark/50 border border-slate-700 rounded p-4 grid grid-cols-1 md:grid-cols-[1fr_160px_120px_100px] gap-3">
                      <TextControl label={`Question${question.status === 'archived' ? ' (archived)' : ''}`} rows={2} value={question.label} onChange={(v) => updateCustom(index, { label: v })} />
                      <SelectControl label="Sharing" value={question.partnerSharePermission || 'private'} options={shareOptions} onChange={(v) => updateCustom(index, { partnerSharePermission: v })} />
                      <button onClick={() => updateCustom(index, { status: question.status === 'archived' ? 'active' : 'archived' })} className="self-end bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm">
                        {question.status === 'archived' ? 'Restore' : 'Archive'}
                      </button>
                      <button onClick={() => updateCustom(index, { status: 'deleted' })} className="self-end bg-red-900/40 hover:bg-red-800 text-red-200 border border-red-900/50 rounded px-3 py-2 text-sm">Delete</button>
                    </div>
                  ))}
                </div>
              </section>

              <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-lg p-5">
                <h2 className="text-xl font-serif text-amber-500 mb-4">Reality Bridge</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <label className="flex items-end gap-2 text-sm text-slate-300 pb-2">
                    <input type="checkbox" checked={Boolean(profile.realityBridge?.enabled)} onChange={(e) => updateRealityBridge('enabled', e.target.checked)} className="accent-amber-500" />
                    Enabled
                  </label>
                  <SelectControl label="Intent" value={profile.realityBridge?.intent || 'discussion_only'} options={['discussion_only', 'maybe_try', 'want_to_try']} onChange={(v) => updateRealityBridge('intent', v)} />
                  <SelectControl label="Comfort" value={profile.realityBridge?.comfortLevel || 'curious'} options={['curious', 'cautious', 'interested', 'enthusiastic']} onChange={(v) => updateRealityBridge('comfortLevel', v)} />
                  <TextControl label="Non-negotiables" value={(profile.realityBridge?.nonNegotiables || []).join('\n')} onChange={(v) => updateRealityBridge('nonNegotiables', v.split('\n').map(x => x.trim()).filter(Boolean))} />
                  <TextControl label="Conditions" value={(profile.realityBridge?.conditions || []).join('\n')} onChange={(v) => updateRealityBridge('conditions', v.split('\n').map(x => x.trim()).filter(Boolean))} />
                  <label className="flex items-end gap-2 text-sm text-slate-300 pb-2">
                    <input type="checkbox" checked={Boolean(profile.realityBridge?.shareWithPartner)} onChange={(e) => updateRealityBridge('shareWithPartner', e.target.checked)} className="accent-amber-500" />
                    Share with partner
                  </label>
                </div>
              </section>
            </>
          )}
        </section>

        <aside className="border-l border-slate-700/70 bg-fantasy-panel/50 p-4 flex flex-col gap-4 overflow-y-auto">
          <button onClick={generateFantasyDraft} disabled={!profile || busy} className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded-lg px-4 py-3 text-sm font-bold uppercase tracking-widest">Random Fantasy Draft</button>

          <section className="flex flex-col gap-2">
            <h2 className="text-xs uppercase tracking-widest text-slate-400">Saved drafts</h2>
            {fantasies.length === 0 && <p className="text-sm text-slate-500 italic">No saved drafts.</p>}
            {fantasies.map(fantasy => (
              <button
                key={fantasy.id}
                onClick={() => openFantasy(fantasy.id)}
                className={`text-left border rounded px-3 py-3 transition ${
                  activeFantasy?.id === fantasy.id
                    ? 'bg-fantasy-accent/15 border-fantasy-accent/60'
                    : 'bg-fantasy-dark/60 border-slate-700 hover:border-slate-500'
                }`}
              >
                <span className="block text-sm font-bold text-amber-400">{fantasy.title}</span>
                <span className="block text-xs text-slate-500 mt-1">v{fantasy.createdFromProfileVersion}{fantasy.passwordProtected ? ' / protected' : ''}</span>
              </button>
            ))}
          </section>

          {activeFantasy && (
            <section className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4 flex flex-col gap-4">
              <div>
                <h2 className="text-lg font-serif text-amber-500">{activeFantasy.title}</h2>
                <p className="text-xs text-slate-500 mt-1">{activeFantasy.id}</p>
              </div>
              <TextControl label="Synopsis" rows={4} value={activeFantasy.synopsis || activeFantasy.content || ''} onChange={() => {}} readOnly />
              <TextControl label="Seed prompt" rows={6} value={activeFantasy.seedPrompt || ''} onChange={() => {}} readOnly />
              {activeFantasy.campaignSeed && (
                <div className="text-xs text-slate-400 bg-slate-950/40 border border-slate-700 rounded p-3">
                  <div className="uppercase tracking-widest text-slate-500 mb-2">Campaign seed</div>
                  <div className="text-slate-300 whitespace-pre-wrap">{activeFantasy.campaignSeed.startingScene}</div>
                </div>
              )}
              {!activeFantasy.passwordProtection?.enabled ? (
                <div className="border-t border-slate-700 pt-4 flex flex-col gap-2">
                  <input
                    type="password"
                    value={protectDraft.password}
                    onChange={(e) => setProtectDraft(d => ({ ...d, password: e.target.value }))}
                    placeholder="Password"
                    className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
                  />
                  <input
                    value={protectDraft.hint}
                    onChange={(e) => setProtectDraft(d => ({ ...d, hint: e.target.value }))}
                    placeholder="Hint"
                    className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
                  />
                  <button onClick={protectFantasy} disabled={protectDraft.password.length < 8 || busy} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Password Protect</button>
                </div>
              ) : (
                <div className="border border-emerald-800 bg-emerald-950/30 text-emerald-200 rounded p-3 text-sm">Password protected</div>
              )}
            </section>
          )}
        </aside>
      </main>
    </div>
  );
}
