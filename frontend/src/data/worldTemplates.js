const worldTemplates = [
  {
    id: 'high-fantasy',
    label: 'High Fantasy',
    description: 'Ancient magic, bright kingdoms, and a relic awakening beneath a border town.',
    worldPrompt: 'A high fantasy realm where ancient sky-temples are waking after a thousand years, drawing rival kingdoms, wandering mages, and dangerous pilgrims toward a small border town.',
    protagonistName: 'Rowan',
    startingLocation: 'The Lantern Ford',
    npcs: [
      {
        name: 'Ser Caldus',
        disposition: 'Friendly',
        gender: 'M',
        appearance: 'An old knight with a dented silver pauldron and careful eyes.',
        description: 'He guards the ford and suspects the old prophecies are becoming literal.',
        secrets_known: ['He once entered a sky-temple and came back with no memory of three days.']
      },
      {
        name: 'Mira Vell',
        disposition: 'Suspicious',
        gender: 'F',
        appearance: 'A traveling scholar in blue robes marked with star charts.',
        description: 'She wants first claim on any artifacts found in the awakened ruins.',
        secrets_known: ['Her royal patron ordered her to sabotage rival expeditions if needed.']
      }
    ],
    lorebook: [
      { keyword: 'SkyTemples', rule: 'Sky-temples are ancient floating ruins that respond to bloodlines, songs, and spoken oaths.' },
      { keyword: 'Relics', rule: 'Relics are powerful but never simple; each gift creates a debt, bond, or visible mark.' },
      { keyword: 'BorderTown', rule: 'The Lantern Ford is crowded with pilgrims, mercenaries, and officials, making secrecy difficult.' }
    ]
  },
  {
    id: 'dark-fantasy',
    label: 'Gritty Dark Fantasy',
    description: 'A famine-struck province where saints stay dead and miracles have prices.',
    worldPrompt: 'A gritty dark fantasy province after a failed harvest, where plague roads, corrupt priests, and hungry nobles circle rumors of a buried saint whose bones still grant miracles.',
    protagonistName: 'Maren',
    startingLocation: 'The Blackroot Chapel',
    npcs: [
      {
        name: 'Prior Othric',
        disposition: 'Neutral',
        gender: 'M',
        appearance: 'A gaunt priest with ink-stained fingers and a cracked wooden rosary.',
        description: 'He keeps the chapel ledger and measures morality in survival.',
        secrets_known: ['He sold false relics to keep the village fed last winter.']
      },
      {
        name: 'Vessa Crowe',
        disposition: 'Suspicious',
        gender: 'F',
        appearance: 'A road warden in patched black leather with a notched axe.',
        description: 'She hunts grave robbers but fears the church more than criminals.',
        secrets_known: ['She saw a dead saint speak through a plague victim.']
      }
    ],
    lorebook: [
      { keyword: 'Miracles', rule: 'Miracles work, but each one transfers suffering somewhere nearby.' },
      { keyword: 'Famine', rule: 'Food, medicine, and clean shelter are scarce enough to drive honest people into ugly bargains.' },
      { keyword: 'TheChurch', rule: 'The church is politically powerful, internally divided, and terrified of uncontrolled relics.' }
    ]
  },
  {
    id: 'sci-fi',
    label: 'Sci-Fi',
    description: 'A failing orbital station, a hidden signal, and factions racing toward first contact.',
    worldPrompt: 'A hard sci-fi orbital station around a storm-wracked exoplanet, where a maintenance failure reveals an impossible signal coming from beneath the clouds.',
    protagonistName: 'Vale',
    startingLocation: 'Docking Ring Seven',
    npcs: [
      {
        name: 'Dr. Imani Ko',
        disposition: 'Friendly',
        gender: 'F',
        appearance: 'A sleep-deprived xenolinguist with a slate full of looping signal glyphs.',
        description: 'She believes the signal is a language and needs protection from station politics.',
        secrets_known: ['She replied to the signal before receiving authorization.']
      },
      {
        name: 'Marshal Brenn',
        disposition: 'Neutral',
        gender: 'M',
        appearance: 'A station security officer with a cracked visor and clipped speech.',
        description: 'He wants order maintained while corporate and scientific crews panic.',
        secrets_known: ['He has orders to quarantine anyone exposed to the signal.']
      }
    ],
    lorebook: [
      { keyword: 'Station', rule: 'The station is aging, underfunded, and dependent on fragile life-support systems.' },
      { keyword: 'Signal', rule: 'The signal affects machines first, then dreams, then spoken language.' },
      { keyword: 'Corporation', rule: 'Corporate command prioritizes proprietary discovery rights over crew safety.' }
    ]
  },
  {
    id: 'horror',
    label: 'Horror',
    description: 'An isolated coastal inn where the guests are vanishing between tides.',
    worldPrompt: 'A slow-burn horror story at an isolated coastal inn during a week of unnatural tides, where guests vanish, old rooms reappear, and the sea leaves messages in salt.',
    protagonistName: 'Clara',
    startingLocation: 'The Gull and Glass Inn',
    npcs: [
      {
        name: 'Nell Armitage',
        disposition: 'Friendly',
        gender: 'F',
        appearance: 'An innkeeper with red hands, tired eyes, and a ring of iron keys.',
        description: 'She is desperate to keep everyone calm until the road reopens.',
        secrets_known: ['Her brother disappeared in the inn twenty years ago and returned last night unchanged.']
      },
      {
        name: 'Mr. Vale',
        disposition: 'Suspicious',
        gender: 'M',
        appearance: 'A pale guest in a salt-stained suit who never seems fully dry.',
        description: 'He asks polite questions about everyone staying at the inn.',
        secrets_known: ['He has signed the guestbook under seven different names across seventy years.']
      }
    ],
    lorebook: [
      { keyword: 'TheInn', rule: 'The inn changes subtly after midnight; doors, rooms, and corridors cannot be fully trusted.' },
      { keyword: 'TheSea', rule: 'The sea behaves like an intelligent presence but never explains itself directly.' },
      { keyword: 'HorrorTone', rule: 'Build dread through sensory details, uncertainty, and consequences rather than sudden gore.' }
    ]
  },
  {
    id: 'historical-medieval',
    label: 'Historical',
    description: 'A medieval market town caught between a disputed inheritance and a winter siege.',
    worldPrompt: 'A grounded medieval drama in a market town during a disputed inheritance, as winter closes the roads and soldiers from two claimants begin arriving at the gates.',
    protagonistName: 'Thomas',
    startingLocation: 'Market Cross of Avelwyck',
    npcs: [
      {
        name: 'Alys Brewer',
        disposition: 'Friendly',
        gender: 'F',
        appearance: 'A practical brewer with rolled sleeves and a sharp measuring eye.',
        description: 'She knows every household debt and every rumor passing through town.',
        secrets_known: ['She hides letters proving the weaker claimant has the lawful title.']
      },
      {
        name: 'Captain Rook',
        disposition: 'Hostile',
        gender: 'M',
        appearance: 'A scarred mercenary captain with a muddy cloak and a polished sword.',
        description: 'He intends to secure supplies before the opposing army arrives.',
        secrets_known: ['His men are not being paid and may mutiny if denied plunder.']
      }
    ],
    lorebook: [
      { keyword: 'HistoryTone', rule: 'Keep events grounded in medieval social limits, travel times, weapons, and political customs.' },
      { keyword: 'Inheritance', rule: 'The succession dispute drives every major faction choice in Avelwyck.' },
      { keyword: 'Winter', rule: 'Snow, hunger, disease, and blocked roads should matter as practical constraints.' }
    ]
  },
  {
    id: 'modern-paranormal',
    label: 'Modern Paranormal',
    description: 'A desert town, a missing radio host, and strange voices beneath the static.',
    worldPrompt: 'A modern paranormal mystery in a remote desert town where a late-night radio host vanishes after broadcasting voices from an abandoned numbers station.',
    protagonistName: 'Riley',
    startingLocation: 'KZRO Radio, Studio B',
    npcs: [
      {
        name: 'June Ortega',
        disposition: 'Friendly',
        gender: 'F',
        appearance: 'A deputy with dust on her boots and a notebook full of crossed-out timelines.',
        description: 'She wants a rational explanation but keeps finding impossible evidence.',
        secrets_known: ['She heard her dead father speaking in last night\'s broadcast.']
      },
      {
        name: 'Eli Ward',
        disposition: 'Neutral',
        gender: 'NB',
        appearance: 'A tower technician with mirrored sunglasses and a coil of cable over one shoulder.',
        description: 'They understand the old station equipment better than anyone in town.',
        secrets_known: ['They have been secretly recording the signal for months.']
      }
    ],
    lorebook: [
      { keyword: 'Static', rule: 'The radio static carries voices that know private facts, but they rarely tell the whole truth.' },
      { keyword: 'DesertTown', rule: 'The town is small enough that everyone knows each other, making secrets socially dangerous.' },
      { keyword: 'ParanormalRules', rule: 'The supernatural is real but leaves physical traces that can be investigated.' }
    ]
  }
];

export default worldTemplates;
