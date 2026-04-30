import { useCallback, useEffect, useState } from 'react';
import { apiFetch, describeApiError, parseErrorResponse } from './lib/api';

const fantasyInterestOptions = ['none', 'low', 'medium', 'high', 'favorite'];
const realWorldOptions = ['hard_no', 'soft_no', 'discuss_only', 'maybe', 'yes'];
const textRoleplayOptions = ['no', 'maybe', 'yes'];
const intensityOptions = ['light', 'moderate', 'intense'];
const shareOptions = ['private', 'overlap_only', 'summary', 'full'];
const fantasySharingOptions = ['private', 'summary_only', 'overlap_only', 'full_scene', 'full_scene_with_notes'];
const contextOptions = ['ai', 'partner', 'multiplayer'];
const povOptions = ['first', 'third'];
const roleOptions = ['dominant', 'submissive', 'switch', 'none'];
const consentOptions = ['explicit', 'implied', 'negotiated'];
const customResponseOptions = ['scale', 'yes_no', 'multi_select', 'text'];
const giverReceiverOptions = ['giver', 'receiver', 'both'];
const giverReceiverLabels = {
  giver: 'I initiate, guide, or direct it',
  receiver: 'I follow, yield, or experience it',
  both: 'I am open to either side'
};
const roleSideHelp = 'For submission or surrender themes, follow/yield means this profile is the submitting side; initiate/direct means this profile guides a submitting partner.';
const fantasyOnlyRealWorldValues = new Set(['hard_no', 'soft_no']);
const onboardingCategoryIds = ['power_dynamics', 'control_themes', 'fantasy_elements', 'emotional_tone'];
const onboardingSteps = ['Identity', 'Boundaries', 'Sharing', 'Reality Bridge', 'Review'];

function labelize(value) {
  return String(value || '').replaceAll('_', ' ');
}

function optionLabel(value, labels = {}) {
  return labels[value] || labelize(value);
}

function roleDirectionLabel(value) {
  if (!value) return giverReceiverLabels.both;
  if (value.startsWith('first_')) return labelize(value).replace('first ', 'First profile: ').replace(' second ', ' / second profile: ');
  return giverReceiverLabels[value] || labelize(value);
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

function SelectControl({ label, value, options, onChange, optionLabels = {}, help = '' }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-400">
      <span className="uppercase tracking-widest">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-fantasy-dark border border-slate-600 rounded px-2 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
      >
        {options.map(option => (
          <option key={option} value={option}>{optionLabel(option, optionLabels)}</option>
        ))}
      </select>
      {help && <span className="text-[11px] leading-snug text-slate-500 normal-case tracking-normal">{help}</span>}
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

export default function PreferenceProfiles({ onBack, onCreateCampaignFromDraft }) {
  const [profiles, setProfiles] = useState([]);
  const [profile, setProfile] = useState(null);
  const [fantasies, setFantasies] = useState([]);
  const [activeFantasy, setActiveFantasy] = useState(null);
  const [newProfileName, setNewProfileName] = useState('');
  const [customDraft, setCustomDraft] = useState({ label: '', description: '', responseType: 'text' });
  const [protectDraft, setProtectDraft] = useState({ password: '', hint: '' });
  const [unlockDraft, setUnlockDraft] = useState({ password: '', unlocked: false });
  const [exportDraftMode, setExportDraftMode] = useState('summary_only');
  const [includePrivateExport, setIncludePrivateExport] = useState(false);
  const [compareProfileId, setCompareProfileId] = useState('');
  const [comparison, setComparison] = useState(null);
  const [generationOptions, setGenerationOptions] = useState({
    context: 'ai',
    selectedCount: 4,
    sharingMode: 'private',
    categoryIds: [],
    intensity: '',
    favoritesOnly: false,
    exploreLowerInterest: false,
    includeRealityBridge: false
  });
  const [onboardingStep, setOnboardingStep] = useState(0);
  const [showAdvancedEditor, setShowAdvancedEditor] = useState(false);
  const [onboardingDefaults, setOnboardingDefaults] = useState({
    textRoleplayWillingness: 'maybe',
    partnerSharePermission: 'private',
    intensityPreference: 'moderate'
  });
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
      setError(`Could not load profiles: ${describeApiError(e)}`);
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
      setError(`Could not load fantasy drafts: ${describeApiError(e)}`);
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
      setComparison(null);
      setOnboardingStep(0);
      setShowAdvancedEditor(Boolean(data.onboardingCompletedAt));
      await loadFantasies(profileId);
    } catch (e) {
      setError(`Could not open profile: ${describeApiError(e)}`);
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
        if (!cancelled) setError(`Could not load profiles: ${describeApiError(e)}`);
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
      setError(`Could not create profile: ${describeApiError(e)}`);
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
      setError(`Could not save profile: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const deleteProfile = async () => {
    if (!profile) return;
    const ok = window.confirm(`Delete "${profile.displayName || 'this profile'}"? Saved fantasy drafts will remain independent.`);
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/preference-profiles/${profile.profileId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const remaining = await loadProfiles();
      setProfile(null);
      setActiveFantasy(null);
      setFantasies([]);
      if (remaining.length > 0) {
        await openProfile(remaining[0].profileId);
      }
    } catch (e) {
      setError(`Could not delete profile: ${describeApiError(e)}`);
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

  const updateOnboardingItem = (itemId, patch) => {
    patchProfile(next => {
      for (const category of next.categories || []) {
        const itemIndex = (category.items || []).findIndex(item => item.id === itemId);
        if (itemIndex >= 0) {
          const current = category.items[itemIndex];
          category.items[itemIndex] = { ...current, ...patch, updatedAt: nowIso() };
          return;
        }
      }
    });
  };

  const applyOnboardingDefaults = () => {
    patchProfile(next => {
      for (const category of next.categories || []) {
        category.items = (category.items || []).map(item => ({
          ...item,
          textRoleplayWillingness: onboardingDefaults.textRoleplayWillingness,
          partnerSharePermission: onboardingDefaults.partnerSharePermission,
          intensityPreference: onboardingDefaults.intensityPreference,
          updatedAt: nowIso()
        }));
      }
    });
  };

  const saveOnboardingProgress = async (nextStep = onboardingStep + 1) => {
    await saveProfile();
    setOnboardingStep(Math.min(nextStep, onboardingSteps.length - 1));
  };

  const finishOnboarding = async () => {
    if (!profile) return;
    const now = nowIso();
    const next = structuredClone(profile);
    next.onboardingCompletedAt = next.onboardingCompletedAt || now;
    next.lastReviewedAt = now;
    next.updatedAt = now;
    await saveProfile(next);
    setShowAdvancedEditor(true);
    setOnboardingStep(onboardingSteps.length - 1);
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
          giverReceiverRole: 'both',
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
        body: JSON.stringify({
          save: true,
          ...generationOptions,
          selectedCount: Number(generationOptions.selectedCount) || 4,
          categoryIds: generationOptions.categoryIds,
          intensity: generationOptions.intensity || null,
          exploreLowerInterest: generationOptions.favoritesOnly ? false : generationOptions.exploreLowerInterest
        })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const draft = await res.json();
      setActiveFantasy(draft);
      await loadFantasies(profile.profileId);
    } catch (e) {
      setError(`Could not create fantasy draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const regenerateFantasyDraft = async () => {
    await generateFantasyDraft();
  };

  const duplicateFantasyDraft = async () => {
    if (!activeFantasy || fantasyIsLocked) return;
    setBusy(true);
    setError('');
    try {
      const copy = structuredClone(activeFantasy);
      delete copy.id;
      copy.title = `${activeFantasy.title || 'Fantasy Draft'} Copy`;
      copy.passwordProtection = { enabled: false, protectedAt: null, hint: '' };
      copy.protectedContent = null;
      copy.updatedAt = nowIso();
      const res = await apiFetch('/api/fantasies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fantasy: copy })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const saved = await res.json();
      setActiveFantasy(saved);
      await loadFantasies(saved.ownerProfileId);
    } catch (e) {
      setError(`Could not duplicate draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const exportActiveFantasy = async () => {
    if (!activeFantasy) return;
    setBusy(true);
    setError('');
    try {
      const body = { mode: exportDraftMode };
      if (activeFantasy.passwordProtection?.enabled && unlockDraft.unlocked) {
        body.password = unlockDraft.password;
      }
      const res = await apiFetch(`/api/fantasies/${activeFantasy.id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const payload = await res.json();
      downloadJson(`${activeFantasy.id}.${exportDraftMode}.fantasy-export.json`, payload);
    } catch (e) {
      setError(`Could not export draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const printActiveFantasy = () => {
    if (!activeFantasy || fantasyIsLocked) return;
    const printable = [
      activeFantasy.title,
      '',
      'Fantasy interest is not real-world consent.',
      '',
      activeFantasy.synopsis || '',
      '',
      activeFantasy.content || '',
      activeFantasy.realityBridgeNotes ? `\nReality bridge notes:\n${activeFantasy.realityBridgeNotes}` : ''
    ].filter(Boolean).join('\n');
    const win = window.open('', '_blank', 'noopener,noreferrer');
    if (!win) {
      setError('Could not open print view. Check popup settings.');
      return;
    }
    win.document.write(`<pre style="white-space:pre-wrap;font:16px Georgia,serif;line-height:1.5;padding:32px;">${printable.replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))}</pre>`);
    win.document.close();
    win.print();
  };

  const printComparisonSummary = () => {
    if (!comparison) return;
    const lines = [
      'Profile Compatibility Summary',
      '',
      comparison.safetyPrinciple,
      '',
      `Matches: ${comparison.matches?.length || 0}`,
      `Blocked: ${comparison.blocked?.length || 0}`,
      `Reality bridge exclusions: ${comparison.realityBridgeExcludedThemeIds?.length || 0}`,
      '',
      'Matched themes:',
      ...(comparison.matches || []).map(match => (
                        `- ${match.label}: ${labelize(match.fantasyInterest)} fantasy, ${labelize(match.textRoleplayWillingness)} text, ${labelize(match.realWorldWillingness)} real world, ${labelize(match.intensityPreference)} intensity, ${roleDirectionLabel(match.giverReceiverRole)}`
      )),
      '',
      'Blocked themes:',
      ...(comparison.blocked || []).slice(0, 20).map(blocked => (
        `- ${blocked.label || blocked.id}: ${(blocked.reasons || []).map(labelize).join(', ')}`
      )),
    ];
    const printable = lines.join('\n');
    const win = window.open('', '_blank', 'noopener,noreferrer');
    if (!win) {
      setError('Could not open print view. Check popup settings.');
      return;
    }
    win.document.write(`<pre style="white-space:pre-wrap;font:16px Georgia,serif;line-height:1.5;padding:32px;">${printable.replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))}</pre>`);
    win.document.close();
    win.print();
  };

  const importFantasyDraft = async (file) => {
    if (!file || !profile) return;
    setBusy(true);
    setError('');
    try {
      const payload = JSON.parse(await file.text());
      const fantasy = structuredClone(payload.fantasy || payload);
      delete fantasy.id;
      fantasy.ownerProfileId = profile.profileId;
      fantasy.ownerUserId = profile.userId || fantasy.ownerUserId || 'local_default';
      fantasy.title = fantasy.title ? `${fantasy.title} (Imported)` : 'Imported Fantasy Draft';
      fantasy.passwordProtection = { enabled: false, protectedAt: null, hint: '' };
      fantasy.protectedContent = null;
      const res = await apiFetch('/api/fantasies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fantasy })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const imported = await res.json();
      setActiveFantasy(imported);
      await loadFantasies(profile.profileId);
    } catch (e) {
      setError(`Could not import draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const updateGenerationCategory = (categoryId, enabled) => {
    setGenerationOptions(current => ({
      ...current,
      categoryIds: enabled
        ? [...new Set([...current.categoryIds, categoryId])]
        : current.categoryIds.filter(id => id !== categoryId)
    }));
  };

  const openFantasy = async (fantasyId) => {
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/fantasies/${fantasyId}?include_private=true`);
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setActiveFantasy(await res.json());
      setProtectDraft({ password: '', hint: '' });
      setUnlockDraft({ password: '', unlocked: false });
    } catch (e) {
      setError(`Could not open fantasy draft: ${describeApiError(e)}`);
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
      setUnlockDraft({ password: '', unlocked: false });
      await loadFantasies(activeFantasy.ownerProfileId);
    } catch (e) {
      setError(`Could not protect draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const unlockFantasy = async () => {
    if (!activeFantasy || !unlockDraft.password) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/fantasies/${activeFantasy.id}/unlock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: unlockDraft.password })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setActiveFantasy(await res.json());
      setUnlockDraft(d => ({ ...d, unlocked: true }));
    } catch (e) {
      setError(`Could not unlock draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const updateActiveFantasy = (patch) => {
    setActiveFantasy(current => (
      current ? { ...current, ...patch, updatedAt: nowIso() } : current
    ));
  };

  const saveActiveFantasy = async () => {
    if (!activeFantasy) return;
    setBusy(true);
    setError('');
    try {
      const body = {
        fantasy: activeFantasy
      };
      if (activeFantasy.passwordProtection?.enabled && unlockDraft.unlocked) {
        body.password = unlockDraft.password;
      }
      const res = await apiFetch(`/api/fantasies/${activeFantasy.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const saved = await res.json();
      setActiveFantasy(saved);
      if (saved.passwordProtection?.enabled) {
        setUnlockDraft({ password: '', unlocked: false });
      }
      await loadFantasies(saved.ownerProfileId);
    } catch (e) {
      setError(`Could not save draft: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const compareProfiles = async () => {
    if (!profile || !compareProfileId || compareProfileId === profile.profileId) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/compatibility/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          firstProfileId: profile.profileId,
          secondProfileId: compareProfileId,
          context: 'ai'
        })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      setComparison(await res.json());
    } catch (e) {
      setError(`Could not compare profiles: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const createOverlapFantasy = async () => {
    if (!profile || !compareProfileId) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/compatibility/overlap-fantasy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          firstProfileId: profile.profileId,
          secondProfileId: compareProfileId,
          context: generationOptions.context || 'ai',
          selectedCount: Number(generationOptions.selectedCount) || 4,
          save: true
        })
      });
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const draft = await res.json();
      setActiveFantasy(draft);
      await loadFantasies(profile.profileId);
    } catch (e) {
      setError(`Could not create overlap draft: ${describeApiError(e)}`);
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
      setError(`Could not export profile: ${describeApiError(e)}`);
    }
  };

  const exportKeyBackup = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/preferences/key-backup');
      if (!res.ok) throw new Error(await parseErrorResponse(res));
      const payload = await res.json();
      downloadJson('tavern-tales-local-encryption-key.backup.json', payload);
    } catch (e) {
      setError(`Could not export key backup: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
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
      setError(`Could not import profile: ${describeApiError(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const visibleCustoms = (profile?.customPreferences || [])
    .map((question, index) => ({ question, index }))
    .filter(({ question }) => question.status !== 'deleted');
  const fantasyIsLocked = Boolean(activeFantasy?.passwordProtection?.enabled && !unlockDraft.unlocked);
  const compareOptions = profiles.filter(summary => summary.profileId !== profile?.profileId);
  const onboardingCategories = (profile?.categories || [])
    .filter(category => onboardingCategoryIds.includes(category.id))
    .map(category => ({ ...category, items: (category.items || []).slice(0, 3) }));
  const showOnboarding = Boolean(profile && !profile.onboardingCompletedAt && !showAdvancedEditor);

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
                {summary.linked_campaigns?.length > 0 && (
                  <span className="block text-xs text-emerald-600 mt-0.5">Used in {summary.linked_campaigns.length} campaign(s)</span>
                )}
              </button>
            ))}
          </div>

          <div className="border-t border-slate-700 pt-4 flex flex-col gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={includePrivateExport} onChange={(e) => setIncludePrivateExport(e.target.checked)} className="accent-amber-500" />
              Include private fields
            </label>
            <button onClick={exportProfile} disabled={!profile} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Export Profile</button>
            <button onClick={exportKeyBackup} disabled={busy} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Backup Local Key</button>
            <button onClick={deleteProfile} disabled={!profile || busy} className="bg-red-900/40 hover:bg-red-800 disabled:opacity-50 text-red-200 border border-red-900/50 rounded px-3 py-2 text-sm">Delete Profile</button>
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
          ) : showOnboarding ? (
            <section className="bg-fantasy-panel/40 border border-slate-700/50 rounded-lg p-5 flex flex-col gap-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-serif text-amber-500">Profile Onboarding</h2>
                  <p className="text-sm text-slate-400 mt-1">Set the basics now. You can skip any category and refine everything later.</p>
                </div>
                <button onClick={() => setShowAdvancedEditor(true)} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm">Advanced Editor</button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {onboardingSteps.map((step, index) => (
                  <button
                    key={step}
                    onClick={() => setOnboardingStep(index)}
                    className={`rounded border px-3 py-2 text-xs uppercase tracking-widest ${
                      onboardingStep === index
                        ? 'bg-fantasy-accent/20 border-fantasy-accent/70 text-amber-200'
                        : 'bg-fantasy-dark/60 border-slate-700 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    {step}
                  </button>
                ))}
              </div>

              {onboardingStep === 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <label className="flex flex-col gap-1 text-xs text-slate-400">
                    <span className="uppercase tracking-widest">Display name</span>
                    <input value={profile.displayName || ''} onChange={(e) => patchProfile(next => { next.displayName = e.target.value; })} className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent" />
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
              )}

              {onboardingStep === 1 && (
                <div className="flex flex-col gap-4">
                  <div className="bg-slate-950/30 border border-slate-700 rounded p-3 text-sm text-slate-300">Fantasy interest, text roleplay, and real-world interest are separate. A fantasy favorite can still be a real-world hard no.</div>
                  {onboardingCategories.map(category => (
                    <div key={category.id} className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4">
                      <h3 className="font-serif text-lg text-amber-500">{category.label}</h3>
                      <p className="text-sm text-slate-400 mb-4">{category.description}</p>
                      <div className="flex flex-col gap-3">
                        {category.items.map(item => (
                          <div key={item.id} className="grid grid-cols-1 md:grid-cols-[1fr_130px_130px_150px_170px] gap-3 items-end border-t border-slate-700/60 pt-3">
                            <div>
                              <div className="font-bold text-slate-100">{item.label}</div>
                              <div className="text-sm text-slate-400">{item.description}</div>
                            </div>
                            <SelectControl label="Fantasy" value={item.fantasyInterest} options={fantasyInterestOptions} onChange={(v) => updateOnboardingItem(item.id, { fantasyInterest: v })} />
                            <SelectControl label="Text" value={item.textRoleplayWillingness} options={textRoleplayOptions} onChange={(v) => updateOnboardingItem(item.id, { textRoleplayWillingness: v })} />
                            <SelectControl
                              label="Real world"
                              value={item.realWorldWillingness}
                              options={realWorldOptions}
                              onChange={(v) => updateOnboardingItem(item.id, { realWorldWillingness: v, fantasyOnly: fantasyOnlyRealWorldValues.has(v) })}
                            />
                            <SelectControl
                              label="My role in this theme"
                              value={item.giverReceiverRole || 'both'}
                              options={giverReceiverOptions}
                              optionLabels={giverReceiverLabels}
                              help={roleSideHelp}
                              onChange={(v) => updateOnboardingItem(item.id, { giverReceiverRole: v })}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {onboardingStep === 2 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <SelectControl label="Default text roleplay" value={onboardingDefaults.textRoleplayWillingness} options={textRoleplayOptions} onChange={(v) => setOnboardingDefaults(d => ({ ...d, textRoleplayWillingness: v }))} />
                  <SelectControl label="Default sharing" value={onboardingDefaults.partnerSharePermission} options={shareOptions} onChange={(v) => setOnboardingDefaults(d => ({ ...d, partnerSharePermission: v }))} />
                  <SelectControl label="Default intensity" value={onboardingDefaults.intensityPreference} options={intensityOptions} onChange={(v) => setOnboardingDefaults(d => ({ ...d, intensityPreference: v }))} />
                  <button onClick={applyOnboardingDefaults} className="md:col-span-3 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm">Apply Defaults To Checklist</button>
                  <div className="md:col-span-3 text-xs text-slate-500">Sharing defaults stay conservative unless you choose otherwise. Private notes are never shared by default.</div>
                </div>
              )}

              {onboardingStep === 3 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <label className="flex items-end gap-2 text-sm text-slate-300 pb-2">
                    <input type="checkbox" checked={Boolean(profile.realityBridge?.enabled)} onChange={(e) => updateRealityBridge('enabled', e.target.checked)} className="accent-amber-500" />
                    Enable reality bridge
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
              )}

              {onboardingStep === 4 && (
                <div className="bg-slate-950/30 border border-slate-700 rounded p-4 text-sm text-slate-300">
                  <div className="font-bold text-amber-400 mb-2">Ready to save this profile</div>
                  <p>Completing onboarding records a review timestamp and opens the full editor. You can return to the editor any time.</p>
                  <p className="mt-2 text-slate-400">Fantasy interest remains fictional preference data, not real-world consent.</p>
                </div>
              )}

              <div className="flex flex-wrap justify-between gap-2 border-t border-slate-700 pt-4">
                <button onClick={() => setOnboardingStep(Math.max(0, onboardingStep - 1))} disabled={onboardingStep === 0 || busy} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-4 py-2 text-sm">Back</button>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => saveOnboardingProgress(onboardingStep + 1)} disabled={busy || onboardingStep >= onboardingSteps.length - 1} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-4 py-2 text-sm">Save And Continue</button>
                  <button onClick={finishOnboarding} disabled={busy} className="bg-fantasy-accent hover:bg-amber-600 disabled:opacity-50 text-white rounded px-4 py-2 text-sm font-bold">Finish Onboarding</button>
                </div>
              </div>
            </section>
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
                          <SelectControl
                            label="Real world interest"
                            value={item.realWorldWillingness}
                            options={realWorldOptions}
                            onChange={(v) => updateItem(categoryIndex, itemIndex, {
                              realWorldWillingness: v,
                              fantasyOnly: fantasyOnlyRealWorldValues.has(v)
                            })}
                          />
                          <SelectControl label="Intensity" value={item.intensityPreference} options={intensityOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { intensityPreference: v })} />
                          <SelectControl
                            label="My role in this theme"
                            value={item.giverReceiverRole || 'both'}
                            options={giverReceiverOptions}
                            optionLabels={giverReceiverLabels}
                            help={roleSideHelp}
                            onChange={(v) => updateItem(categoryIndex, itemIndex, { giverReceiverRole: v })}
                          />
                          <SelectControl label="Partner share" value={item.partnerSharePermission} options={shareOptions} onChange={(v) => updateItem(categoryIndex, itemIndex, { partnerSharePermission: v })} />
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
                    <div key={question.id || index} className="bg-fantasy-dark/50 border border-slate-700 rounded p-4 grid grid-cols-1 md:grid-cols-[1fr_140px_140px_120px_100px] gap-3">
                      <TextControl label={`Question${question.status === 'archived' ? ' (archived)' : ''}`} rows={2} value={question.label} onChange={(v) => updateCustom(index, { label: v })} />
                      <SelectControl
                        label="My role"
                        value={question.giverReceiverRole || 'both'}
                        options={giverReceiverOptions}
                        optionLabels={giverReceiverLabels}
                        help={roleSideHelp}
                        onChange={(v) => updateCustom(index, { giverReceiverRole: v })}
                      />
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
          <section className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4 flex flex-col gap-3">
            <h2 className="text-xs uppercase tracking-widest text-slate-400">Fantasy Generator</h2>
            <div className="grid grid-cols-2 gap-3">
              <SelectControl label="Context" value={generationOptions.context} options={contextOptions} onChange={(v) => setGenerationOptions(o => ({ ...o, context: v }))} />
              <label className="flex flex-col gap-1 text-xs text-slate-400">
                <span className="uppercase tracking-widest">Themes</span>
                <input
                  type="number"
                  min="1"
                  max="6"
                  value={generationOptions.selectedCount}
                  onChange={(e) => setGenerationOptions(o => ({ ...o, selectedCount: e.target.value }))}
                  className="bg-fantasy-dark border border-slate-600 rounded px-2 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
                />
              </label>
              <SelectControl label="Sharing" value={generationOptions.sharingMode} options={fantasySharingOptions} onChange={(v) => setGenerationOptions(o => ({ ...o, sharingMode: v }))} />
              <SelectControl label="Intensity" value={generationOptions.intensity} options={['', ...intensityOptions]} onChange={(v) => setGenerationOptions(o => ({ ...o, intensity: v }))} />
            </div>
            <div className="flex flex-col gap-2">
              <div className="text-xs uppercase tracking-widest text-slate-400">Categories</div>
              <div className="grid grid-cols-1 gap-1 max-h-40 overflow-y-auto pr-1">
                {(profile?.categories || []).map(category => (
                  <label key={category.id} className="flex items-center gap-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={generationOptions.categoryIds.includes(category.id)}
                      onChange={(e) => updateGenerationCategory(category.id, e.target.checked)}
                      className="accent-amber-500"
                    />
                    {category.label}
                  </label>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={generationOptions.favoritesOnly} onChange={(e) => setGenerationOptions(o => ({ ...o, favoritesOnly: e.target.checked, exploreLowerInterest: e.target.checked ? false : o.exploreLowerInterest }))} className="accent-amber-500" />
              Favorites only
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={generationOptions.exploreLowerInterest} disabled={generationOptions.favoritesOnly} onChange={(e) => setGenerationOptions(o => ({ ...o, exploreLowerInterest: e.target.checked }))} className="accent-amber-500 disabled:opacity-50" />
              Explore lower-interest themes
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={generationOptions.includeRealityBridge} onChange={(e) => setGenerationOptions(o => ({ ...o, includeRealityBridge: e.target.checked }))} className="accent-amber-500" />
              Include reality bridge metadata
            </label>
            <button onClick={generateFantasyDraft} disabled={!profile || busy} className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded-lg px-4 py-3 text-sm font-bold uppercase tracking-widest">Generate Draft</button>
          </section>

          <section className="bg-fantasy-dark/50 border border-slate-700 rounded-lg p-4 flex flex-col gap-3">
            <h2 className="text-xs uppercase tracking-widest text-slate-400">Compare Profiles</h2>
            <select
              value={compareProfileId}
              onChange={(e) => { setCompareProfileId(e.target.value); setComparison(null); }}
              disabled={!profile || compareOptions.length === 0}
              className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent disabled:opacity-50"
            >
              <option value="">Select another profile</option>
              {compareOptions.map(summary => (
                <option key={summary.profileId} value={summary.profileId}>{summary.displayName}</option>
              ))}
            </select>
            <button onClick={compareProfiles} disabled={!profile || !compareProfileId || busy} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Compare</button>
            {comparison && (
              <div className="text-sm flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-2">
                  <button onClick={printComparisonSummary} className="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm">Print Comparison</button>
                  <button onClick={createOverlapFantasy} disabled={busy || !comparison.matches?.length} className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded px-3 py-2 text-sm">Overlap Draft</button>
                </div>
                <div className="text-xs text-slate-500">{comparison.safetyPrinciple}</div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-slate-950/40 border border-slate-700 rounded p-2">
                    <div className="text-lg font-bold text-emerald-300">{comparison.matches?.length || 0}</div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider">Matches</div>
                  </div>
                  <div className="bg-slate-950/40 border border-slate-700 rounded p-2">
                    <div className="text-lg font-bold text-amber-300">{comparison.blocked?.length || 0}</div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider">Blocked</div>
                  </div>
                  <div className="bg-slate-950/40 border border-slate-700 rounded p-2">
                    <div className="text-lg font-bold text-red-300">{comparison.realityBridgeExcludedThemeIds?.length || 0}</div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider">Reality no</div>
                  </div>
                </div>
                {(comparison.matches || []).slice(0, 5).map(match => (
                  <div key={match.id} className="bg-slate-950/40 border border-slate-700 rounded p-2">
                    <div className="font-bold text-amber-400">{match.label}</div>
                    <div className="text-xs text-slate-400 mt-1">
                      {labelize(match.fantasyInterest)} interest / {labelize(match.textRoleplayWillingness)} text / {labelize(match.realWorldWillingness)} real world
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {labelize(match.intensityPreference)} intensity / {roleDirectionLabel(match.giverReceiverRole)}
                    </div>
                    <div className="text-xs text-slate-500 mt-2 flex flex-col gap-1">
                      {(match.compatibilityNotes || []).map(note => <span key={note}>{note}</span>)}
                    </div>
                    {(match.shareableComments || []).length > 0 && (
                      <div className="mt-2 border-t border-slate-700 pt-2 text-xs text-slate-300">
                        {(match.shareableComments || []).map(entry => (
                          <div key={`${match.id}-${entry.profileId}`}><span className="text-slate-500">{entry.profileId}:</span> {entry.comment}</div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {(comparison.blocked || []).length > 0 && (
                  <details className="bg-slate-950/40 border border-slate-700 rounded p-2">
                    <summary className="text-xs uppercase tracking-widest text-slate-400 cursor-pointer">Blocked Details</summary>
                    <div className="mt-2 flex flex-col gap-2">
                      {(comparison.blocked || []).slice(0, 8).map(blocked => (
                        <div key={blocked.id} className="border-t border-slate-700 pt-2">
                          <div className="font-bold text-amber-400">{blocked.label}</div>
                          <div className="text-xs text-slate-400">{(blocked.reasons || []).map(labelize).join(', ')}</div>
                          <div className="text-xs text-slate-500 mt-1">
                            First: {labelize(blocked.first?.fantasyInterest)} fantasy / {labelize(blocked.first?.textRoleplayWillingness)} text / {labelize(blocked.first?.realWorldWillingness)} real / {roleDirectionLabel(blocked.first?.giverReceiverRole)}
                          </div>
                          <div className="text-xs text-slate-500">
                            Second: {labelize(blocked.second?.fantasyInterest)} fantasy / {labelize(blocked.second?.textRoleplayWillingness)} text / {labelize(blocked.second?.realWorldWillingness)} real / {roleDirectionLabel(blocked.second?.giverReceiverRole)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                {comparison.matches?.length === 0 && (
                  <div className="text-xs text-slate-500 italic">No mutually compatible shared themes for this context.</div>
                )}
              </div>
            )}
          </section>

          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-xs uppercase tracking-widest text-slate-400">Saved drafts</h2>
              <label className="text-xs text-amber-400 hover:text-amber-300 cursor-pointer">
                Import
                <input
                  type="file"
                  accept="application/json"
                  onChange={(e) => importFantasyDraft(e.target.files?.[0])}
                  className="hidden"
                />
              </label>
            </div>
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
              <div className="flex flex-col gap-2">
                <label className="flex flex-col gap-1 text-xs text-slate-400">
                  <span className="uppercase tracking-widest">Draft title</span>
                  <input
                    value={activeFantasy.title || ''}
                    readOnly={fantasyIsLocked}
                    onChange={(e) => updateActiveFantasy({ title: e.target.value })}
                    className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-base font-bold text-amber-400 focus:outline-none focus:border-fantasy-accent disabled:opacity-50"
                  />
                </label>
                <p className="text-xs text-slate-500 mt-1">{activeFantasy.id}</p>
              </div>
              {fantasyIsLocked ? (
                <div className="border border-amber-800 bg-amber-950/30 rounded p-3 text-sm text-amber-100">
                  This draft is password protected. Unlock it to view or edit the protected fantasy text.
                </div>
              ) : (
                <>
                  <TextControl label="Synopsis" rows={4} value={activeFantasy.synopsis || ''} onChange={(v) => updateActiveFantasy({ synopsis: v })} />
                  <TextControl label="Fantasy draft" rows={7} value={activeFantasy.content || ''} onChange={(v) => updateActiveFantasy({ content: v })} />
                  <TextControl label="Seed prompt" rows={6} value={activeFantasy.seedPrompt || ''} onChange={(v) => updateActiveFantasy({ seedPrompt: v })} />
                  <TextControl label="Reality bridge notes" rows={3} value={activeFantasy.realityBridgeNotes || ''} onChange={(v) => updateActiveFantasy({ realityBridgeNotes: v })} />
                </>
              )}
              {!fantasyIsLocked && activeFantasy.campaignSeed && (
                <div className="text-xs text-slate-400 bg-slate-950/40 border border-slate-700 rounded p-3">
                  <div className="uppercase tracking-widest text-slate-500 mb-2">Campaign seed</div>
                  <div className="text-slate-300 whitespace-pre-wrap">{activeFantasy.campaignSeed.startingScene}</div>
                </div>
              )}
              <button onClick={saveActiveFantasy} disabled={busy || fantasyIsLocked} className="bg-fantasy-accent hover:bg-amber-600 disabled:opacity-50 text-white rounded px-3 py-2 text-sm font-bold">Save Draft</button>
              <div className="grid grid-cols-2 gap-2">
                <button onClick={regenerateFantasyDraft} disabled={!profile || busy} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Regenerate</button>
                <button onClick={duplicateFantasyDraft} disabled={busy || fantasyIsLocked} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Duplicate</button>
              </div>
              <div className="border-t border-slate-700 pt-3 flex flex-col gap-2">
                <SelectControl label="Export mode" value={exportDraftMode} options={fantasySharingOptions} onChange={setExportDraftMode} />
                <button
                  onClick={exportActiveFantasy}
                  disabled={busy || (activeFantasy.passwordProtection?.enabled && ['private', 'full_scene', 'full_scene_with_notes'].includes(exportDraftMode) && !unlockDraft.unlocked)}
                  className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm"
                >
                  Export Draft
                </button>
                <button onClick={printActiveFantasy} disabled={busy || fantasyIsLocked} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Print View</button>
              </div>
              <button
                onClick={() => onCreateCampaignFromDraft?.(activeFantasy)}
                disabled={busy || fantasyIsLocked || !onCreateCampaignFromDraft}
                className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded px-3 py-2 text-sm font-bold"
              >
                Use Draft in Campaign Setup
              </button>
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
                <div className="border border-emerald-800 bg-emerald-950/30 text-emerald-200 rounded p-3 text-sm flex flex-col gap-2">
                  <div>Password protected{unlockDraft.unlocked ? ' and unlocked for this edit session' : ''}</div>
                  {!unlockDraft.unlocked && (
                    <>
                      {activeFantasy.passwordProtection?.hint && (
                        <div className="text-xs text-emerald-300/80">Hint: {activeFantasy.passwordProtection.hint}</div>
                      )}
                      <input
                        type="password"
                        value={unlockDraft.password}
                        onChange={(e) => setUnlockDraft(d => ({ ...d, password: e.target.value }))}
                        placeholder="Password"
                        className="bg-fantasy-dark border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fantasy-accent"
                      />
                      <button onClick={unlockFantasy} disabled={!unlockDraft.password || busy} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-600 rounded px-3 py-2 text-sm">Unlock Draft</button>
                    </>
                  )}
                </div>
              )}
            </section>
          )}
        </aside>
      </main>
    </div>
  );
}
